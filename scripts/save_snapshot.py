"""Save source and a consistent local demo database without copying secret files."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def save_snapshot():
    stamp = datetime.now(ZoneInfo('Europe/Amsterdam')).strftime('%Y-%m-%d_%H%M%S')
    destination = ROOT / 'backups'
    destination.mkdir(exist_ok=True)
    archive_path = destination / f'sdw-kantine_{stamp}.zip'
    sources = []
    for folder in ('app', 'migrations', 'scripts', 'tests'):
        sources.extend(p for p in (ROOT / folder).rglob('*') if p.is_file()
                       and '__pycache__' not in p.parts and p.suffix != '.pyc')
    for name in ('.gitignore', '.env.example', 'README.md', 'SESSION_HANDOFF.md',
                 'requirements.txt', 'requirements-dev.txt', 'alembic.ini',
                 'research/dashboard-en.png', 'research/visitors-dashboard-en.png',
                 'research/visitors-mobile-en.png'):
        path = ROOT / name
        if path.exists():
            sources.append(path)
    manifest = {'saved_at': datetime.now(ZoneInfo('Europe/Amsterdam')).isoformat(),
                'files': {}, 'secrets_excluded': ['.env', '.provision.env', 'test-credentials.txt', 'SSH private key'],
                'status': 'Source and local demo snapshot. See SESSION_HANDOFF.md for current live deployment status; hosted PostgreSQL is not included.'}
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(sources):
            name = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            archive.writestr(name, content)
            manifest['files'][name] = hashlib.sha256(content).hexdigest()
        database_path = ROOT / 'development.db'
        if database_path.exists():
            with sqlite3.connect(database_path.as_uri() + '?mode=ro', uri=True) as source:
                with sqlite3.connect(':memory:') as snapshot:
                    source.backup(snapshot)
                    if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Database integrity check failed; original files were not modified.')
                    content = snapshot.serialize()
                    archive.writestr('development.db', content)
                    manifest['files']['development.db'] = hashlib.sha256(content).hexdigest()
        archive.writestr('SNAPSHOT_MANIFEST.json', json.dumps(manifest, indent=2))
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Snapshot archive verification failed.')
    manifest['archive'] = archive_path.name
    manifest['archive_sha256'] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    manifest_path = archive_path.with_suffix('.manifest.json')
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'archive': str(archive_path), 'manifest': str(manifest_path),
                      'saved_files': len(manifest['files']), 'bytes': archive_path.stat().st_size,
                      'database_integrity': 'ok', 'archive_integrity': 'ok'}))


if __name__ == '__main__':
    save_snapshot()
