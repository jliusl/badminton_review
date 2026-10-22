from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("BADMINTON_DATA_DIR", PROJECT_ROOT / "library"))
PROJECTS_DIR = DATA_DIR / "projects"
EXPORTS_DIR = DATA_DIR / "outputs"
DB_PATH = Path(os.getenv("BADMINTON_DB_PATH", DATA_DIR / "badminton.db"))
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def find_ffmpeg() -> str:
    configured = os.getenv("BADMINTON_FFMPEG")
    if configured:
        return configured
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = find_ffmpeg()
