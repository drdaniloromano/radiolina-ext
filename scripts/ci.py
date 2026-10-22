#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Local/Actions adapter for existing Make tests; never publishes anything."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'build/ci'
PREFIX = os.environ.get('CI_IMAGE_PREFIX', 'localhost/radiolina-ci')
AAC = os.environ.get('CI_AAC_IMAGE', PREFIX + '-aac:44')
PROFILES = ('49', '50')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def read(path):
    return json.loads(path.read_text())


def source_id():
    value = hashlib.sha256()
    for name in ('extension', 'src', 'scripts', 'tests', 'LICENSE', 'Makefile',
                 'Dockerfile', 'Dockerfile.shell', 'Dockerfile.aac', '.dockerignore', '.github'):
        base = ROOT / name
        for path in sorted(base.rglob('*')) if base.is_dir() else [base]:
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                value.update(str(path.relative_to(ROOT)).encode() + b'\0' + path.read_bytes() + b'\0')
    return value.hexdigest()


def run(command, log=None, timeout=1200):
    print('+ ' + ' '.join(command), flush=True)
    if log is None:
        return subprocess.check_output(command, cwd=ROOT, text=True).strip()
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log.open('w') as output:
        process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    print(log.read_text(errors='replace')[-10000:], flush=True)
    if code:
        raise subprocess.CalledProcessError(code, command)
    return round(time.monotonic() - started, 3)


def image_name(profile):
    return AAC if profile == 'aac' else f'{PREFIX}:{profile}'


def inspect(engine, image):
    return run([engine, 'image', 'inspect', '--format', '{{.Id}}', image])


def make(engine, target, **values):
    return ['make', target, f'CONTAINER_ENGINE={engine}',
            *[f'{key}={value}' for key, value in values.items()]]


def image(args):
    name = image_name(args.profile)
    cache = ROOT / 'build/ci-cache' / args.profile
    archive, metadata = cache / 'image.tar.gz', cache / 'image.json'
    key = hashlib.sha256(b'\0'.join((ROOT / file).read_bytes() for file in
                         ('Dockerfile.shell', 'Dockerfile.aac', '.dockerignore', 'Makefile',
                          'scripts/container-shell.py', 'scripts/container-identity.py',
                          '.github/ci-image-generation')) +
                          f'{args.profile}:{os.getuid()}:{os.getgid()}'.encode()).hexdigest()
    origin = 'build'
    if args.reuse_local:
        origin = 'local-existing'
    elif not args.refresh and archive.is_file() and metadata.is_file():
        saved = read(metadata)
        if saved['input_sha256'] != key or digest(archive) != saved['archive_sha256']:
            raise ValueError('Image cache integrity/input mismatch; request a fresh build')
        run([args.engine, 'load', '--input', str(archive)], STATE / f'load-{args.profile}.log')
        if inspect(args.engine, name) != saved['image_id']:
            raise ValueError('Loaded image differs from cached immutable identity')
        origin = 'cache'
    else:
        if args.profile == 'aac':
            command = make(args.engine, 'container-aac-build', AAC_IMAGE=name,
                           AAC_BASE_IMAGE=image_name('50'))
            if args.refresh:
                # AAC inherits the refreshed 50 image; refresh its codec layer too.
                command = [args.engine, 'build', '--no-cache', '--build-arg',
                           f'BASE_IMAGE={image_name("50")}', '-t', name, '-f', 'Dockerfile.aac', '.']
        else:
            command = make(args.engine, 'container-shell-refresh' if args.refresh else
                           'container-shell-build', SHELL_VERSIONS=args.profile,
                           SHELL_IMAGE_PREFIX=PREFIX)
        run(command, STATE / f'build-{args.profile}.log', timeout=1800)
    identifier = inspect(args.engine, name)
    write(STATE / f'image-{args.profile}.json', {
        'image': name, 'image_id': identifier, 'origin': origin,
        'engine': run([args.engine, '--version']), 'input_sha256': key,
        'packages': run([args.engine, 'run', '--rm', '--network=none', '--read-only',
                         '--cap-drop=all', '--security-opt=no-new-privileges',
                         '--memory=256m', '--pids-limit=64', identifier, 'rpm', '-q',
                         'gnome-shell', 'mutter', 'gjs', 'gstreamer1',
                         'gstreamer1-plugins-base', 'gstreamer1-plugins-good', 'libsoup3',
                         *(['gstreamer1-plugin-libav', 'libavcodec-free'] if args.profile == 'aac' else [])]).splitlines()})
    if origin == 'build':
        cache.mkdir(parents=True, exist_ok=True)
        temporary = cache / 'image.partial.gz'
        try:
            with gzip.open(temporary, 'wb', compresslevel=1) as output:
                process = subprocess.Popen([args.engine, 'save', name], stdout=subprocess.PIPE)
                try:
                    shutil.copyfileobj(process.stdout, output)
                finally:
                    process.stdout.close()
                    code = process.wait()
                if code:
                    raise subprocess.CalledProcessError(code, process.args)
            if temporary.stat().st_size > 3 * 1024 ** 3:
                raise ValueError('Compressed image exceeds the 3 GiB per-profile cache budget')
            temporary.replace(archive)
            write(metadata, {'input_sha256': key, 'image_id': identifier,
                             'archive_sha256': digest(archive)})
        finally:
            temporary.unlink(missing_ok=True)


