from datetime import timedelta
import importlib.util
from pathlib import Path
import re
import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import select, func
from app.config import Settings, settings
from app.models import Invitation, Outbox, User, Fixture, Shift, aware, utcnow
from app.mailer import deliver_outbox
from app.planning import fill_shift

ROOT = Path(__file__).resolve().parents[1]


def local_settings(**overrides):
    values = dict(secret_key='isolated-test-secret-at-least-32-characters',
                  database_url='sqlite://', base_url='http://127.0.0.1:8000',
                  cookie_secure=False, demo_mode=True, local_mail_capture=True,
                  smtp_host='mailpit', smtp_port=1025, smtp_from='kantine@example.invalid',
                  smtp_username='', smtp_password='')
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize('override', [
    {'demo_mode': False, 'database_url': 'postgresql+psycopg://user:pass@db/test'},
    {'cookie_secure': True}, {'base_url': 'https://datariotfc.alwaysdata.net'},
    {'base_url': 'http://example.org'}, {'smtp_host': 'smtp.example.org'},
    {'smtp_port': 587}, {'smtp_username': 'real-user'}, {'smtp_password': 'real-password'},
    {'smtp_from': 'sender@example.org'},
])
def test_capture_mode_refuses_production_or_external_delivery(override):
    with pytest.raises(ValidationError):
        local_settings(**override)


def test_local_capture_delivers_only_fake_mail_and_preserves_reply_contract(db, users, monkeypatch):
    from test_system import fixture, shift
    for key, value in local_settings().model_dump().items():
        if key != 'database_url':
            monkeypatch.setattr(settings(), key, value)
    s = shift(db, fixture(db))
    fill_shift(db, s)
    messages = []

    class CaptureSMTP:
        def __init__(self, host, port, **kwargs):
            assert (host, port) == ('mailpit', 1025)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, **kwargs): raise AssertionError('Capture must not use production SMTP')
        def login(self, *args): raise AssertionError('Capture must not use real credentials')
        def send_message(self, message): messages.append(message)

    assert deliver_outbox(db, smtp_factory=CaptureSMTP) == 1
    invite = db.scalar(select(Invitation))
    outbox = db.scalar(select(Outbox))
    assert messages[0]['To'] == 'parent1@example.invalid'
    assert 'http://127.0.0.1:8000/?lang=nl&invitation=' in messages[0].get_content()
    assert invite.state == 'pending' and invite.sent_at and invite.expires_at
    assert aware(invite.expires_at)-aware(invite.sent_at) <= timedelta(hours=48)
    assert outbox.state == 'simulated' and outbox.encrypted_payload == ''


def test_capture_mode_rejects_real_recipient_even_on_a_demo_shift(db, users, monkeypatch):
    from test_system import fixture, shift
    for key, value in local_settings().model_dump().items():
        if key != 'database_url':
            monkeypatch.setattr(settings(), key, value)
    db.get(User, 1).email = 'real-parent@example.org'
    fill_shift(db, shift(db, fixture(db)))
    def forbidden(*args, **kwargs): raise AssertionError('Must not open SMTP')
    assert deliver_outbox(db, smtp_factory=forbidden) == 0
    assert db.scalar(select(Invitation)).state == 'queued'
    assert db.scalar(select(Invitation)).expires_at is None
    assert 'testinbox' in db.scalar(select(Outbox)).error


def test_fictional_seed_is_repeatable_without_resetting_accounts(db, monkeypatch):
    from app.seed import seed
    from app.db import Base
    from app.security import verify_password
    # The fixture's base club/policy is removed only from this in-memory test DB.
    assert db.bind.dialect.name == 'sqlite'
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    monkeypatch.setattr(settings(), 'local_mail_capture', False)
    assert seed(db, 'local-admin-password!', 'local-parent-password!')['state'] == 'demo_initialized'
    before = tuple(db.scalar(select(func.count()).select_from(model)) for model in (User, Fixture, Shift, Invitation))
    assert seed(db, 'different-admin-password!', 'different-parent-password!') == {'state': 'already_initialized'}
    assert before == tuple(db.scalar(select(func.count()).select_from(model)) for model in (User, Fixture, Shift, Invitation))
    parent = db.scalar(select(User).where(User.username == 'ouder.test'))
    assert verify_password(parent.password_hash, 'local-parent-password!')


