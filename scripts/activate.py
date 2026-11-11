"""Server activation. Receives deployment secrets exclusively through stdin."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path('/home/datariotfc/sdw-kantine')
os.chdir(root)
os.umask(0o077)
config = json.load(sys.stdin)
env_file = root / '.env'
if env_file.exists():
    print('Existing server configuration retained; running migrations only.')
else:
    # JSON quoted strings are supported by python-dotenv; never interpolate values into shell code.
    lines = [f'{key}={json.dumps(str(value))}' for key, value in config['environment'].items()]
    env_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    env_file.chmod(0o600)
python = str(root / '.venv/bin/python')
subprocess.run([python, '-m', 'alembic', 'upgrade', 'head'], check=True)
subprocess.run([python, '-m', 'app.seed'], input=json.dumps(config['credentials']), text=True, check=True)
subprocess.run([python, 'scripts/job.py'], check=True)
print('Database migrations, seed, and first scheduled job completed.')