def test(args):
    destination = STATE / 'artifacts/package'
    if destination.exists():
        shutil.rmtree(destination)
    result_file = STATE / f'test-{args.profile}.json'
    result_file.unlink(missing_ok=True)
    identity = read(STATE / f'image-{args.profile}.json')
    if inspect(args.engine, identity['image']) != identity['image_id']:
        raise ValueError('Image changed since preparation')
    before = set((ROOT / 'build/shell-tests').glob('*/*/container.json'))
    record = {'source_sha256': source_id(), 'runtime': identity, 'passed': False, 'runs': []}
    service_name = 'radiolina-ci-service-' + uuid.uuid4().hex[:12]
    try:
        record['service_seconds'] = run(make(args.engine, 'container-test',
            IMAGE=identity['image_id'], REQUIRE_AAC=int(args.profile == 'aac'),
            CONTAINER_RUN_FLAGS='--rm --network=none --security-opt=label=disable '
                f'--name={service_name} --memory=1g --cpus=2 --pids-limit=256'),
            STATE / f'service-{args.profile}.log')
        if args.profile != 'aac':
            for scale, theme in (('1', 'dark'), ('1.5', 'light')):
                run(make(args.engine, 'container-shell-test', SHELL_VERSIONS=args.profile,
                         SHELL_IMAGE_PREFIX=PREFIX, SHELL_SCALE=scale, SHELL_THEME=theme),
                    STATE / f'shell-{args.profile}-{scale}.log', timeout=660)
        if source_id() != record['source_sha256']:
            raise ValueError('Sources changed during tests')
        record['passed'] = True
    finally:
        subprocess.run([args.engine, 'rm', '--force', service_name], cwd=ROOT, capture_output=True)
        after = set((ROOT / 'build/shell-tests').glob('*/*/container.json'))
        record['runs'] = [str(path.parent.relative_to(ROOT)) for path in sorted(after - before)]
        write(result_file, record)


def payload(archive):
    value = hashlib.sha256()
    for name in sorted(archive.namelist()):
        value.update(name.encode() + b'\0' + archive.read(name) + b'\0')
    return value.hexdigest()


