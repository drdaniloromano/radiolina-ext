#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Opt-in Linux resource probe with private XDG paths and D-Bus; no forced GC."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='radiolina-resources-') as directory:
    env = dict(os.environ, XDG_RUNTIME_DIR=directory, XDG_CONFIG_HOME=directory,
               XDG_CACHE_HOME=directory, GIO_USE_VFS='local',
               GST_REGISTRY=str(Path(directory) / 'gst-registry.bin'))
    subprocess.run(['dbus-run-session', '--config-file=scripts/test-bus.conf', '--',
                    'python3', 'tests/e2e/resources.py'], cwd=ROOT, env=env, check=True)
