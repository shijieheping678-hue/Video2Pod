"""Voice cloning module using Volcengine (ByteDance) Mega TTS API.

Provides functionality to upload audio samples for voice cloning training,
check training status, and wait for training completion. Supports both
ICL 1.0 and ICL 2.0 voice cloning models.
"""

import os
import json
import base64
import requests
import time
from src.utils import logger


class VoiceCloner:
    """Volcengine voice cloning client for training custom TTS voices.

    Handles the full voice cloning lifecycle: audio upload, training
    submission, and status polling via the Volcengine Mega TTS API.

    Attributes:
        appid (str): Volcengine application ID.
        token (str): Volcengine access token for authentication.
        host (str): Base URL for the Volcengine OpenSpeech API.
        default_model_type (int): Default cloning model type (1 = ICL 1.0).
        default_resource_id (str): Default resource ID for API requests.
    """

    def __init__(self):
        """Initialize VoiceCloner with credentials from environment variables.

        Reads ``VOLC_APPID`` and ``VOLC_ACCESS_TOKEN`` from the environment,
        falling back to hardcoded defaults if not set.
        """
        self.appid = os.getenv("VOLC_APPID")
        self.token = os.getenv("VOLC_ACCESS_TOKEN")
        self.host = "https://openspeech.bytedance.com"

        # 默认配置
        self.default_model_type = 1 # ICL 1.0
        self.default_resource_id = "seed-icl-1.0" # ICL 1.0 对应的 resource id

    def _get_headers(self, resource_id=None):
        """Build HTTP headers for Volcengine API requests.

        Args:
            resource_id (str, optional): The API resource ID to use.
                Defaults to ``self.default_resource_id`` if not provided.

        Returns:
            dict: HTTP headers including authorization and content type.

        Raises:
            Exception: If ``appid`` or ``token`` is not configured.
        """
        if not self.appid or not self.token:
            raise Exception("VOLC_APPID or VOLC_ACCESS_TOKEN not configured.")

        return {
            "Authorization": f"Bearer;{self.token}",
            "Resource-Id": resource_id or self.default_resource_id,
            "Content-Type": "application/json"
        }

    def upload_audio(self, file_path, speaker_id, model_type=4, language=0):
        """Upload an audio sample to start voice cloning training.

        Reads the audio file, encodes it as base64, and submits it to the
        Volcengine Mega TTS training endpoint.

        Args:
            file_path (str): Path to the local audio file (wav, mp3, m4a, etc.).
            speaker_id (str): Unique identifier for the cloned voice.
                This ID will be used later to reference the voice in TTS calls.
            model_type (int): Cloning model version to use.
                1 = ICL 1.0 (recommended), 4 = ICL 2.0. Defaults to 4.
            language (int): Language of the audio sample.
                0 = Chinese (default), 1 = English.

        Returns:
            dict: API response containing status and request metadata.

        Raises:
            FileNotFoundError: If the audio file does not exist.
            Exception: If the upload fails or the API returns an error.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        # Determine Resource ID based on model_type
        # Document says: seed-icl-1.0 for model_type=1/2/3, seed-icl-2.0 for model_type=4
        resource_id = "seed-icl-2.0" if model_type == 4 else "seed-icl-1.0"

        url = f"{self.host}/api/v1/mega_tts/audio/upload"

        # Read and encode audio
        with open(file_path, "rb") as f:
            audio_data = f.read()
            encoded_audio = base64.b64encode(audio_data).decode('utf-8')

        file_ext = os.path.splitext(file_path)[1][1:].lower() # e.g. "mp3"
        if file_ext == "wav": file_ext = "wav" # Ensure format string matches requirement if needed

        headers = self._get_headers(resource_id)

        payload = {
            "appid": self.appid,
            "speaker_id": speaker_id,
            "audios": [{
                "audio_bytes": encoded_audio,
                "audio_format": file_ext
            }],
            "source": 2, # Fixed value
            "language": language,
            "model_type": model_type,
            # Optional extra params - Try empty if error persists
            "extra_params": "{}"
        }

        try:
            logger.info(f"Uploading audio to {url}")
            logger.info(f"Headers: {headers}")
            logger.info(f"Payload keys: {payload.keys()}")

            resp = requests.post(url, json=payload, headers=headers)
            resp_data = resp.json()

            logger.info(f"Response: {resp_data}")

            if "BaseResp" in resp_data and resp_data["BaseResp"]["StatusCode"] == 0:
                logger.info(f"Voice upload successful: {speaker_id}")
                return resp_data
            else:
                msg = resp_data.get("BaseResp", {}).get("StatusMessage", "Unknown Error")
                code = resp_data.get("BaseResp", {}).get("StatusCode")
                raise Exception(f"Voice upload failed: {msg} (Code: {code})")

        except Exception as e:
            logger.error(f"Voice Clone Upload Exception: {e}")
            raise e

    def check_status(self, speaker_id, model_type=4):
        """Query the training status of a cloned voice.

        Args:
            speaker_id (str): The unique voice identifier to check.
            model_type (int): Cloning model version (determines resource ID).
                1 = ICL 1.0, 4 = ICL 2.0. Defaults to 4.

        Returns:
            int: Voice training status code.
                - 0: Not found
                - 1: Training in progress
                - 2: Training successful
                - 3: Training failed
                - 4: Active (ready to use)
                - -1: Query error
        """
        resource_id = "seed-icl-2.0" if model_type == 4 else "seed-icl-1.0"
        url = f"{self.host}/api/v1/mega_tts/status"

        payload = {
            "appid": self.appid,
            "speaker_id": speaker_id
        }

        try:
            resp = requests.post(url, json=payload, headers=self._get_headers(resource_id))
            resp_data = resp.json()

            if "BaseResp" in resp_data and resp_data["BaseResp"]["StatusCode"] == 0:
                status = resp_data.get("status")
                logger.info(f"Voice status for {speaker_id}: {status}")
                return status
            else:
                logger.error(f"Check status failed: {resp_data}")
                return -1 # Error

        except Exception as e:
            logger.error(f"Check Status Exception: {e}")
            return -1

    def wait_for_training(self, speaker_id, timeout=60):
        """Poll training status until the voice is ready or timeout is reached.

        Repeatedly calls ``check_status`` every 2 seconds until the voice
        reaches a successful state (2 or 4) or the timeout expires.

        Args:
            speaker_id (str): The unique voice identifier to monitor.
            timeout (int): Maximum wait time in seconds. Defaults to 60.

        Returns:
            bool: True if training completed successfully.

        Raises:
            Exception: If training fails (status 3) or times out.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.check_status(speaker_id)
            if status == 2 or status == 4: # Success or Active
                return True
            elif status == 3: # Failed
                raise Exception("Voice training failed.")
            elif status == 0: # Not Found (maybe not uploaded yet?)
                pass

            time.sleep(2)

        raise Exception("Voice training timed out.")

