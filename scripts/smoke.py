"""Read-only HTTP smoke checks against local or deployed installation."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import ssl
import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('base', nargs='?', default='http://127.0.0.1:8000')
parser.add_argument('--require-scheduler', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
base = args.base
creds = json.loads((root / 'test-credentials.txt').read_text())
with httpx.Client(base_url=base, verify=ssl.create_default_context(), timeout=30) as client:
    assert client.get('/health').json() == {'status':'ok'}
    homepage = client.get('/')
    assert homepage.status_code == 200 and 'SDW' in homepage.text
    for asset in ['/static/app.js','/static/app.en.js','/static/style.css','/static/mark.svg',
                  '/static/manifest.webmanifest','/static/icons/icon-192.png',
                  '/static/icons/icon-512.png','/static/icons/apple-touch-icon.png',
                  '/static/icons/maskable-512.png','/static/branding/sdw-logo.jpg','/static/branding/sdw-favicon.ico']:
        result=client.get(asset)
        assert result.status_code == 200
        assert hashlib.sha256(result.content).digest() == hashlib.sha256((root/'app'/asset.lstrip('/')).read_bytes()).digest(), asset
    for language in ('en','nl'):
        result=client.get('/?lang='+language)
        assert f'<html lang="{language}">' in result.text
        assert 'mobile-navigation' in result.text and 'manifest.webmanifest' in result.text
        assert 'Data Riot FC' not in result.text and 'DATA RIOT FC' not in result.text
        assert 'property="og:site_name" content="SDW Kantine"' in result.text
        assert 'https://datariotfc.alwaysdata.net/static/branding/sdw-logo.jpg?v=sdw-20261105' in result.text
    print('Dutch/English mobile pages, install manifest, icons and source integrity verified')
    assert client.get('/api/dashboard').status_code == 401
    for username, key, role in [('beheer.test','admin_password','admin'),('ouder.test','parent_password','parent')]:
        response = client.post('/api/login', json={'username':username,'password':creds[key]})
        assert response.status_code == 200, f'{role} login: {response.status_code}'
        csrf = response.json()['csrf']
        assert response.json()['user']['role'] == role
        result = client.get('/api/dashboard')
        assert result.status_code == 200
        data = result.json()
        assert ('parents' in data) == (role == 'admin')
        assert 'password_hash' not in result.text
        analytics=client.get('/api/admin/analytics')
        assert analytics.status_code==(200 if role=='admin' else 403)
        assert 'visitor_hash' not in analytics.text
        if role == 'admin' and args.require_scheduler:
            job=data['integrations']['last_job']
            assert job and job['state']=='success', 'No successful worker heartbeat'
            age=datetime.now(timezone.utc)-datetime.fromisoformat(job['at'])
            assert timedelta(0)<=age<timedelta(minutes=30), 'Worker heartbeat is stale'
            print('Automatic scheduler verified:', job['at'])
        if role == 'parent':
            assert client.post('/api/admin/plan',headers={'X-CSRF-Token':csrf},json={}).status_code==403
            assert all(i['user_id']==data['user']['id'] for s in data['shifts'] for i in s['invitations'])
        assert client.post('/api/logout',headers={'X-CSRF-Token':csrf},json={}).status_code==200
        assert client.get('/api/me').status_code==401
        print(f'{role}: login, dashboard, privacy, and logout verified; {len(data["shifts"])} visible shifts')
print('HTTP checks passed for',base)
