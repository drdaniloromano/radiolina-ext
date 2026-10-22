#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run tests with temporary XDG paths and a private D-Bus session."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
subprocess.run(['python3', 'tests/e2e/package.py'], cwd=ROOT, check=True)
subprocess.run(['python3', 'tests/e2e/container_shell.py'], cwd=ROOT, check=True)
subprocess.run(['python3', 'tests/e2e/ci.py'], cwd=ROOT, check=True)
subprocess.run(['python3', 'tests/e2e/security.py'], cwd=ROOT, check=True)
with tempfile.TemporaryDirectory(prefix='gnome-radio-tests-') as directory:
    env = dict(os.environ, GIO_USE_VFS='local', XDG_RUNTIME_DIR=directory,
               XDG_CONFIG_HOME=directory, XDG_CACHE_HOME=directory,
               GST_REGISTRY=str(Path(directory) / 'gst-registry.bin'))
    subprocess.run(['gjs', '-m', 'tests/unit/critical.js'], cwd=ROOT, env=env, check=True)
    subprocess.run(['dbus-run-session', '--config-file=scripts/test-bus.conf', '--', 'python3', 'tests/e2e/service.py'],
                   cwd=ROOT, env=env, check=True)
    subprocess.run(['dbus-run-session', '--config-file=scripts/test-bus.conf', '--', 'python3', 'tests/e2e/validation.py'],
                   cwd=ROOT, env=env, check=True)
