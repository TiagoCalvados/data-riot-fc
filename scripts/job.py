import os
import sys
from pathlib import Path

os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, str(Path.cwd()))
from app.db import SessionLocal
from app.jobs import run_job

with SessionLocal() as db:
    print(run_job(db))
