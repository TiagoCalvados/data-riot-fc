"""Upload reviewed application source; no credentials or local data enter the archive."""
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
HOST = 'datariotfc@ssh-datariotfc.alwaysdata.net'
KEY = str(Path.home() / '.ssh/id_ed25519_datariotfc_alwaysdata')
OPTIONS = ['-i', KEY, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes']


def stage():
    from build_locales import build
    build()
    archive = ROOT / 'sdw-kantine.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in ['app', 'migrations', 'scripts/start.py', 'scripts/job.py', 'scripts/activate.py', 'scripts/build_locales.py',
                     'requirements.txt', 'requirements-dev.txt', 'alembic.ini', 'README.md', 'tests']:
            path = ROOT / name
            if path.exists():
                tar.add(path, arcname=name, filter=lambda info: None if '__pycache__' in info.name or info.name.endswith('.pyc') else info)
    subprocess.run(['scp', *OPTIONS, str(archive), HOST + ':sdw-kantine.tar.gz'], check=True)
    installer = '''from pathlib import Path
import subprocess, tarfile
root = Path('/home/datariotfc/sdw-kantine')
root.mkdir(mode=0o700, exist_ok=True)
with tarfile.open('/home/datariotfc/sdw-kantine.tar.gz') as archive:
    archive.extractall(root, filter='data')
if not (root/'.venv/bin/python').exists():
    subprocess.run(['python3','-m','venv',str(root/'.venv')],check=True)
subprocess.run([str(root/'.venv/bin/python'),'-m','pip','install','--no-user','-q','-r',str(root/'requirements.txt')],check=True)
print('Application source and dependencies staged in', root)
'''
    subprocess.run(['ssh', *OPTIONS, HOST, 'python3 -'], input=installer, text=True, check=True)


if __name__ == '__main__':
    stage()
