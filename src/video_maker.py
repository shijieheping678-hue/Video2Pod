"""Video rendering and composition module.

Provides functionality for:
- Extracting audio from video files using FFmpeg.
- Creating podcast videos by combining static images with audio and subtitles.
- Rendering animated videos using Remotion (React-based video framework).
- Serving local files via HTTP for Remotion asset access.
"""

import ffmpeg
import os
import json
import subprocess
import threading
import http.server
import socketserver
import time
from src.utils import logger, ensure_dir

# --- Static File Server for Remotion ---
PORT = 8000
SERVER_URL = f"http://127.0.0.1:{PORT}"
server_thread = None

def start_static_server():
    """Start a local HTTP server to serve project files for Remotion rendering.

    Launches a background daemon thread running a simple HTTP server on port 8000.
    The server serves files from the current working directory, allowing Remotion
    to access audio, image, and JSON assets via ``http://127.0.0.1:8000/``.

    If the server is already running (thread alive) or the port is occupied,
    the function returns silently without starting a duplicate.
    """
    global server_thread
    if server_thread and server_thread.is_alive():
        return

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass # Suppress logs

    def run_server():
        try:
            # Allow address reuse to prevent "Address already in use" errors on reload
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
                logger.info(f"Serving static files at {SERVER_URL}")
                httpd.serve_forever()
        except OSError as e:
            logger.warning(f"Port {PORT} likely in use ({e}). Assuming static server is already running.")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1) # Give it a moment to start

def to_local_url(abs_path):
    """Convert an absolute file path to a localhost HTTP URL.

    Computes the relative path from the current working directory and
    constructs an HTTP URL served by the local static server. Ensures
    the static server is started before generating the URL.

    Args:
        abs_path (str): Absolute path to a local file.

    Returns:
        str: HTTP URL pointing to the file (e.g., ``http://127.0.0.1:8000/temp/audio.mp3``).
            Falls back to a ``file:///`` URL if the path is outside the project root.
    """
    # Ensure server is started
    start_static_server()

    # Assume abs_path is within project root
    # Get relative path from current working directory
    try:
        rel_path = os.path.relpath(abs_path, os.getcwd())
        # Replace backslashes for URL
        url_path = rel_path.replace("\\", "/")
        return f"{SERVER_URL}/{url_path}"
    except ValueError:
        logger.warning(f"Path {abs_path} is not within project root. Using file:// might fail.")
        return f"file:///{abs_path.replace('\\', '/')}"

# --- Existing FFmpeg Functions ---

