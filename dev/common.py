"""Refuse local tooling against unrelated or production databases."""
import os
from sqlalchemy.engine import make_url
from app.config import settings


def require_local_database(*, test_only=False):
    config = settings()
    url = make_url(config.database_url)
    names = ('sdw_test',) if test_only else ('sdw_local', 'sdw_test')
    if (os.environ.get('LOCAL_DOCKER') != '1' or url.get_backend_name() != 'postgresql'
            or url.host != 'db' or url.database not in names
            or not config.demo_mode or not config.local_mail_capture):
        raise RuntimeError('Docker tooling requires the isolated db/sdw_local or db/sdw_test environment')
    return config
