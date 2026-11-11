"""Read-only dev checks; mutating response test is restricted to db/sdw_test."""
import os
import re
import time
from datetime import datetime, timezone, timedelta
import httpx
from sqlalchemy import select, func
from dev.common import require_local_database
from app.db import SessionLocal
from app.models import JobRun, Shift
from dev.mailcheck import inbox, check_webmail


def run(*, exercise_response=False):
    config = require_local_database(test_only=exercise_response)
    check_webmail('demo0@example.invalid')
    parent_messages = inbox('demo0@example.invalid')
    assert all('demo0@example.invalid' in str(message['To']) for message in parent_messages)
    with httpx.Client(base_url='http://app:8000', headers={'Origin': config.base_url}, timeout=10) as admin:
        assert admin.get('/health').json() == {'status': 'ok'}
        for language in ('nl', 'en'):
            assert f'<html lang="{language}">' in admin.get('/?lang='+language).text
        assert admin.get('/api/dashboard').status_code == 401
        response = admin.post('/api/login', json={'username': 'beheer.test', 'password': os.environ['LOCAL_ADMIN_PASSWORD']})
        response.raise_for_status()
        csrf = response.json()['csrf']
        assert 'Secure' not in response.headers.get('set-cookie', '')
        dashboard = admin.get('/api/dashboard').json()
        assert dashboard['demo_mode'] and dashboard['local_mail_capture']
        assert all(f['is_demo'] for f in dashboard['fixtures'])
        assert all(p['is_demo'] and p['email'].endswith('@example.invalid') for p in dashboard['parents'])
        last = dashboard['integrations']['last_job']
        assert last and datetime.now(timezone.utc)-datetime.fromisoformat(last['at']) < timedelta(minutes=2)
        assert admin.post('/api/admin/plan', json={}, headers={'X-CSRF-Token': csrf, 'Origin': 'http://example.invalid'}).status_code == 403
        with httpx.Client(base_url='http://app:8000', headers={'Origin': config.base_url}, timeout=10) as parent:
            response = parent.post('/api/login', json={'username': 'ouder.test', 'password': os.environ['LOCAL_PARENT_PASSWORD']})
            response.raise_for_status()
            parent_csrf = response.json()['csrf']
            assert parent.get('/api/admin/analytics').status_code == 403
            own = parent.get('/api/dashboard').json()
            assert all(i['user_id'] == own['user']['id'] for s in own['shifts'] for i in s['invitations'])
            if exercise_response:
                with httpx.Client(base_url='http://mailpit:8025', timeout=10) as mail:
                    messages = mail.get('/api/v1/messages').json()['messages']
                    pending = {i['id'] for s in own['shifts'] for i in s['invitations'] if i['state'] == 'pending'}
                    chosen = None
                    for summary in messages:
                        if not any(recipient['Address'] == 'demo0@example.invalid' for recipient in summary['To']):
                            continue
                        message = mail.get('/api/v1/message/'+summary['ID']).json()
                        match = re.search(r'invitation=([A-Za-z0-9_-]+)', message['Text'])
                        if not match:
                            continue
                        lookup = parent.get('/api/invitations/by-token/'+match[1])
                        if lookup.status_code == 200 and lookup.json()['id'] in pending:
                            chosen = lookup.json()['id']
                            break
                    assert chosen is not None, 'No pending captured invitation for ouder.test'
                    assert any(match[1] in message.get_body(preferencelist=('plain',)).get_content()
                               for message in parent_messages), 'Invitation absent from the parent IMAP mailbox'
                    assert not any(match[1] in message.get_body(preferencelist=('plain',)).get_content()
                                   for message in inbox('demo1@example.invalid')), 'Mailbox isolation failed'
                    assert parent.post(f'/api/invitations/{chosen}/respond', json={'decision': 'confirmed'},
                                       headers={'X-CSRF-Token': parent_csrf}).status_code == 200
                    after = parent.get('/api/dashboard').json()
                    assert any(i['id'] == chosen and i['state'] == 'confirmed' for s in after['shifts'] for i in s['invitations'])
                print('SMTP delivery, private IMAP inbox, Roundcube login, invitation link and explicit response passed')
            assert parent.post('/api/logout', json={}, headers={'X-CSRF-Token': parent_csrf}).status_code == 200
        assert admin.post('/api/logout', json={}, headers={'X-CSRF-Token': csrf}).status_code == 200
    if exercise_response:
        with SessionLocal() as db:
            before = list(db.execute(select(Shift.id, Shift.starts_at, Shift.ends_at).order_by(Shift.id)))
            last_id = db.scalar(select(func.max(JobRun.id)))
        for _ in range(30):
            time.sleep(1)
            with SessionLocal() as db:
                if db.scalar(select(func.max(JobRun.id))) > last_id:
                    assert list(db.execute(select(Shift.id, Shift.starts_at, Shift.ends_at).order_by(Shift.id))) == before
                    break
        else:
            raise AssertionError('The independent worker did not advance its heartbeat')
        print('Independent PostgreSQL worker heartbeat advanced; shift identities/times preserved')
    print('Local HTTP, languages, logins, cookies, origins, privacy and scheduler checks passed')


if __name__ == '__main__':
    run()
