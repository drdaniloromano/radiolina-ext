#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare optional GNOME 49 live media; never boot or install host packages."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
VM = ROOT / 'workspace' / 'gnome49-vm'
ISO_NAME = 'Fedora-Workstation-Live-43-1.6.x86_64.iso'
ISO_SIZE = 2742190080
ISO_SHA256 = '2a4a16c009244eb5ab2198700eb04103793b62407e8596f30a3e0cc8ac294d77'
FINGERPRINT = 'C6E7F081CF80E13146676E88829B606631645531'
UUID = 'radiolina@drdaniloromano.github.io'
BASE_URL = 'https://download.fedoraproject.org/pub/fedora/linux/releases/43/Workstation/x86_64/iso/'
ARCHIVE_URL = 'https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/43/Workstation/x86_64/iso/'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_iso(path):
    if path.stat().st_size != ISO_SIZE or sha256(path) != ISO_SHA256:
        raise RuntimeError('ISO size/hash mismatch; preserve it for inspection or remove it explicitly.')


def verify_signature():
    with tempfile.TemporaryDirectory(prefix='fedora-signature-') as temporary:
        command = ['gpg', '--batch', '--no-autostart', '--homedir', temporary]
        subprocess.run(command + ['--import', str(SCRIPTS / 'fedora43-signing-key.asc')],
                       check=True, capture_output=True)
        result = subprocess.run(command + ['--status-fd', '1', '--verify',
            str(SCRIPTS / 'Fedora-Workstation-43-1.6-x86_64-CHECKSUM')],
            check=True, capture_output=True, text=True)
        signatures = [line.split() for line in result.stdout.splitlines()
                      if line.startswith('[GNUPG:] VALIDSIG ')]
        if not any(line[2] == FINGERPRINT or line[-1] == FINGERPRINT for line in signatures):
            raise RuntimeError('Fedora checksum signer fingerprint mismatch.')
    checksum = (SCRIPTS / 'Fedora-Workstation-43-1.6-x86_64-CHECKSUM').read_text()
    if f'SHA256 ({ISO_NAME}) = {ISO_SHA256}' not in checksum:
        raise RuntimeError('Signed checksum does not match the pinned ISO.')


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        if not url.startswith('https://'):
            raise RuntimeError('Refusing a non-HTTPS download redirect.')
        return super().redirect_request(request, response, code, message, headers, url)


def download_iso(destination, archive):
    # An interrupted/invalid download never becomes trusted installation media.
    partial = destination.with_suffix('.iso.part')
    if partial.exists():
        raise RuntimeError(f'Remove the previous partial download explicitly: {partial}')
    url = (ARCHIVE_URL if archive else BASE_URL) + ISO_NAME
    print(f'Downloading {ISO_SIZE:,} bytes from {url}', flush=True)
    try:
        opener = urllib.request.build_opener(HTTPSRedirect())
        with opener.open(url, timeout=60) as response, partial.open('xb') as output:
            received = 0
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > ISO_SIZE:
                    raise RuntimeError('ISO download exceeds its pinned size.')
                output.write(chunk)
        verify_iso(partial)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def package_metadata(path):
    with zipfile.ZipFile(path) as package:
        info = package.getinfo('metadata.json')
        if info.file_size > 65536:
            raise RuntimeError('Package metadata exceeds its size bound.')
        metadata = json.loads(package.read(info))
    if (not isinstance(metadata, dict) or metadata.get('uuid') != UUID or
            not isinstance(metadata.get('shell-version'), list) or
            '49' not in metadata['shell-version']):
        raise RuntimeError('ZIP must be radiolina and declare GNOME 49 support.')
    return metadata


def require_stopped():
    spec = importlib.util.spec_from_file_location('radiolina_vm', SCRIPTS / 'vm.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    if launcher.running():
        raise RuntimeError('Stop the owned VM before changing its media.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', required=True, type=Path, help='Built and reviewed installer ZIP')
    parser.add_argument('--download', action='store_true', help='Explicitly allow a 2.74 GB ISO download')
    parser.add_argument('--archive', action='store_true', help='Use the official Fedora archive for a download')
    args = parser.parse_args()
    package = args.zip.resolve(strict=True)
    metadata = package_metadata(package)
    require_stopped()
    for executable in ('gpg', 'xorriso'):
        if not shutil.which(executable):
            raise RuntimeError(f'Missing existing host tool: {executable}; no packages were installed.')
    verify_signature()
    VM.mkdir(parents=True, exist_ok=True)
    iso = VM / ISO_NAME
    if not iso.exists():
        if not args.download:
            raise RuntimeError('ISO missing. Rerun with --download to explicitly allow the download.')
        download_iso(iso, args.archive)
    else:
        verify_iso(iso)
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=VM) as temporary:
        stage = Path(temporary)
        boot = stage / 'boot'
        boot.mkdir()
        subprocess.run(['xorriso', '-osirrox', 'on', '-indev', str(iso),
            '-extract', '/boot/x86_64/loader/linux', str(boot / 'vmlinuz'),
            '-extract', '/boot/x86_64/loader/initrd', str(boot / 'initrd.img')], check=True)
        payload = stage / 'payload'
        payload.mkdir()
        shutil.copyfile(SCRIPTS / 'prepare-guest.sh', payload / 'prepare-guest.sh')
        shutil.copyfile(package, payload / f'{UUID}.zip')
        subprocess.run(['xorriso', '-as', 'mkisofs', '-quiet', '-V', 'RADIOLINA_TEST',
            '-o', str(stage / 'payload.iso'), str(payload)], check=True)
        require_stopped()
        # Copy only the allowlisted files; unrelated private evidence stays intact.
        for directory, names in ((boot, ('vmlinuz', 'initrd.img')),
                                 (payload, ('prepare-guest.sh', f'{UUID}.zip'))):
            target = VM / directory.name
            target.mkdir(exist_ok=True)
            for name in names:
                os.replace(directory / name, target / name)
        os.replace(stage / 'payload.iso', VM / 'payload.iso')
    receipt = {
        'prepared_at': datetime.now(timezone.utc).isoformat(),
        'iso_sha256': ISO_SHA256, 'signer_fingerprint': FINGERPRINT,
        'zip_sha256': sha256(package), 'version': metadata.get('version-name'),
        'boot_sha256': {name: sha256(VM / 'boot' / name) for name in ('vmlinuz', 'initrd.img')},
        'booted': False,
    }
    (VM / 'rebuild-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Verified media prepared. Nothing booted; no host packages or extensions installed.')
    print('Start explicitly: python3 scripts/gnome49-vm/vm.py ready --view')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError,
            zipfile.BadZipFile) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
