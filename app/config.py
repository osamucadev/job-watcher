from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "Job Watcher"
APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
DATA_DIR = Path(os.getenv("JOB_WATCHER_DATA_DIR", PROJECT_DIR / "data"))
DATABASE_PATH = Path(os.getenv("JOB_WATCHER_DATABASE", DATA_DIR / "job-watcher.db"))
TIMEZONE = os.getenv("JOB_WATCHER_TIMEZONE", "America/Sao_Paulo")
SCHEDULE_HOURS = (9, 12, 15, 18)
PAGE_SIZE = 20

