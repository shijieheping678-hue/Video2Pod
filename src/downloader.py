"""Video downloader module using yt-dlp.

Supports downloading videos from platforms like Bilibili and YouTube.
Downloaded files are saved in MP4 format by default.
"""

import yt_dlp
import os
from src.utils import logger


def download_video(url, output_dir="temp"):
    """Download a video from a given URL using yt-dlp.

    Supports multiple platforms including Bilibili and YouTube.
    The video is saved in MP4 format when available, falling back
    to the best available format otherwise.

    Args:
        url (str): The video URL to download (e.g., Bilibili or YouTube link).
        output_dir (str): Directory to save the downloaded file. Defaults to "temp".
            The directory will be created if it does not exist.

    Returns:
        str: Absolute path to the downloaded video file.

    Raises:
        Exception: If the download fails due to network errors, invalid URL,
            or unsupported platform.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    ydl_opts = {
        'format': 'best[ext=mp4]/best',  # Prefer MP4
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        logger.info(f"Starting download for URL: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            logger.info(f"Download completed: {filename}")
            return filename
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        raise e
