"""Task (project) management module for podcast generation workflows.

Provides persistent task storage using a directory-based structure where
each task has its own folder containing a ``state.json`` file and all
associated media files (video, audio, scripts, etc.).
"""

import os
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from src.utils import logger, ensure_dir

TASKS_DIR = "tasks"


class TaskManager:
    """File-system based task manager for podcast generation projects.

    Each task is stored as a directory under the tasks root folder, containing
    a ``state.json`` file that tracks task metadata, processing status, file
    references, and text data (transcript, script).

    Directory structure example::

        tasks/
        └── 20260210_143000_MyPodcast/
            ├── state.json
            ├── original_video.mp4
            ├── audio.mp3
            ├── podcast_audio.mp3
            └── temp/segments/...

    Attributes:
        tasks_dir (str): Root directory for all task folders.
    """

    def __init__(self, tasks_dir=TASKS_DIR):
        """Initialize the TaskManager and ensure the tasks directory exists.

        Args:
            tasks_dir (str): Root directory path for storing tasks.
                Defaults to "tasks".
        """
        self.tasks_dir = tasks_dir
        ensure_dir(self.tasks_dir)

    def create_task(self, name="New Task"):
        """Create a new task with an initialized directory and state file.

        Generates a unique task ID from the current timestamp and sanitized
        task name, creates the task directory, and writes an initial
        ``state.json`` with empty file references and data fields.

        Args:
            name (str): Human-readable task name. Special characters are
                sanitized and spaces are replaced with underscores.
                Defaults to "New Task".

        Returns:
            str: The generated task ID (format: ``YYYYMMDD_HHMMSS_SafeName``).
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize name
        safe_name = "".join([c for c in name if c.isalnum() or c in (' ', '-', '_', '.')]).strip().replace(' ', '_')
        if not safe_name:
            safe_name = "Untitled"

        task_id = f"{timestamp}_{safe_name}"

        task_path = os.path.join(self.tasks_dir, task_id)
        ensure_dir(task_path)

        # Initialize empty state
        initial_state = {
            "id": task_id,
            "name": name,
            "created_at": timestamp,
            "status": "created", # created, processing, completed, failed
            "current_step": 0,   # 0: start, 1: video_ready, 2: transcript_ready, 3: script_ready, 4: audio_ready, 5: video_done
            "files": {
                "original_video": None,
                "audio": None,
                "transcript": None,
                "script": None,
                "podcast_audio": None,
                "final_video": None
            },
            "data": {
                "transcript_text": None,
                "script_content": None
            }
        }

        self.save_task_state(task_id, initial_state)
        logger.info(f"Created new task: {task_id}")
        return task_id

    def get_task_dir(self, task_id):
        """Get the absolute directory path for a given task.

        Args:
            task_id (str): The task identifier (directory name).

        Returns:
            str: Full path to the task's directory.
        """
        return os.path.join(self.tasks_dir, task_id)

    def save_task_state(self, task_id, state):
        """Save a task's state dictionary to its ``state.json`` file.

        Args:
            task_id (str): The task identifier.
            state (dict): Complete task state dictionary to persist.
        """
        task_dir = self.get_task_dir(task_id)
        state_path = os.path.join(task_dir, "state.json")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def load_task(self, task_id):
        """Load a task's state from its ``state.json`` file.

        Args:
            task_id (str): The task identifier.

        Returns:
            dict | None: The task state dictionary, or None if the state
                file does not exist.
        """
        task_dir = self.get_task_dir(task_id)
        state_path = os.path.join(task_dir, "state.json")

        if not os.path.exists(state_path):
            return None

        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_tasks(self):
        """List all tasks sorted by creation time (newest first).

        Scans the tasks directory for subdirectories containing valid
        ``state.json`` files.

        Returns:
            list[dict]: List of task state dictionaries, sorted by
                ``created_at`` in descending order. Returns an empty
                list if no tasks exist.
        """
        tasks = []
        if not os.path.exists(self.tasks_dir):
            return []

        for dirname in os.listdir(self.tasks_dir):
            dirpath = os.path.join(self.tasks_dir, dirname)
            if os.path.isdir(dirpath):
                state = self.load_task(dirname)
                if state:
                    tasks.append(state)

        # Sort by timestamp (descending)
        tasks.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return tasks

    def update_task_file(self, task_id, file_key, source_path, move=False):
        """Copy or move a file into the task directory and update the state.

        Includes retry logic (up to 3 attempts) for Windows file locking issues.

        Args:
            task_id (str): The task identifier.
            file_key (str): The state file key to update. One of:
                "original_video", "audio", "transcript", "script",
                "podcast_audio", "final_video".
            source_path (str): Path to the source file to copy/move.
            move (bool): If True, moves the file instead of copying.
                Defaults to False (copy).

        Returns:
            str | None: Path to the file in the task directory on success,
                or None if the task state could not be loaded.

        Raises:
            PermissionError: If the file remains locked after all retries.
            Exception: If the file operation fails for other reasons.
        """
        state = self.load_task(task_id)
        if not state:
            return None

        task_dir = self.get_task_dir(task_id)
        filename = os.path.basename(source_path)
        dest_path = os.path.join(task_dir, filename)

        # Retry logic for Windows file locking issues
        max_retries = 3
        for i in range(max_retries):
            try:
                if move:
                    shutil.move(source_path, dest_path)
                else:
                    shutil.copy2(source_path, dest_path)
                break # Success
            except PermissionError as e:
                if i == max_retries - 1:
                    logger.error(f"Failed to move/copy file after {max_retries} retries: {e}")
                    raise e
                logger.warning(f"File locked, retrying in 1s... ({i+1}/{max_retries})")
                time.sleep(1)
            except Exception as e:
                logger.error(f"File operation failed: {e}")
                raise e

        state["files"][file_key] = filename # Store relative path
        self.save_task_state(task_id, state)
        return dest_path

    def update_task_data(self, task_id, data_key, content):
        """Update a text data field in the task state.

        Args:
            task_id (str): The task identifier.
            data_key (str): The data field key to update. One of:
                "transcript_text", "script_content".
            content (str): The text content to store.
        """
        state = self.load_task(task_id)
        if state:
            state["data"][data_key] = content
            self.save_task_state(task_id, state)

    def delete_task(self, task_id):
        """Delete a task and all its associated files.

        Removes the entire task directory recursively. This operation
        is irreversible.

        Args:
            task_id (str): The task identifier to delete.
        """
        task_dir = self.get_task_dir(task_id)
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir)
            logger.info(f"Deleted task: {task_id}")
