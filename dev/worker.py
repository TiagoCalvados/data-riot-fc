"""Container scheduler with graceful shutdown and a successful-job heartbeat."""
import json
import os
from pathlib import Path
import signal
import threading
from datetime import datetime, timezone
from dev.common import require_local_database
from app.db import SessionLocal
from app.jobs import run_job

HEARTBEAT = Path('/tmp/sdw-worker-heartbeat')


def main():
    require_local_database()
    interval = max(2, int(os.environ.get('WORKER_INTERVAL_SECONDS', '30')))
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                result = run_job(db)
            HEARTBEAT.write_text(datetime.now(timezone.utc).isoformat())
            print(json.dumps({'worker': 'success', **result}), flush=True)
        except Exception as exc:
            # DB errors may embed connection credentials; do not log their bodies.
            print('Local worker failed: '+type(exc).__name__, flush=True)
        stop.wait(interval)


if __name__ == '__main__':
    main()