if __name__ == "__main__":
    # import argparse
    # from dotenv import load_dotenv
    #
    # # Load env vars if running directly
    # load_dotenv()
    #
    # parser = argparse.ArgumentParser(description="Volcengine Voice Cloning Tool")
    # parser.add_argument("file_path", help="Path to the audio file for training")
    # parser.add_argument("speaker_id", help="Unique ID for the new voice")
    # parser.add_argument("--model_type", type=int, default=1, help="Model type: 1=ICL1.0 (default), 4=ICL2.0")
    #
    # args = parser.parse_args()
    #
    # if not os.path.exists(args.file_path):
    #     print(f"Error: File '{args.file_path}' not found.")
    #     exit(1)
    #
    # cloner = VoiceCloner()
    #
    # try:
    #     print(f"--- Starting Voice Cloning ---")
    #     print(f"File: {args.file_path}")
    #     print(f"Speaker ID: {args.speaker_id}")
    #     print(f"Model Type: {args.model_type}")
    #
    #     # 1. Upload
    #     resp = cloner.upload_audio(args.file_path, args.speaker_id, model_type=args.model_type)
    #     print(f"Upload successful. Request ID: {resp.get('BaseResp', {}).get('RequestId')}")
    #
    #     # 2. Wait
    #     print("Waiting for training to complete...")
    #     cloner.wait_for_training(args.speaker_id)
    #
    #     print(f"\n[SUCCESS] Voice '{args.speaker_id}' is ready!")
    #     print(f"You can now use '{args.speaker_id}' as the Guest Voice ID in the Podcast Generator settings.")
    #
    # except Exception as e:
    #     print(f"\n[ERROR] Training failed: {e}")
    #     exit(1)

    print(f"开始训练音色: S_0VWdKj6T1 ...")

    cloner = VoiceCloner()
    speaker_id = "S_0VWdKj6T1"
    try:
        # 1. 上传
        cloner.upload_audio("../my.m4a", speaker_id)
        print("上传成功，正在训练中...")

        # 2. 等待结果 (会阻塞直到完成或超时)
        cloner.wait_for_training(speaker_id, timeout=120)

        print(f"训练成功！音色ID: {speaker_id}")

    except Exception as e:
        print(f"训练失败: {str(e)}")
