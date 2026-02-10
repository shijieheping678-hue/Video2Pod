"""Audio transcription module supporting multiple ASR providers.

Provides speech-to-text transcription via Alibaba DashScope (Qwen ASR)
or Volcengine (ByteDance) ASR services. Supports caching to avoid
redundant API calls for previously transcribed files.
"""

import os
import base64
import time
from openai import OpenAI
from src.utils import logger
from src.volc_service import VolcService


class Transcriber:
    """Multi-provider audio transcription service.

    Supports two ASR backends:
    - **DashScope** (Alibaba): Uses Qwen3-ASR-Flash via OpenAI-compatible API.
    - **Volcengine** (ByteDance): Uses TOS upload + async ASR task pipeline.

    Transcription results are cached as text files alongside the source audio
    to avoid repeated API calls.

    Attributes:
        provider (str): The ASR provider to use ("dashscope" or "volc").
        api_key (str): API key for DashScope provider (not used for Volcengine).
        client (OpenAI): OpenAI-compatible client for DashScope (only when provider="dashscope").
        volc_service (VolcService): Volcengine service instance (only when provider="volc").
    """

    def __init__(self, provider="dashscope", api_key=None):
        """Initialize the Transcriber with the specified ASR provider.

        Args:
            provider (str): ASR backend to use. One of "dashscope" or "volc".
                Defaults to "dashscope".
            api_key (str, optional): API key for DashScope. If not provided,
                reads from the ``DASHSCOPE_API_KEY`` environment variable.
                Ignored when provider is "volc".
        """
        self.provider = provider
        self.api_key = api_key

        if self.provider == "dashscope":
            self.api_key = self.api_key or os.getenv("DASHSCOPE_API_KEY")
            if not self.api_key:
                logger.warning("DASHSCOPE_API_KEY not found. Transcription may fail.")

            # Initialize OpenAI client compatible with DashScope
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        elif self.provider == "volc":
            self.volc_service = VolcService()

    def transcribe(self, audio_file_path, resume_task_id=None, task_id_callback=None):
        """Transcribe an audio file to text using the configured provider.

        Routes the request to the appropriate backend (DashScope or Volcengine)
        based on the provider set during initialization.

        Args:
            audio_file_path (str): Path to the audio file to transcribe.
            resume_task_id (str, optional): For Volcengine only. If provided,
                resumes polling an existing ASR task instead of creating a new one.
            task_id_callback (callable, optional): For Volcengine only. A callback
                function that receives the task ID immediately after submission,
                allowing the caller to persist it for later resumption.

        Returns:
            str: The transcribed text content.

        Raises:
            FileNotFoundError: If the audio file does not exist.
            Exception: If the transcription API call fails.
        """
        if self.provider == "volc":
            return self.transcribe_volc(audio_file_path, resume_task_id, task_id_callback)
        else:
            return self.transcribe_dashscope(audio_file_path)

    def transcribe_volc(self, audio_file_path, resume_task_id=None, task_id_callback=None):
        """Transcribe audio using Volcengine ASR (TOS upload + async task).

        Workflow:
        1. Check for a cached transcript file (``<audio_path>.volc.txt``).
        2. If no cache and no ``resume_task_id``, upload the audio to TOS
           and submit a new ASR task.
        3. Poll the ASR task until completion.
        4. Cache the result to a local text file.

        Args:
            audio_file_path (str): Path to the audio file to transcribe.
            resume_task_id (str, optional): An existing Volcengine ASR task ID
                to resume polling instead of creating a new task.
            task_id_callback (callable, optional): Called with the task ID
                immediately after submission, useful for persistence.

        Returns:
            str: The transcribed text content.

        Raises:
            FileNotFoundError: If the audio file does not exist.
            Exception: If TOS upload, ASR submission, or result polling fails.
        """
        logger.info(f"Transcribing audio with Volcengine: {audio_file_path}")

        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

        # Check for cached transcript
        cache_file = f"{audio_file_path}.volc.txt"
        if os.path.exists(cache_file):
            logger.info(f"Found cached transcript: {cache_file}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()

        try:
            task_id = resume_task_id

            if not task_id:
                # 1. Upload to TOS
                logger.info("Uploading to TOS...")
                file_url = self.volc_service.upload_to_tos(audio_file_path)

                # 2. Submit Task
                logger.info("Submitting ASR task...")
                task_id = self.volc_service.submit_asr_task(file_url)

                # Callback to save task ID immediately
                if task_id_callback:
                    task_id_callback(task_id)
            else:
                logger.info(f"Resuming existing Volcengine task: {task_id}")

            # 3. Poll for results
            logger.info(f"Polling for results (Task ID: {task_id})...")
            while True:
                result = self.volc_service.get_asr_result(task_id)
                status = result["status"]

                if status == "success":
                    transcript = result["text"]
                    logger.info("Volcengine Transcription successful")
                    break
                elif status == "failed":
                    raise Exception(f"Volcengine ASR failed: {result['message']}")

                # running
                time.sleep(2) # Wait before next poll

            # Save to cache
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(transcript)

            return transcript

        except Exception as e:
            logger.error(f"Volcengine Transcription error: {str(e)}")
            raise e

    def transcribe_dashscope(self, audio_file_path):
        """Transcribe audio using Alibaba DashScope (Qwen3-ASR-Flash).

        Uses the OpenAI-compatible API with base64-encoded audio input.
        Results are cached to ``<audio_path>.txt`` to avoid repeated API calls.

        Args:
            audio_file_path (str): Path to the audio file to transcribe.
                Supported formats: mp3, wav, m4a, flac, etc.

        Returns:
            str: The transcribed text content.

        Raises:
            FileNotFoundError: If the audio file does not exist.
            Exception: If the DashScope API call fails.
        """
        logger.info(f"Transcribing audio with DashScope (qwen3-asr-flash): {audio_file_path}")

        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

        # Check for cached transcript
        cache_file = f"{audio_file_path}.txt"
        if os.path.exists(cache_file):
            logger.info(f"Found cached transcript: {cache_file}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()

        try:
            # 1. Read file and encode to base64
            with open(audio_file_path, "rb") as audio_file:
                audio_data = audio_file.read()
                # Ensure no newlines in base64
                encoded_audio = base64.b64encode(audio_data).decode('utf-8').replace('\n', '')

            # 2. Call the API
            # Note: For qwen3-asr-flash via OpenAI SDK, 'data' field usually expects URL or Base64.
            # If providing Base64, it might need to be clean.

            completion = self.client.chat.completions.create(
                model="qwen3-asr-flash",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": f"data:audio/mp3;base64,{encoded_audio}",
                                    "format": "mp3"
                                }
                            }
                        ]
                    }
                ],
                extra_body={
                    "asr_options": {
                        "enable_itn": False
                    }
                }
            )

            # 3. Extract text
            transcript = completion.choices[0].message.content
            logger.info("Transcription successful")

            # Save to cache
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(transcript)

            return transcript

        except Exception as e:
            logger.error(f"DashScope Transcription error: {str(e)}")
            raise e
