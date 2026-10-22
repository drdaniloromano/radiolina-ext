#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build or sequentially test versioned, private headless GNOME containers."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {'49': '43', '50': '44'}
SOURCES = ('extension', 'src', 'scripts', 'tests', 'LICENSE')


def run(command, **kwargs):
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def fingerprint():
    digest = hashlib.sha256()
    for name in SOURCES:
        path = ROOT / name
        files = sorted(path.rglob('*')) if path.is_dir() else [path]
        for file in files:
            if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc':
                digest.update(str(file.relative_to(ROOT)).encode() + b'\0' + file.read_bytes() + b'\0')
    return digest.hexdigest()


def main():
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'test'))
    parser.add_argument('--engine', default='podman')
    parser.add_argument('--gnome', nargs='+', choices=PROFILES, default=['49', '50'])
    parser.add_argument('--image-prefix', default='localhost/radiolina-shell-test')
    parser.add_argument('--refresh', action='store_true', help='pull base and bypass build cache')
    parser.add_argument('--scale', choices=('1', '1.5'), default='1')
    parser.add_argument('--theme', choices=('light', 'dark'), default='dark')
    args = parser.parse_args()
    if args.refresh and args.action != 'build':
        parser.error('--refresh applies only to build')
    engine = shlex.split(args.engine)
    if not engine:
        parser.error('--engine must name Podman or Docker')
    version = run([*engine, '--version'], capture_output=True, text=True).stdout.strip()
    if not version.startswith(('podman ', 'Docker ')):
        parser.error('unsupported engine: choose Podman or Docker')
    identity = shlex.split(run(['sh', 'scripts/container-user-flags.sh', *engine],
                              capture_output=True, text=True).stdout)
    artifacts = ROOT / 'build/shell-tests'
    artifacts.mkdir(parents=True, exist_ok=True)
    # The same lock covers independent invocations, not just this version loop.
    with (artifacts / '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('another Shell container build/test is running for this checkout')
        for major in dict.fromkeys(args.gnome):
            image = f'{args.image_prefix}:{major}'
            if args.action == 'build':
                flags = []
                if args.refresh:
                    flags = ['--pull=always' if version.startswith('podman ') else '--pull', '--no-cache']
                run([*engine, 'build', *flags, '-t', image, '-f', 'Dockerfile.shell',
                     '--build-arg', f'FEDORA_VERSION={PROFILES[major]}',
                     '--build-arg', f'GNOME_VERSION={major}',
                     '--build-arg', f'TEST_UID={os.getuid()}',
                     '--build-arg', f'TEST_GID={os.getgid()}', '.'])
                continue
            image_id = run([*engine, 'image', 'inspect', '--format', '{{.Id}}', image],
                           capture_output=True, text=True).stdout.strip()
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            name = f'radiolina-shell-{major}-{uuid.uuid4().hex[:12]}'
            output = artifacts / major / f'{stamp}-{name.rsplit("-", 1)[-1]}'
            output.mkdir(parents=True, mode=0o700)
            manifest = {'gnome_major': major, 'fedora_release': PROFILES[major], 'image': image,
                        'image_id': image_id, 'engine': version, 'scale': args.scale, 'theme': args.theme,
                        'source_sha256': fingerprint(), 'release_approved': False}
            command = [*engine, 'run', '--rm', '--name', name, *identity,
                       '--network=none', '--read-only', '--cap-drop=all',
                       '--security-opt=no-new-privileges', '--security-opt=label=disable',
                       '--memory=1g', '--cpus=2', '--pids-limit=256', '--shm-size=128m',
                       '--tmpfs', '/tmp:rw,nosuid,nodev,size=1g',
                       '--tmpfs', '/run:rw,nosuid,nodev,size=16m',
                       '--env', 'HOME=/tmp/home', '--env', f'GNOME_RADIO_TEST_SCALE={args.scale}',
                       '--env', f'GNOME_RADIO_TEST_THEME={args.theme}']
            for source in SOURCES:
                command.extend(['-v', f'{ROOT / source}:/input/{source}:ro'])
            # Run the inspected immutable ID, even if a tag is changed externally.
            command.extend(['-v', f'{output}:/results:rw', image_id, 'python3',
                            '/input/scripts/run-shell-container.py', '--gnome', major])
            print(f'Testing GNOME {major}; evidence: {output.relative_to(ROOT)}', flush=True)
            code = 1
            try:
                code = subprocess.run(command, cwd=ROOT, timeout=600).returncode
            except subprocess.TimeoutExpired:
                print('Shell container exceeded its ten-minute limit.', flush=True)
            finally:
                # Covers timeout/interruption too; never stop an unrelated container.
                subprocess.run([*engine, 'rm', '--force', name], cwd=ROOT, capture_output=True)
                manifest['exit_code'] = code
                (output / 'container.json').write_text(json.dumps(manifest, indent=2) + '\n')
            if code:
                return code
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Shell container operation interrupted; owned container cleanup requested.', file=sys.stderr)
        raise SystemExit(130)
