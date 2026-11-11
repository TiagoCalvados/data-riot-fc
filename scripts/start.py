"""Alwaysdata User program entrypoint; IPv6 address and port are provided by hosting."""
import os
import sys
from pathlib import Path
import uvicorn

os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, str(Path.cwd()))
uvicorn.run('app.main:app', host=os.environ.get('IP', '::'), port=int(os.environ.get('PORT', '8000')),
            proxy_headers=True, forwarded_allow_ips=os.environ.get('TRUSTED_PROXIES', '127.0.0.1,::1'),
            access_log=False, workers=1)