def verify_bundle(bundle):
    metadata = read(ROOT / 'extension/metadata.json')
    with zipfile.ZipFile(bundle) as archive:
        if archive.testzip() or len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('Corrupt or duplicate ZIP members')
        actual = json.loads(archive.read('metadata.json'))
        sources = {str(path.relative_to(ROOT / 'extension')): path
                   for path in (ROOT / 'extension').rglob('*') if path.is_file()}
        sources.update({'src/' + str(path.relative_to(ROOT / 'src')): path
                        for path in (ROOT / 'src').rglob('*') if path.is_file()})
        runtime, stylesheet = actual['radio-runtime'], actual['radio-stylesheet']
        if set(archive.namelist()) != set(sources) | {'LICENSE', runtime, stylesheet}:
            raise ValueError('ZIP includes missing or unexpected files')
        expected = dict(metadata, **{'radio-runtime': runtime, 'radio-stylesheet': stylesheet})
        if actual != expected or archive.read('LICENSE') != (ROOT / 'LICENSE').read_bytes():
            raise ValueError('ZIP metadata/license mismatch')
        for name, path in sources.items():
            if name not in ('extension.js', 'stylesheet.css', 'metadata.json'):
                if archive.read(name) != path.read_bytes():
                    raise ValueError(f'ZIP source mismatch: {name}')
        source = (ROOT / 'extension/extension.js').read_bytes()
        styles = (ROOT / 'extension/stylesheet.css').read_bytes()
        expected_runtime = 'radio-' + hashlib.sha256(source + b'\0' + styles).hexdigest()[:12] + '.js'
        expected_style = 'radio-style-' + hashlib.sha256(styles).hexdigest()[:12] + '.css'
        if (runtime != expected_runtime or stylesheet != expected_style or
            archive.read(runtime) != source or archive.read(stylesheet) != styles or
            archive.read('extension.js') != ('// SPDX-License-Identifier: MIT\n'
                 f"export {{default}} from './{runtime}';\n").encode() or
            archive.read('stylesheet.css') != b'/* SPDX-License-Identifier: MIT */\n'
                 b'/* Layout is loaded from the versioned radio stylesheet. */\n'):
            raise ValueError('ZIP runtime/style wrapper mismatch')
        return payload(archive)


def package(args):
    destination = STATE / 'artifacts/package'
    if destination.exists():
        shutil.rmtree(destination)
    results = {}
    for profile in (*PROFILES, 'aac'):
        record = read(STATE / f'test-{profile}.json')
        if not record['passed'] or record['source_sha256'] != source_id():
            raise ValueError('All current profile tests must pass before artifact packaging')
        if profile in PROFILES:
            if len(record['runs']) != 2:
                raise ValueError('Both theme/scale runs are required for each Shell profile')
            for directory in record['runs']:
                runtime = read(ROOT / directory / 'runtime.json')
                container = read(ROOT / directory / 'container.json')
                if (runtime['exit_code'] or container['exit_code'] or
                    container['image_id'] != record['runtime']['image_id']):
                    raise ValueError('Shell runtime evidence does not match the tested image')
        results[profile] = record
    identity = results['50']['runtime']
    if inspect(args.engine, identity['image']) != identity['image_id']:
        raise ValueError('Packaging image differs from the tested runtime')
    run(make(args.engine, 'container-package', IMAGE=identity['image_id']), STATE / 'package.log')
    metadata = read(ROOT / 'extension/metadata.json')
    bundle = ROOT / 'build' / f'{metadata["uuid"]}.zip'
    if (bundle.stat().st_uid, bundle.stat().st_gid) != (os.getuid(), os.getgid()):
        raise ValueError('Generated ZIP ownership differs from invoking user')
    checksum = verify_bundle(bundle)
    for profile in PROFILES:
        for directory in results[profile]['runs']:
            if read(ROOT / directory / 'runtime.json')['package_payload_sha256'] != checksum:
                raise ValueError('Installation ZIP differs from the actual Shell-tested payload')
    destination.mkdir(parents=True)
    shutil.copyfile(bundle, destination / bundle.name)
    (destination / 'SHA256SUMS').write_text(f'{digest(bundle)}  {bundle.name}\n')
    write(destination / 'verification.json', {
        'source_commit': run(['git', 'rev-parse', 'HEAD']), 'source_sha256': source_id(),
        'zip_sha256': digest(bundle), 'package_payload_sha256': checksum,
        'runtimes': {key: value['runtime'] for key, value in results.items()},
        'shell_packages': {profile: read(ROOT / results[profile]['runs'][0] / 'runtime.json')['packages']
                           for profile in PROFILES},
        'release_approved': False, 'physical_hardware_verified': False})


