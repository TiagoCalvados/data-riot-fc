"""One-shot migration and idempotent fictional seed, before app/worker startup."""
import os
import json
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import select, func
from dev.common import require_local_database
from app.db import SessionLocal
from app.models import User, Fixture, Shift, Invitation
from app.seed import seed
from app.jobs import run_job
from app.security import password_hash


def ensure_mail_parents(db):
    """Add local-only named test accounts without replacing existing credentials."""
    accounts = json.loads((Path(__file__).parent/'mailboxes.json').read_text())
    for account in accounts:
        if not db.scalar(select(User.id).where(User.username == account['username'])):
            db.add(User(**account, password_hash=password_hash(os.environ['LOCAL_PARENT_PASSWORD']), is_demo=True))
    db.commit()


def counts(db):
    return tuple(db.scalar(select(func.count()).select_from(model)) for model in (User, Fixture, Shift, Invitation))


def main():
    require_local_database()
    command.upgrade(Config('alembic.ini'), 'head')
    with SessionLocal() as db:
        result = seed(db, os.environ['LOCAL_ADMIN_PASSWORD'], os.environ['LOCAL_PARENT_PASSWORD'])
        before = counts(db)
        # A second bootstrap must retain accounts/passwords and all history.
        assert seed(db, os.environ['LOCAL_ADMIN_PASSWORD'], os.environ['LOCAL_PARENT_PASSWORD'])['state'] == 'already_initialized'
        assert counts(db) == before
        ensure_mail_parents(db)
        run_job(db)
    print('Local fictional bootstrap ready:', result['state'], '; seed repeatability verified', flush=True)


if __name__ == '__main__':
    main()
