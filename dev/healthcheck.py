"""Dependency-free container readiness probes."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.request import urlopen


def main():
    if sys.argv[1] in ('app', 'gateway'):
        with urlopen('http://127.0.0.1:8000/health', timeout=3) as response:
            assert json.load(response) == {'status': 'ok'}
        if sys.argv[1] == 'gateway':
            with urlopen('http://127.0.0.1:8025/readyz', timeout=3) as response:
                assert response.status == 200
            with urlopen('http://127.0.0.1:8080/', timeout=3) as response:
                assert response.status == 200
    else:
        last = datetime.fromisoformat(Path('/tmp/sdw-worker-heartbeat').read_text())
        age = (datetime.now(timezone.utc)-last).total_seconds()
        assert 0 <= age <= max(60, 2*int(os.environ.get('WORKER_INTERVAL_SECONDS', '30'))+15)


if __name__ == '__main__':
    main()