def test_compose_separates_persistent_dev_from_disposable_tests():
    base = yaml.safe_load((ROOT/'compose.yaml').read_text())
    local = yaml.safe_load((ROOT/'compose.local.yaml').read_text())
    test = yaml.safe_load((ROOT/'compose.test.yaml').read_text())
    assert base['services']['bootstrap']['depends_on']['db']['condition'] == 'service_healthy'
    assert base['services']['app']['depends_on']['bootstrap']['condition'] == 'service_completed_successfully'
    assert base['services']['worker']['command'] == ['python', '-m', 'dev.worker']
    assert base['services']['app']['environment']['LOCAL_MAIL_CAPTURE'] == 'true'
    assert base['services']['app']['environment']['SPORTLINK_CLIENT_ID'] == ''
    assert base['networks']['local']['internal'] is True
    assert 'volumes' not in base['services']['db'] and 'ports' not in base['services']['app']
    assert local['services']['db']['volumes'] == ['postgres_data:/var/lib/postgresql/data']
    gateway = local['services']['gateway']
    assert all(port.startswith('127.0.0.1:') for port in gateway['ports'])
    assert set(gateway['networks']) == {'local', 'host_access'}
    assert local['networks']['host_access'] == {}
    assert all('ports' not in local['services'].get(name, {}) for name in ('app', 'mailpit', 'db'))
    assert all(service.get('networks') == ['local'] for service in base['services'].values())
    assert 'gateway' not in test['services']
    assert test['services']['db']['tmpfs'] == ['/var/lib/postgresql/data']
    assert not any('ports' in service or 'volumes' in service for service in test['services'].values())
    assert test['services']['tests']['environment']['DATABASE_URL'].endswith('/sdw_test')
    assert 'USER 10001:10001' in (ROOT/'Dockerfile').read_text()


def test_host_helper_retains_config_and_reset_requires_explicit_flag(tmp_path):
    spec = importlib.util.spec_from_file_location('sdw_dev_cli', ROOT/'scripts/dev.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = tmp_path/'local.env'
    generated = module.generate_config(config)
    assert len(generated['LOCAL_SECRET_KEY']) >= 32
    assert module.read_config(config) == generated
    with pytest.raises(FileExistsError): module.generate_config(config)
    test_command = module.compose_command('docker', config, project='sdw-kantine-test-unique', test=True)
    assert 'sdw-kantine-test-unique' in test_command and str(ROOT/'compose.test.yaml') in test_command
    assert module.local_engine_endpoint('npipe:////./pipe/dockerDesktopLinuxEngine')
    assert module.local_engine_endpoint('unix:///var/run/docker.sock')
    assert not module.local_engine_endpoint('ssh://production.example.org')
    assert not module.local_engine_endpoint('tcp://production.example.org:2376')
    with pytest.raises(SystemExit): module.main(['reset'])


def test_response_smoke_cannot_target_interactive_or_hosted_database(monkeypatch):
    from dev.common import require_local_database
    monkeypatch.setenv('LOCAL_DOCKER', '1')
    cfg = settings()
    monkeypatch.setattr(cfg, 'local_mail_capture', True)
    for url in ('postgresql+psycopg://sdw:fake@db/sdw_local',
                'postgresql+psycopg://sdw:fake@db/production',
                'postgresql+psycopg://sdw:fake@postgresql-datariotfc.alwaysdata.net/sdw_test'):
        monkeypatch.setattr(cfg, 'database_url', url)
        with pytest.raises(RuntimeError): require_local_database(test_only=True)
