"""Unit suite plus the isolated PostgreSQL/Mailpit HTTP integration flow."""
import os
import subprocess
import sys
from dev.common import require_local_database


def main():
    require_local_database(test_only=True)
    env = os.environ.copy()
    env['LOCAL_MAIL_CAPTURE'] = 'false'  # conftest owns unit-test SQLite/settings
    env.pop('SSLKEYLOGFILE', None)
    subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'], env=env, check=True)
    subprocess.run([sys.executable, '-m', 'dev.bootstrap'], check=True)
    subprocess.run([sys.executable, '-m', 'dev.bootstrap'], check=True)
    from dev.smoke import run
    run(exercise_response=True)


if __name__ == '__main__':
    main()
