#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline VM preparation boundaries; never download, boot or signal processes."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts' / 'gnome49-vm'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rebuild = load('rebuild')
launcher = load('vm')


class PreparationBoundaries(unittest.TestCase):
    @unittest.skipUnless(shutil.which('gpg'), 'GnuPG unavailable; do not install host dependencies')
    def test_signature_and_tampered_checksum(self):
        rebuild.verify_signature()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            shutil.copyfile(SCRIPTS / 'fedora43-signing-key.asc', temporary / 'fedora43-signing-key.asc')
            name = 'Fedora-Workstation-43-1.6-x86_64-CHECKSUM'
            checksum = (SCRIPTS / name).read_text().replace(rebuild.ISO_SHA256, '0' * 64)
            (temporary / name).write_text(checksum)
            with patch.object(rebuild, 'SCRIPTS', temporary):
                with self.assertRaises(subprocess.CalledProcessError):
                    rebuild.verify_signature()

    def test_missing_iso_never_downloads_without_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            package = temporary / 'installer.zip'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('metadata.json', json.dumps({
                    'uuid': rebuild.UUID, 'shell-version': ['49'], 'version-name': 'test'}))
            with (patch.object(rebuild, 'VM', temporary / 'vm'),
                  patch.object(rebuild, 'verify_signature'),
                  patch.object(rebuild, 'require_stopped'),
                  patch.object(rebuild.shutil, 'which', return_value='/existing/tool'),
                  patch.object(rebuild, 'download_iso') as download,
                  patch.object(sys, 'argv', ['rebuild.py', '--zip', str(package)])):
                with self.assertRaisesRegex(RuntimeError, 'explicitly allow'):
                    rebuild.main()
                download.assert_not_called()
                self.assertFalse((temporary / 'vm' / 'payload.iso').exists())

    def test_corrupt_media_and_incompatible_package_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            media = temporary / 'bad.iso'
            media.write_bytes(b'not a Fedora ISO')
            with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                rebuild.verify_iso(media)
            package = temporary / 'wrong.zip'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('metadata.json', json.dumps({
                    'uuid': rebuild.UUID, 'shell-version': ['50']}))
            with self.assertRaisesRegex(RuntimeError, 'GNOME 49 support'):
                rebuild.package_metadata(package)

    def test_foreign_pid_is_not_owned_and_extra_payload_is_not_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            (temporary / 'qemu.pid').write_text(str(os.getpid()))
            payload = temporary / 'payload'
            payload.mkdir()
            for name in ('prepare-guest.sh', f'{rebuild.UUID}.zip', 'private.txt'):
                (payload / name).write_text('fixture')
            with (patch.object(launcher, 'VM', temporary),
                  patch.object(launcher.subprocess, 'run') as run):
                self.assertIsNone(launcher.running())
                with self.assertRaisesRegex(RuntimeError, 'Unexpected payload'):
                    launcher.start()
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
