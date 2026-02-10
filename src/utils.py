"""Utility functions for the Podcast Generator application.

Provides common helpers used across all modules, including logging setup,
directory management, and file path manipulation.
"""

import os
import logging
from pathlib import Path


def setup_logging():
    """Configure and initialize the application-wide logger.

    Sets up a logger named "PodcastGenerator" with both file and console output.
    Log messages are formatted with timestamp, logger name, level, and message.

    Returns:
        logging.Logger: Configured logger instance for the application.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("app.log"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("PodcastGenerator")


def ensure_dir(directory):
    """Ensure that a directory exists, creating it and any parents if necessary.

    Args:
        directory (str): Path to the directory to create. Can be absolute or relative.
    """
    Path(directory).mkdir(parents=True, exist_ok=True)


def get_filename_from_path(path):
    """Extract the filename without its extension from a file path.

    Args:
        path (str): Full or relative file path.

    Returns:
        str: The stem (filename without extension) of the given path.

    Examples:
        >>> get_filename_from_path("/tmp/video.mp4")
        'video'
        >>> get_filename_from_path("podcast_audio.mp3")
        'podcast_audio'
    """
    return Path(path).stem


logger = setup_logging()
