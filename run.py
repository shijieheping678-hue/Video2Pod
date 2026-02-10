"""Application launcher for the AI Video Podcast Generator.

Starts the Streamlit web application in headless mode with development
mode disabled. This is the recommended entry point for production use.

Usage:
    python run.py
"""

import subprocess
import sys
import os


def resolve_path(path):
    """Resolve a relative path to its absolute form.

    Args:
        path (str): Relative or absolute file path.

    Returns:
        str: The absolute path.
    """
    return os.path.abspath(path)

if __name__ == "__main__":
    app_path = resolve_path("app.py")

    # Construct the command: streamlit run app.py --server.headless=true
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        app_path,
        "--server.headless=true",
        "--global.developmentMode=false"
    ]

    print(f"Starting Streamlit app: {' '.join(cmd)}")

    try:
        # Run as a subprocess to ensure clean environment
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"Error launching Streamlit: {e}")
