"""Initialize the existing alwaysdata database after its user is provisioned.

Requires authorization to store the app database password in private server config.
Secrets are read from the ignored local credential file and sent only over SSH stdin.
"""
import json
from pathlib import Path
import subprocess
from stage import ROOT, HOST, OPTIONS


def activate():
    credentials = json.loads((ROOT / 'test-credentials.txt').read_text(encoding='utf-8'))
    environment = {
        'DATABASE_URL': 'postgresql+psycopg://datariotfc_kantine:' + credentials['db_password']
                        + '@postgresql-datariotfc.alwaysdata.net:5432/datariotfc_kantine?sslmode=require',
        'SECRET_KEY': credentials['secret_key'],
        'BASE_URL': 'https://datariotfc.alwaysdata.net',
        'COOKIE_SECURE': 'true',
        'DEMO_MODE': 'true',
    }
    activation = {'environment': environment,
                  'credentials': {k: credentials[k] for k in ('admin_password', 'parent_password')}}
    subprocess.run(['ssh', *OPTIONS, HOST,
                    '/home/datariotfc/sdw-kantine/.venv/bin/python /home/datariotfc/sdw-kantine/scripts/activate.py'],
                   input=json.dumps(activation), text=True, check=True)


if __name__ == '__main__':
    activate()
