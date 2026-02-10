"""Volcengine (ByteDance) unified service module.

Provides a single entry point for all Volcengine cloud services used in the
podcast generator, including:
- **TOS** (Tinder Object Storage): File upload and pre-signed URL generation.
- **ASR** (Automatic Speech Recognition): V1 standard and V2/V3 BigModel APIs.
- **TTS** (Text-to-Speech): V1 standard, V3 streaming, and cloned voice synthesis.

All credentials are read from environment variables (see ``.env``).
"""

import base64
import os
import time
import json
import uuid
import requests
import tos
from src.utils import logger
from tos.enum import HttpMethodType


class VolcService:
    """Unified client for Volcengine TOS, ASR, and TTS services.

    Manages authentication, API routing (V1 vs V2/V3), and provides
    methods for file upload, speech recognition, and speech synthesis.

    Attributes:
        ak (str): Volcengine IAM access key (for TOS).
        sk (str): Volcengine IAM secret key (for TOS).
        region (str): Volcengine region (default: "cn-beijing").
        appid (str): Volcengine application ID (for Speech APIs).
        token (str): Volcengine access token (for Speech APIs).
        appkey (str): Volcengine app key (for V2/V3 APIs).
        cluster (str): ASR cluster identifier.
        version (str): ASR API version preference ("v1" or "v2").
        tos_endpoint (str): TOS service endpoint URL.
        tos_bucket (str): TOS bucket name for file storage.
        tos_folder (str): TOS folder prefix for uploaded files.
        tos_client (tos.TosClientV2 | None): Initialized TOS client instance.
    """

    def __init__(self):
        """Initialize VolcService with credentials from environment variables.

        Reads all configuration from environment variables prefixed with ``VOLC_``.
        Initializes the TOS client if access key, secret key, and endpoint are available.

        Environment variables used:
            - ``VOLC_ACCESS_KEY``: IAM access key for TOS.
            - ``VOLC_SECRET_KEY``: IAM secret key for TOS.
            - ``VOLC_REGION``: Cloud region (default: "cn-beijing").
            - ``VOLC_APPID``: Application ID for Speech services.
            - ``VOLC_ACCESS_TOKEN``: Access token for Speech services.
            - ``VOLC_APPKEY``: App key for V2/V3 APIs.
            - ``VOLC_ASR_CLUSTER``: ASR cluster (default: "volc_auc_common").
            - ``VOLC_ASR_VERSION``: ASR version preference (default: "v1").
            - ``VOLC_TOS_ENDPOINT``: TOS endpoint URL.
            - ``VOLC_TOS_BUCKET``: TOS bucket name.
            - ``VOLC_TOS_FOLDER``: TOS folder prefix (default: "podcast-inputs/").
        """
        # TOS Auth (Global IAM)
        self.ak = os.getenv("VOLC_ACCESS_KEY")
        self.sk = os.getenv("VOLC_SECRET_KEY")
        self.region = os.getenv("VOLC_REGION", "cn-beijing")

        # Speech Auth
        self.appid = os.getenv("VOLC_APPID")
        self.token = os.getenv("VOLC_ACCESS_TOKEN")
        self.appkey = os.getenv("VOLC_APPKEY") # For V2
        self.cluster = os.getenv("VOLC_ASR_CLUSTER", "volc_auc_common")

        # Version Control (v1 or v2/bigmodel)
        self.version = os.getenv("VOLC_ASR_VERSION", "v1").lower()

        # TOS Config
        self.tos_endpoint = os.getenv("VOLC_TOS_ENDPOINT", "tos-cn-beijing.volces.com")
        self.tos_bucket = os.getenv("VOLC_TOS_BUCKET")
        self.tos_folder = os.getenv("VOLC_TOS_FOLDER", "podcast-inputs/")

        # Initialize TOS Client
        self.tos_client = None
        if self.ak and self.sk and self.tos_endpoint:
            try:
                self.tos_client = tos.TosClientV2(
                    self.ak,
                    self.sk,
                    self.tos_endpoint,
                    self.region
                )
                logger.info("Volcengine TOS Client initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize TOS client: {e}")

    def upload_to_tos(self, file_path):
        """Upload a file to TOS and return a pre-signed download URL.

        Checks if the file already exists in TOS before uploading to avoid
        duplicates. Generates a pre-signed URL valid for 1 hour.

        Args:
            file_path (str): Path to the local file to upload.

        Returns:
            str: Pre-signed HTTPS URL for accessing the uploaded file.

        Raises:
            Exception: If the TOS client is not initialized or the bucket
                is not configured, or if the upload/signing operation fails.
        """
        if not self.tos_client:
            raise Exception("TOS client not initialized. Check VOLC_ACCESS_KEY/SK/ENDPOINT in .env")

        if not self.tos_bucket:
            raise Exception("VOLC_TOS_BUCKET not configured in .env")

        file_name = os.path.basename(file_path)
        # Use original filename as key (skip if exists)
        object_key = f"{self.tos_folder.strip('/')}/{file_name}"

        try:
            # 1. Check if object exists
            exists = False
            try:
                self.tos_client.head_object(self.tos_bucket, object_key)
                exists = True
                logger.info(f"File already exists in TOS, skipping upload: {object_key}")
            except Exception:
                exists = False

            # 2. Upload if not exists
            if not exists:
                logger.info(f"Uploading {file_path} to TOS: {self.tos_bucket}/{object_key}")
                self.tos_client.put_object_from_file(self.tos_bucket, object_key, file_path)

            # 3. Generate pre-signed URL
            signed_url = self.tos_client.pre_signed_url(
                HttpMethodType.Http_Method_Get,
                self.tos_bucket,
                object_key,
                expires=3600
            )
            logger.info(f"Generated TOS signed URL")

            # Extract string URL
            if hasattr(signed_url, 'signed_url'):
                return signed_url.signed_url
            return str(signed_url)

        except Exception as e:
            logger.error(f"TOS operation failed: {e}")
            raise e

    def submit_asr_task(self, file_url, language="zh-CN"):
        """Submit an ASR (speech recognition) task to Volcengine.

        Routes to V1 or V2 API based on the ``VOLC_ASR_VERSION`` setting.

        Args:
            file_url (str): URL of the audio file (typically a TOS pre-signed URL).
            language (str): Language code for recognition. Defaults to "zh-CN".

        Returns:
            str: The ASR task ID for polling results.

        Raises:
            Exception: If the ASR submission fails.
        """
        if self.version in ["v2", "bigmodel"]:
            return self.submit_asr_task_v2(file_url, language)
        else:
            return self.submit_asr_task_v1(file_url, language)

    def submit_asr_task_v1(self, file_url, language="zh-CN"):
        """Submit an ASR task using the V1 Standard/Universal API.

        Args:
            file_url (str): URL of the audio file to transcribe.
            language (str): Language code. Defaults to "zh-CN".

        Returns:
            str: The V1 ASR task ID.

        Raises:
            Exception: If ``VOLC_APPID`` or ``VOLC_ACCESS_TOKEN`` is missing,
                or if the API returns an error.
        """
        if not self.appid or not self.token:
            raise Exception("VOLC_APPID or VOLC_ACCESS_TOKEN not configured for V1.")

        url = "https://openspeech.bytedance.com/api/v1/auc/submit"
        headers = {
            "Authorization": f"Bearer; {self.token}",
            "Content-Type": "application/json"
        }

        # Payload matching the Demo structure
        payload = {
            "app": {
                "appid": self.appid,
                "token": self.token,
                "cluster": self.cluster
            },
            "user": {
                "uid": "podcast_generator_user"
            },
            "audio": {
                "format": "mp3", # Demo used wav, but we upload mp3 mostly.
                "url": file_url
            },
            "additions": {
                "with_speaker_info": "True", # We might want speaker info for dialogue
                "language": language
            }
        }

        try:
            resp = requests.post(url, json=payload, headers=headers)
            resp_data = resp.json()

            # Demo: id = resp_dic['resp']['id']
            if "resp" in resp_data and "id" in resp_data["resp"]:
                task_id = resp_data["resp"]["id"]
                logger.info(f"ASR Task Submitted (V1). ID: {task_id}")
                return task_id

            # Error handling
            msg = resp_data.get("resp", {}).get("message", "Unknown error")
            raise Exception(f"ASR Submit Failed (V1): {msg}")

        except Exception as e:
            logger.error(f"ASR Submit Exception (V1): {e}")
            raise e

    def submit_asr_task_v2(self, file_url, language="zh-CN"):
        """Submit an ASR task using the V3 BigModel API.

        Args:
            file_url (str): URL of the audio file to transcribe.
            language (str): Language code. Defaults to "zh-CN".

        Returns:
            str: Composite task ID in ``"uuid|logid"`` format, needed for
                polling results via ``get_asr_result_v2``.

        Raises:
            Exception: If ``VOLC_APPKEY`` or ``VOLC_ACCESS_TOKEN`` is missing,
                or if the API returns an error status code.
        """
        if not self.appkey or not self.token:
            raise Exception("VOLC_APPKEY or VOLC_ACCESS_TOKEN not configured for V2.")

        url = "https://openspeech-direct.zijieapi.com/api/v3/auc/bigmodel/submit"
        task_uuid = str(uuid.uuid4())

        headers = {
            "X-Api-App-Key": self.appid,
            "X-Api-Access-Key": self.token,
            "X-Api-Resource-Id": "volc.bigasr.auc",
            "X-Api-Request-Id": task_uuid,
            "X-Api-Sequence": "-1"
        }

        payload = {
            "user": {"uid": "podcast_generator_user"},
            "audio": {"url": file_url, "format": "mp3"},
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_speaker_info": True,
                "language": language
            }
        }

        try:
            resp = requests.post(url, json=payload, headers=headers)

            # Check Header Status
            status_code = resp.headers.get("X-Api-Status-Code")
            if status_code != "20000000":
                 msg = resp.headers.get("X-Api-Message", "Unknown Error")
                 raise Exception(f"ASR Submit Failed (V2): {status_code} - {msg}")

            x_tt_logid = resp.headers.get("X-Tt-Logid", "")
            composite_id = f"{task_uuid}|{x_tt_logid}"

            logger.info(f"ASR Task Submitted (V2). ID: {composite_id}")
            return composite_id

        except Exception as e:
            logger.error(f"ASR Submit Exception (V2): {e}")
            raise e

    def get_asr_result(self, task_id):
        """Poll for ASR task results, routing to V1 or V2 based on configuration.

        Args:
            task_id (str): The ASR task ID returned by ``submit_asr_task``.

        Returns:
            dict: Result dictionary with keys:
                - ``status`` (str): "success", "running", or "failed".
                - ``text`` (str): Transcribed text (only when status is "success").
                - ``message`` (str): Error message (only when status is "failed").
        """
        if self.version in ["v2", "bigmodel"]:
            return self.get_asr_result_v2(task_id)
        else:
            return self.get_asr_result_v1(task_id)

    def get_asr_result_v1(self, task_id):
        """Poll for ASR results using the V1 Standard API.

        Args:
            task_id (str): The V1 ASR task ID.

        Returns:
            dict: Result with ``status`` ("success"/"running"/"failed"),
                and ``text``/``utterances`` on success.

        Raises:
            Exception: If the API response is invalid or the query fails.
        """
        url = "https://openspeech.bytedance.com/api/v1/auc/query"
        headers = {
            "Authorization": f"Bearer; {self.token}",
            "Content-Type": "application/json"
        }

        # Demo: query_dic['appid'] = ... (Flat structure)
        payload = {
            "appid": self.appid,
            "token": self.token,
            "id": task_id,
            "cluster": self.cluster
        }

        try:
            resp = requests.post(url, json=payload, headers=headers)
            data = resp.json()

            if "resp" not in data:
                 raise Exception(f"Invalid ASR response: {data}")

            resp_body = data["resp"]
            code = resp_body.get("code")
            message = resp_body.get("message", "")

            # Demo Logic:
            # code == 1000 -> Success
            if code == 1000:
                text = resp_body.get("text", "")
                utterances = resp_body.get("utterances", [])
                return {"status": "success", "text": text, "utterances": utterances}

            # Demo Logic: elif code < 2000: failed
            if code < 2000:
                 return {"status": "failed", "message": f"{code}: {message}"}

            # If code >= 2000, treat as running
            return {"status": "running"}

        except Exception as e:
            logger.error(f"ASR Query Exception (V1): {e}")
            raise e

    def get_asr_result_v2(self, composite_task_id):
        """Poll for ASR results using the V3 BigModel API.

        Args:
            composite_task_id (str): Composite ID in ``"uuid|logid"`` format,
                as returned by ``submit_asr_task_v2``.

        Returns:
            dict: Result with ``status`` ("success"/"running"/"failed"),
                and ``text`` on success.

        Raises:
            Exception: If the composite ID format is invalid or the query fails.
        """
        try:
            task_id, x_tt_logid = composite_task_id.split("|")
        except ValueError:
            raise Exception("Invalid V2 task_id format. Expected 'uuid|logid'")

        url = "https://openspeech-direct.zijieapi.com/api/v3/auc/bigmodel/query"

        headers = {
            "X-Api-App-Key": self.appid,
            "X-Api-Access-Key": self.token,
            "X-Api-Resource-Id": "volc.bigasr.auc",
            "X-Api-Request-Id": task_id,
            "X-Tt-Logid": x_tt_logid
        }

        try:
            resp = requests.post(url, json={}, headers=headers)
            data = resp.json()

            # Check Status in Header
            status_code = resp.headers.get("X-Api-Status-Code")

            # 20000000: Success
            if status_code == "20000000":
                if "result" in data:
                    text = data["result"].get("text", "")
                    return {"status": "success", "text": text}
                return {"status": "running"} # Should have result, but if not, assume running?

            # 20000001: Processing, 20000002: In Queue
            if status_code in ["20000001", "20000002"]:
                return {"status": "running"}

            # 20000003: Silent Audio
            if status_code == "20000003":
                 return {"status": "failed", "message": "Silent audio detected (20000003)"}

            # Other errors
            msg = resp.headers.get("X-Api-Message", "Unknown Error")
            raise Exception(f"ASR Query Failed (V2): {status_code} - {msg}")

        except Exception as e:
            logger.error(f"ASR Query Exception (V2): {e}")
            raise e

    def synthesize_standard_tts(self, text, voice_type, output_file, speed_ratio=1.0):
        """Synthesize speech using standard or BigModel voices via V3 API.

        Args:
            text (str): Text content to synthesize.
            voice_type (str): Volcengine voice identifier (e.g., "BV001_streaming").
            output_file (str): Path to save the generated MP3 file.
            speed_ratio (float): Speech speed multiplier. Defaults to 1.0.

        Returns:
            str: Path to the output audio file.

        Raises:
            Exception: If the V3 TTS API call fails after retries.
        """
        return self._synthesize_v3_internal(text, voice_type, output_file, speed_ratio)

    def synthesize_cloned_tts(self, text, voice_type, output_file, speed_ratio=1.0):
        """Synthesize speech using a cloned voice via V1 ICL API.

        Cloned voices (IDs starting with "S_") require the V1 API with the
        ``volcano_icl`` cluster, which is distinct from the standard TTS endpoint.

        Args:
            text (str): Text content to synthesize.
            voice_type (str): Cloned voice identifier (e.g., "S_0VWdKj6T1").
            output_file (str): Path to save the generated MP3 file.
            speed_ratio (float): Speech speed multiplier. Defaults to 1.0.

        Returns:
            str: Path to the output audio file.

        Raises:
            Exception: If the V1 TTS API call fails after retries.
        """
        return self._synthesize_v1_internal(text, voice_type, output_file, speed_ratio, cluster="volcano_icl")

    def _synthesize_v3_internal(self, text, voice_type, output_file, speed_ratio):
        """Internal helper for V3 TTS streaming API.

        Sends a streaming TTS request and accumulates audio chunks into
        a single MP3 file. Includes retry logic with exponential backoff.

        Args:
            text (str): Text content to synthesize.
            voice_type (str): Voice identifier.
            output_file (str): Path to save the MP3 output.
            speed_ratio (float): Speech speed multiplier.

        Returns:
            str: Path to the output audio file.

        Raises:
            Exception: If all retry attempts fail.
        """
        if not self.appkey or not self.token:
            raise Exception("VOLC_APPKEY or VOLC_ACCESS_TOKEN not configured for V3 TTS.")

        api_url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
        task_uuid = str(uuid.uuid4())
        session = requests.Session()
        headers = {
            "X-Api-App-Id": self.appid,
            "X-Api-Access-Key": self.token,
            # Resource ID is optional or specific.
            # If 'volc.tts' fails, try omitting it or using 'volcano_tts'
            # Let's try omitting it first as some V3 docs suggest it's optional for standard TTS
            "X-Api-Resource-Id": "seed-tts-2.0",
            "Content-Type": "application/json",
            "Connection": "keep-alive"
        }

        request_json = {
            "user": {
                "uid": "podcast_generator_user"
            },
            "req_params": {
                "text": text,
                "speaker": voice_type,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": 24000,
                    "enable_timestamp": True
                }
            }
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = session.post(api_url, json=request_json, headers=headers, timeout=30, stream=True)
                if resp.status_code != 200:
                    if attempt == max_retries - 1:
                        raise Exception(f"Volcengine TTS V3 API Error: {resp.text}")
                    time.sleep(2)
                    continue


                audio_data = bytearray()
                total_audio_size = 0
                for chunk in resp.iter_lines(decode_unicode=True):
                    if not chunk:
                        continue
                    data = json.loads(chunk)

                    if data.get("code", 0) == 0 and "data" in data and data["data"]:
                        chunk_audio = base64.b64decode(data["data"])
                        audio_size = len(chunk_audio)
                        total_audio_size += audio_size
                        audio_data.extend(chunk_audio)
                        continue
                    if data.get("code", 0) == 0 and "sentence" in data and data["sentence"]:
                        print("sentence_data:", data)
                        continue
                    if data.get("code", 0) == 20000000:
                        if 'usage' in data:
                            print("usage:", data['usage'])
                        break
                    if data.get("code", 0) > 0:
                        print(f"error response:{data}")
                        break

                if audio_data:
                    with open(output_file, "wb") as f:
                        f.write(audio_data)
                return output_file

            except (requests.exceptions.RequestException, ConnectionError) as e:
                logger.warning(f"TTS V3 Request failed (attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise e
                import random
                time.sleep(2 + attempt + random.random())

        raise Exception("Volcengine TTS V3 failed after retries")

    def _synthesize_v1_internal(self, text, voice_type, output_file, speed_ratio, cluster):
        """Internal helper for V1 TTS API.

        Sends a synchronous TTS request and decodes the base64-encoded
        audio response. Includes retry logic with exponential backoff.

        Args:
            text (str): Text content to synthesize.
            voice_type (str): Voice identifier.
            output_file (str): Path to save the MP3 output.
            speed_ratio (float): Speech speed multiplier.
            cluster (str): Volcengine TTS cluster name (e.g., "volcano_icl").

        Returns:
            str: Path to the output audio file.

        Raises:
            Exception: If all retry attempts fail.
        """
        if not self.appid or not self.token:
            raise Exception("VOLC_APPID or VOLC_ACCESS_TOKEN not configured.")

        api_url = "https://openspeech.bytedance.com/api/v1/tts"
        header = {"Authorization": f"Bearer;{self.token}", "Connection": "close"}

        request_json = {
            "app": {
                "appid": self.appid,
                "token": self.token,
                "cluster": cluster
            },
            "user": {
                "uid": "podcast_generator_user"
            },
            "audio": {
                "voice_type": voice_type,
                "encoding": "mp3",
                "speed_ratio": speed_ratio,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
                "frontend_type": "unitTson"
            }
        }

        # Add retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.post(api_url, json=request_json, headers=header, timeout=30)

                if resp.status_code != 200:
                    if attempt == max_retries - 1:
                        raise Exception(f"Volcengine TTS API Error: {resp.text}")
                    time.sleep(2)
                    continue

                resp_json = resp.json()
                if "data" not in resp_json:
                     if "message" in resp_json:
                         raise Exception(f"Volcengine TTS Error: {resp_json['message']}")
                     raise Exception(f"Unknown Volcengine response: {resp_json}")

                audio_data = base64.b64decode(resp_json["data"])
                with open(output_file, "wb") as f:
                    f.write(audio_data)
                return output_file

            except (requests.exceptions.RequestException, ConnectionError) as e:
                logger.warning(f"TTS Request failed (attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise e
                import random
                time.sleep(2 + attempt + random.random())

        raise Exception("Volcengine TTS failed after retries")

    def synthesize_speech(self, text, voice_type, output_file, speed_ratio=1.0):
        """Synthesize speech, automatically routing to the correct API.

        Detects whether the voice is a cloned voice (ID starts with "S_")
        and routes to the appropriate API:
        - Cloned voices -> V1 ICL API (``synthesize_cloned_tts``).
        - Standard voices -> V3 streaming API (``synthesize_standard_tts``).

        Args:
            text (str): Text content to synthesize.
            voice_type (str): Voice identifier. Cloned voices start with "S_".
            output_file (str): Path to save the generated MP3 file.
            speed_ratio (float): Speech speed multiplier. Defaults to 1.0.

        Returns:
            str: Path to the output audio file.
        """
        if voice_type.startswith("S_"):
            return self.synthesize_cloned_tts(text, voice_type, output_file, speed_ratio)
        else:
            return self.synthesize_standard_tts(text, voice_type, output_file, speed_ratio)
