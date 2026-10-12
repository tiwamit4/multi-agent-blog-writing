"""Run the existing Streamlit application from the repository root."""

from pathlib import Path
import runpy
import sys

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

if __name__ == "__main__":
    runpy.run_path(str(BACKEND_DIR / "bwa_frontend.py"), run_name="__main__")