def extract_audio(video_path, output_audio_path):
    """Extract audio track from a video file using FFmpeg.

    Converts the audio to MP3 format at 192kbps bitrate.

    Args:
        video_path (str): Path to the input video file.
        output_audio_path (str): Path to save the extracted MP3 audio.

    Returns:
        str: Path to the output audio file.

    Raises:
        ffmpeg.Error: If FFmpeg fails to extract the audio.
    """
    logger.info(f"Extracting audio from {video_path}...")
    try:
        (
            ffmpeg
            .input(video_path)
            .output(output_audio_path, acodec='mp3', audio_bitrate='192k')
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Audio extracted to: {output_audio_path}")
        return output_audio_path
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg extract error: {e.stderr.decode('utf8')}")
        raise e

def create_podcast_video(image_path, audio_path, output_video_path, subtitle_path=None):
    """Create a podcast video by combining a static image with audio using FFmpeg.

    Generates an H.264/AAC MP4 video from a background image and audio track.
    Optionally burns SRT subtitles directly into the video.

    Args:
        image_path (str): Path to the background image (JPG/PNG). 16:9 recommended.
        audio_path (str): Path to the podcast audio file (MP3).
        output_video_path (str): Path to save the output MP4 video.
        subtitle_path (str, optional): Path to an SRT subtitle file to burn
            into the video. If None or file doesn't exist, no subtitles are added.

    Returns:
        str: Path to the created video file.

    Raises:
        ffmpeg.Error: If FFmpeg fails during video creation.
    """
    logger.info(f"Creating video: {output_video_path}")
    try:
        input_image = ffmpeg.input(image_path, loop=1)
        input_audio = ffmpeg.input(audio_path)

        output_args = {
            'vcodec': 'libx264',
            'acodec': 'aac',
            'pix_fmt': 'yuv420p',
            'r': 25, # Use standard framerate to ensure subtitles render smoothly
            'shortest': None
        }

        if subtitle_path and os.path.exists(subtitle_path):
            logger.info(f"Burning subtitles from: {subtitle_path}")
            # Ensure path uses forward slashes for FFmpeg filter compatibility on Windows
            sub_path_fixed = subtitle_path.replace('\\', '/').replace(':', '\\:')

            # Since we need to apply a filter to the video stream 'input_image':
            video_stream = input_image.filter('subtitles', subtitle_path)

            # Combine
            out = ffmpeg.output(
                video_stream,
                input_audio,
                output_video_path,
                **output_args
            )
        else:
            out = ffmpeg.output(
                input_image,
                input_audio,
                output_video_path,
                **output_args
            )

        (
            out
            .global_args('-shortest')
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Video created successfully: {output_video_path}")
        return output_video_path
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg merge error: {e.stderr.decode('utf8')}")
        raise e

def render_remotion_video(audio_path, image_path, json_path, output_path):
    """Render an animated podcast video using the Remotion framework.

    Workflow:
    1. Start a local HTTP server for asset access.
    2. Load caption data from JSON and convert file paths to HTTP URLs.
    3. Invoke the Remotion CLI to render the video composition.
    4. Re-encode the output with FFmpeg for broad compatibility
       (H.264 Main Profile, yuv420p, AAC, faststart).

    Args:
        audio_path (str): Path to the podcast audio file.
        image_path (str): Path to the background image.
        json_path (str): Path to the Remotion caption JSON file (generated
            by ``generate_dialogue_audio``). Must contain ``captions`` and
            ``durationInSeconds`` fields.
        output_path (str): Path to save the final MP4 video.

    Returns:
        str: Path to the rendered and re-encoded video file.

    Raises:
        Exception: If Remotion rendering or FFmpeg re-encoding fails.
    """
    logger.info(f"Starting Remotion render: {output_path}")

    # 0. Start local server
    start_static_server()

    # 1. Prepare Input Props
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Convert absolute paths to HTTP URLs
    input_props = {
        "audioUrl": to_local_url(os.path.abspath(audio_path)),
        "bgImage": to_local_url(os.path.abspath(image_path)) if image_path else "",
        "captions": data['captions'],
        "durationInSeconds": data['durationInSeconds']
    }

    # Save a temporary input file for CLI
    props_file = os.path.abspath("temp/remotion_props.json")
    with open(props_file, "w", encoding="utf-8") as f:
        json.dump(input_props, f, ensure_ascii=False)

    # 2. Run Remotion CLI
    ensure_dir(os.path.dirname(output_path))

    # Try to find local Chrome if possible (optional optimization)
    # common_chrome = [
    #     r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    #     r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    # ]
    # browser_path = next((p for p in common_chrome if os.path.exists(p)), None)

    cmd = [
        "npx", "remotion", "render",
        "src/index.tsx",
        "MyComp",
        os.path.abspath(output_path),
        f"--props={props_file}",
        "--overwrite",
        "--log=verbose",
        "--concurrency=6" # Reduce load
    ]

    # If you want to force local chrome, uncomment below:
    # if browser_path:
    #     cmd.extend(["--browser-executable", browser_path])

    # On Windows, npx might need shell=True
    use_shell = os.name == 'nt'

    try:
        logger.info(f"Running command in remotion-video/: {' '.join(cmd)}")
        process = subprocess.run(
            cmd,
            cwd="remotion-video",
            capture_output=True,
            text=True,
            shell=use_shell
        )

        if process.returncode != 0:
            logger.error(f"Remotion Error: {process.stderr}")
            raise Exception(f"Remotion render failed: {process.stderr}")

        logger.info(f"Remotion render success: {process.stdout}")

        # --- Post-processing: Re-encode with FFmpeg for compatibility ---
        # Remotion might output High Profile or other settings not friendly to all players (e.g. Windows Media Player, WeChat)
        # We enforce H.264 Main Profile + yuv420p + AAC

        temp_remotion_output = output_path + ".temp.mp4"

        # Rename original output to temp
        if os.path.exists(output_path):
            if os.path.exists(temp_remotion_output):
                os.remove(temp_remotion_output)
            os.rename(output_path, temp_remotion_output)

        logger.info(f"Re-encoding Remotion output for compatibility: {output_path}")
        try:
            (
                ffmpeg
                .input(temp_remotion_output)
                .output(
                    output_path,
                    vcodec='libx264',
                    acodec='aac',
                    pix_fmt='yuv420p',
                    # movflags=+faststart moves metadata to front for web streaming
                    movflags='+faststart'
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            # Clean up temp file
            os.remove(temp_remotion_output)
            logger.info("Re-encoding successful.")
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg re-encode error: {e.stderr.decode('utf8')}")
            # If re-encode fails, try to restore original
            if os.path.exists(temp_remotion_output):
                os.rename(temp_remotion_output, output_path)
            raise e

        return output_path

    except Exception as e:
        logger.error(f"Remotion execution failed: {str(e)}")
        raise e
