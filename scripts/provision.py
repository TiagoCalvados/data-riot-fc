"""Provision alwaysdata using an account-scoped API token from .provision.env.

The token is never copied to the hosting server. Generated credentials travel to SSH
over stdin. Re-running preserves existing resources and existing secrets.
"""
from pathlib import Path
import json
import secrets
import ssl
import subprocess
import sys
import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from stage import HOST, OPTIONS

DB_NAME = 'datariotfc_kantine'
DB_USER = 'datariotfc_kantine'
DOMAIN = 'datariotfc.alwaysdata.net'
REMOTE = '/home/datariotfc/sdw-kantine'
STATE_FILE = ROOT / 'deployment-state.json'


def provision():
    config = dotenv_values(ROOT / '.provision.env')
    token = config.get('ALWAYSDATA_API_TOKEN')
    if not token or token == 'your-token':
        raise SystemExit('Missing ALWAYSDATA_API_TOKEN in .provision.env; no hosting settings changed.')
    saved = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    credentials_file = ROOT / 'test-credentials.txt'
    if credentials_file.exists():
        private = json.loads(credentials_file.read_text())
    else:
        private = {'admin_password': secrets.token_urlsafe(18), 'parent_password': secrets.token_urlsafe(18),
                   'db_password': secrets.token_urlsafe(32), 'secret_key': secrets.token_urlsafe(48)}
        credentials_file.write_text(json.dumps(private, indent=2), encoding='utf-8')
    with httpx.Client(base_url='https://api.alwaysdata.com/v1/', auth=(token + ' account=datariotfc', ''),
                      headers={'alwaysdata-synchronous':'yes'},
                      verify=ssl.create_default_context(), timeout=30) as client:
        def call(method, path, payload=None):
            result = client.request(method, path, json=payload)
            if result.status_code >= 400:
                # Error payloads may echo credentials. Only status + field names are reported.
                fields = []
                try:
                    body = result.json()
                    fields = list(body) if isinstance(body, dict) else []
                except ValueError:
                    pass
                raise SystemExit(f'alwaysdata API {method} {path}: HTTP {result.status_code}; fields: {fields}')
            if result.content:
                return result.json()
            return {'href': result.headers.get('Location')}

        def persist():
            STATE_FILE.write_text(json.dumps(saved, indent=2), encoding='utf-8')

        databases = call('GET', 'database/')
        existing_db = next((d for d in databases if d['name'] == DB_NAME and d['type'] == 'POSTGRESQL'), None)
        if not existing_db:
            existing_db = call('POST', 'database/', {'name': DB_NAME, 'type': 'POSTGRESQL', 'annotation': 'SDW kantineplanning'})
        saved['database'] = existing_db
        persist()
        users = call('GET', 'database/user/')
        existing_user = next((u for u in users if u['name'] == DB_USER and u['type'] == 'POSTGRESQL'), None)
        if not existing_user:
            existing_user = call('POST', 'database/user/', {'name': DB_USER, 'type': 'POSTGRESQL',
                'password': private['db_password'], 'require_ssl': True, 'permissions': {DB_NAME: 'FULL'},
                'annotation': 'SDW application only'})
        saved['database_user'] = existing_user
        persist()
        # Preserve all unrelated websites; update only the default account-domain site.
        sites = call('GET', 'site/')
        existing_site = next((s for s in sites if DOMAIN in [a.rstrip('/') for a in s.get('addresses', [])]), None)
        site_config = {'type': 'user_program', 'command': REMOTE + '/.venv/bin/python ' + REMOTE + '/scripts/start.py',
                       'working_directory': 'sdw-kantine', 'ssl_force': True,
                       'environment': 'PYTHON_VERSION=3.13', 'annotation': 'SDW kantineplanning', 'addresses': [DOMAIN]}
        environment = {'DATABASE_URL': f'postgresql+psycopg://{DB_USER}:{private["db_password"]}@postgresql-datariotfc.alwaysdata.net:5432/{DB_NAME}?sslmode=require',
            'SECRET_KEY': private['secret_key'], 'BASE_URL': 'https://' + DOMAIN, 'COOKIE_SECURE': 'true', 'DEMO_MODE': 'true'}
        for name in ['SMTP_HOST','SMTP_PORT','SMTP_USERNAME','SMTP_PASSWORD','SMTP_FROM','SPORTLINK_CLIENT_ID','SPORTLINK_CLUB_CODE']:
            if config.get(name):
                environment[name] = config[name]
        activation = {'environment': environment, 'credentials': {k:private[k] for k in ('admin_password','parent_password')}}
        subprocess.run(['ssh', *OPTIONS, HOST, REMOTE + '/.venv/bin/python ' + REMOTE + '/scripts/activate.py'],
                       input=json.dumps(activation), text=True, check=True)
        if existing_site:
            saved['previous_site'] = existing_site
            persist()
            path = f'site/{existing_site["id"]}/'
            # Keep any existing additional addresses.
            site_config['addresses'] = existing_site.get('addresses') or [DOMAIN]
            call('PATCH', path, site_config)
            saved['site_id'] = existing_site['id']
        else:
            created = call('POST', 'site/', site_config)
            saved['site_id'] = created.get('id')
        persist()
        jobs = call('GET', 'job/')
        command = REMOTE + '/.venv/bin/python ' + REMOTE + '/scripts/job.py'
        job = next((j for j in jobs if j.get('argument') == command), None)
        if not job:
            ssh_users = call('GET', 'ssh/')
            user = next(u for u in ssh_users if u['name'] == 'datariotfc')
            job = call('POST', 'job/', {'type':'TYPE_COMMAND', 'date_type':'CRONTAB', 'crontab_syntax':'*/10 * * * *',
                'argument':command,'working_directory':'sdw-kantine','ssh_user':user['id'],
                'environment':'PYTHON_VERSION=3.13','annotation':'SDW: invitation expiry, email delivery, fixture sync'})
        saved['job'] = job
        persist()
    print('Provisioned https://' + DOMAIN)
    print('Test credentials saved locally in test-credentials.txt (not uploaded as a file).')


if __name__ == '__main__':
    provision()
