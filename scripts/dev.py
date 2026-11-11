"""Cross-platform local Docker lifecycle; stdlib only, never loads the root .env."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / '.local/docker.env'
PROJECT = 'sdw-kantine-local'


def docker_binary():
    found = shutil.which('docker')
    if found:
        return found
    if os.name == 'nt':
        for base in (Path(os.environ.get('LOCALAPPDATA', ''))/'Programs/DockerDesktop',
                     Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'Docker/Docker'):
            candidate = base/'resources/bin/docker.exe'
            if candidate.is_file():
                return str(candidate)
    raise RuntimeError('Docker CLI is missing. Install/start Docker Desktop with Linux containers; see dev/README.md.')


def generate_config(path, *, test=False, app_port=8000, mail_port=8025):
    if not (1024 <= app_port <= 65535 and 1024 <= mail_port <= 65535 and app_port != mail_port):
        raise ValueError('Choose distinct unprivileged app/mail ports from 1024 through 65535')
    data = {'LOCAL_DB_PASSWORD': secrets.token_urlsafe(32), 'LOCAL_SECRET_KEY': secrets.token_urlsafe(48),
            'LOCAL_ADMIN_PASSWORD': secrets.token_urlsafe(18), 'LOCAL_PARENT_PASSWORD': secrets.token_urlsafe(18),
            'LOCAL_DB_NAME': 'sdw_test' if test else 'sdw_local', 'APP_PORT': str(app_port),
            'MAIL_PORT': str(mail_port), 'WORKER_INTERVAL_SECONDS': '3' if test else '30'}
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents normal startup from replacing persisted credentials.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
        output.write('# Generated local-only credentials; never commit or share this file.\n')
        output.writelines(f'{key}={value}\n' for key, value in data.items())
    return data


def read_config(path):
    return dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines()
                if line and not line.startswith('#'))


def compose_command(docker, config, *, project=PROJECT, test=False):
    overlay = 'compose.test.yaml' if test else 'compose.local.yaml'
    return [docker, 'compose', '--project-name', project, '--project-directory', str(ROOT),
            '--env-file', str(config), '-f', str(ROOT/'compose.yaml'), '-f', str(ROOT/overlay)]


def execute(command, *, capture=False, check=True, timeout=None):
    # Parent terminal SSL tracing hooks must not enter the local application.
    env = os.environ.copy()
    env.pop('SSLKEYLOGFILE', None)
    return subprocess.run(command, cwd=ROOT, env=env, check=check, text=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None)


def check_engine(docker):
    version = execute([docker, 'compose', 'version', '--short'], capture=True, timeout=20).stdout.strip().lstrip('v')
    parts = tuple(int(p) for p in version.split('.')[:2])
    if parts < (2, 24):
        raise RuntimeError('Docker Compose 2.24 or newer is required')
    endpoint = os.environ.get('DOCKER_HOST') if not os.environ.get('DOCKER_CONTEXT') else None
    if not endpoint:
        endpoint = execute([docker, 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'],
                           capture=True, timeout=20).stdout.strip()
    if not local_engine_endpoint(endpoint):
        raise RuntimeError('Select a local Docker Desktop/Linux context; this wrapper refuses remote engines')
    result = execute([docker, 'info', '--format', '{{.OSType}}'], capture=True, timeout=30)
    if result.stdout.strip() != 'linux':
        raise RuntimeError('Start Docker Desktop and select Linux containers')
    print('Docker Linux engine ready; Compose '+version)


def local_engine_endpoint(endpoint):
    return (endpoint.startswith(('unix:///', 'npipe:////./pipe/'))
            or (urlsplit(endpoint).scheme == 'tcp' and urlsplit(endpoint).hostname in ('localhost', '127.0.0.1', '::1')))


def wait_ready(command, timeout=180):
    deadline = time.monotonic()+timeout
    pending = {'app', 'worker'}
    while pending and time.monotonic() < deadline:
        for service in tuple(pending):
            result = execute([*command, 'exec', '-T', service, 'python', '-m', 'dev.healthcheck', service],
                             capture=True, check=False, timeout=20)
            if result.returncode == 0:
                pending.remove(service)
        if pending:
            time.sleep(2)
    if pending:
        raise RuntimeError('Readiness timed out for '+', '.join(sorted(pending))+'; inspect dev.py logs')


def start(command):
    execute([*command, 'up', '--build', '--detach', 'app', 'worker'])
    wait_ready(command)


def isolated_tests(docker):
    project = 'sdw-kantine-test-'+uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix='sdw-docker-test-') as folder:
        config = Path(folder)/'test.env'
        generate_config(config, test=True)
        command = compose_command(docker, config, project=project, test=True)
        try:
            start(command)
            execute([*command, 'run', '--rm', '--build', 'tests'])
        finally:
            # Only this random test project is torn down; never the dev volume.
            execute([*command, 'down', '--volumes', '--remove-orphans', '--rmi', 'local'], check=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'doctor', 'up', 'down', 'logs', 'status',
                                           'rebuild', 'test', 'smoke', 'credentials', 'reset', 'config'))
    parser.add_argument('--app-port', type=int, default=8000)
    parser.add_argument('--mail-port', type=int, default=8025)
    parser.add_argument('--confirm-delete-local-data', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'reset' and not args.confirm_delete_local_data:
        parser.error('Reset deletes only the local development database volume. Add --confirm-delete-local-data explicitly.')
    if args.command in ('init', 'up', 'rebuild', 'credentials', 'config') and not CONFIG.exists():
        generate_config(CONFIG, app_port=args.app_port, mail_port=args.mail_port)
    if args.command == 'init':
        print('Local config retained at .local/docker.env. Run python scripts/dev.py up next.')
        return
    if args.command == 'credentials':
        data = read_config(CONFIG)
        print('Fictional coordinator: beheer.test / '+data['LOCAL_ADMIN_PASSWORD'])
        print('Fictional parent: ouder.test / '+data['LOCAL_PARENT_PASSWORD'])
        return
    docker = docker_binary()
    if args.command == 'config':
        execute([*compose_command(docker, CONFIG), 'config', '--quiet'])
        print('Compose configuration is valid; secrets were not printed.')
        return
    check_engine(docker)
    if args.command == 'doctor':
        return
    if args.command == 'test':
        isolated_tests(docker)
        return
    if not CONFIG.exists():
        raise RuntimeError('Run python scripts/dev.py init first')
    command = compose_command(docker, CONFIG)
    if args.command in ('up', 'rebuild'):
        if args.command == 'rebuild':
            execute([*command, 'build', '--pull'])
        start(command)
        data = read_config(CONFIG)
        print('App: http://127.0.0.1:'+data['APP_PORT'])
        print('Captured mail: http://127.0.0.1:'+data['MAIL_PORT'])
        print('Login details: python scripts/dev.py credentials')
    elif args.command == 'down':
        execute([*command, 'down', '--remove-orphans'])
    elif args.command == 'logs':
        execute([*command, 'logs', '--tail', '100', '--follow', 'app', 'worker', 'bootstrap', 'mailpit'])
    elif args.command == 'status':
        execute([*command, 'ps', '--all'])
    elif args.command == 'smoke':
        execute([*command, 'run', '--rm', '--no-deps', '--entrypoint', 'python', 'app', '-m', 'dev.smoke'])
    elif args.command == 'reset':
        execute([*command, 'down', '--volumes', '--remove-orphans'])
        print('Deleted only the '+PROJECT+' local volume; generated credentials retained. Run up to reseed.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Compose can echo environment values in its command; omit full exception text.
        print(str(exc) if not isinstance(exc, (subprocess.CalledProcessError, subprocess.TimeoutExpired))
              else 'Docker command failed; check Docker Desktop and the local service logs.', file=sys.stderr)
        raise SystemExit(1)
