#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Container-only worker: copy allowlisted inputs, build and test privately."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gnome', required=True, choices=('49', '50'))
    args = parser.parse_args()
    if not Path('/input/extension/metadata.json').is_file() or not Path('/results').is_dir():
        parser.error('run through scripts/container-shell.py, not on the desktop host')
    version = subprocess.check_output(['gnome-shell', '--version'], text=True).strip()
    if version.split()[-1].split('.')[0] != args.gnome:
        parser.error(f'expected GNOME {args.gnome}, found {version}')
    packages = subprocess.check_output(['rpm', '-q', 'gnome-shell', 'mutter', 'gjs', 'gstreamer1',
                                        'gstreamer1-plugins-base', 'gstreamer1-plugins-good', 'libsoup3'], text=True)
    Path.home().mkdir(mode=0o700, parents=True, exist_ok=True)
    results = Path('/results')
    summary = {'shell': version, 'packages': packages.splitlines(), 'exit_code': 1,
               'headless': True, 'silent_audio': True, 'release_approved': False}
    with tempfile.TemporaryDirectory(prefix='radiolina-shell-checkout-') as temporary:
        checkout = Path(temporary)
        for source in ('extension', 'src', 'scripts', 'tests'):
            shutil.copytree(Path('/input') / source, checkout / source,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copyfile('/input/LICENSE', checkout / 'LICENSE')
        (checkout / 'workspace').mkdir(mode=0o700)
        code = 1
        try:
            with (results / 'test.log').open('w') as log:
                for command in (['python3', 'scripts/build.py'],
                                ['python3', 'scripts/test-shell.py', '--expected-major', args.gnome]):
                    result = subprocess.run(command, cwd=checkout, stdout=log, stderr=subprocess.STDOUT)
                    code = result.returncode
                    log.flush()
                    if code:
                        break
            bundle = next((checkout / 'build').glob('*.zip'), None)
            if bundle:
                summary['zip_sha256'] = hashlib.sha256(bundle.read_bytes()).hexdigest()
                # ZIP timestamps differ between disposable checkouts. Compare
                # installed file bytes separately across the version matrix.
                payload = hashlib.sha256()
                with zipfile.ZipFile(bundle) as archive:
                    for name in sorted(archive.namelist()):
                        payload.update(name.encode() + b'\0' + archive.read(name) + b'\0')
                summary['package_payload_sha256'] = payload.hexdigest()
        finally:
            shutil.copytree(checkout / 'workspace', results / 'evidence', dirs_exist_ok=True)
            summary['exit_code'] = code
            (results / 'runtime.json').write_text(json.dumps(summary, indent=2) + '\n')
        print((results / 'test.log').read_text()[-12000:], flush=True)
        return code


if __name__ == '__main__':
    raise SystemExit(main())
