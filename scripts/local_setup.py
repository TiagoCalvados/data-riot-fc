"""Prepare an isolated local demo with randomly generated test credentials."""
from pathlib import Path
import json
import os
import secrets
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
os.chdir(root)
credentials_file = root / 'test-credentials.txt'
if credentials_file.exists():
    private = json.loads(credentials_file.read_text())
else:
    private = {'admin_password': secrets.token_urlsafe(18), 'parent_password': secrets.token_urlsafe(18),
               'db_password': secrets.token_urlsafe(32), 'secret_key': secrets.token_urlsafe(48)}
    credentials_file.write_text(json.dumps(private, indent=2), encoding='utf-8')
if not (root / '.env').exists():
    (root / '.env').write_text('DATABASE_URL=sqlite:///./development.db\nSECRET_KEY=' + private['secret_key'] +
                             '\nBASE_URL=http://127.0.0.1:8000\nCOOKIE_SECURE=false\nDEMO_MODE=true\n', encoding='utf-8')
subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], check=True)
subprocess.run([sys.executable, '-m', 'app.seed'], input=json.dumps(private), text=True, check=True)
subprocess.run([sys.executable, 'scripts/job.py'], check=True)
print('Local demo ready. Usernames: beheer.test / ouder.test. Passwords are in ignored test-credentials.txt.')
