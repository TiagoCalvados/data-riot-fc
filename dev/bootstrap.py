"""One-shot migration and idempotent fictional seed, before app/worker startup."""
import os
from alembic import command
from alembic.config import Config
from sqlalchemy import select, func
from dev.common import require_local_database
from app.db import SessionLocal
from app.models import User, Fixture, Shift, Invitation
from app.seed import seed
from app.jobs import run_job


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
        run_job(db)
    print('Local fictional bootstrap ready:', result['state'], '; seed repeatability verified', flush=True)


if __name__ == '__main__':
    main()