def evidence(_args):
    destination = STATE / 'artifacts/test-evidence'
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    # These are test-generated files only, never the host/private workspace.
    selected = list(STATE.glob('*.log'))
    selected += list(STATE.glob('image-*.json')) + list(STATE.glob('test-*.json'))
    for record_file in STATE.glob('test-*.json'):
        for directory in read(record_file)['runs']:
            folder = ROOT / directory
            if not folder.resolve().is_relative_to((ROOT / 'build/shell-tests').resolve()):
                raise ValueError('Unexpected evidence directory')
            selected.extend(folder / name for name in ('container.json', 'runtime.json', 'test.log'))
            selected.extend(folder / 'evidence' / name for name in (
                'shell-oom-recovery.json', 'shell-resource-lifecycle.json', 'play-circle-alignment.json',
                'shell-e2e.log', 'playback-hover-light.png', 'playback-hover-dark.png',
                'large-text-light-stations.png', 'large-text-dark-stations.png', 'popup.png',
                'row-actions-hidden.png', 'editor.png', 'settings.png',
                'shell-final.png', 'screenshot-regression.png'))
    total = 0
    for path in selected:
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix == '.png' and path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError('Screenshot exceeds the 5 MiB per-file output budget')
        with path.open('rb') as stream:
            if path.suffix == '.log':
                stream.seek(max(0, path.stat().st_size - 1024 * 1024))
            data = stream.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise ValueError('Evidence exceeds the per-file output budget')
        if path.suffix != '.png':
            text = data.decode(errors='replace')[-1024 * 1024:]
            text = text.replace(str(ROOT), '<checkout>')
            text = re.sub(r'https?://[^\s\"\'<>]+', '<url>', text)
            data = text.encode()
        total += len(data)
        if total > 25 * 1024 * 1024 or len(data) > 5 * 1024 * 1024:
            raise ValueError('Selected evidence exceeds the documented output budget')
        name = '__'.join(path.relative_to(ROOT / 'build').parts)
        (destination / name).write_bytes(data)
    write(destination / 'coverage.json', {
        'source_commit': run(['git', 'rev-parse', 'HEAD']),
        'release_approved': False, 'screenshots_require_human_review': True,
        'physical_audio_media_keys_lock_suspend_verified': False,
        'note': 'Allowlisted logs have URL redaction and a 1 MiB tail limit.'})


def main():
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'image', 'test', 'package', 'evidence'))
    parser.add_argument('--engine', default='podman', choices=('podman', 'docker'))
    parser.add_argument('--profile', choices=(*PROFILES, 'aac'), default='49')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--reuse-local', action='store_true', help='local verification only, never CI cache seeding')
    args = parser.parse_args()
    if args.action == 'start':
        # Explicit fresh run prevents old successful results from authorizing packaging.
        if STATE.exists():
            shutil.rmtree(STATE)
        STATE.mkdir(parents=True)
    else:
        if not STATE.is_dir():
            parser.error('run start first')
        if args.action in ('image', 'test', 'package') and os.environ.get('GITHUB_ACTIONS') == 'true':
            version = run([args.engine, '--version'])
            if args.engine != 'docker' or not version.startswith('Docker '):
                parser.error('Actions requires genuine Docker, not a Podman wrapper')
            if args.reuse_local:
                parser.error('--reuse-local is not allowed in Actions')
        globals()[args.action](args)


if __name__ == '__main__':
    main()
