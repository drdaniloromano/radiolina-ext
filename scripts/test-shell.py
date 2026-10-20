#!/usr/bin/env python3
"""Run real Shell E2E tests with disposable settings and a private bus."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='gnome-radio-shell-') as directory:
    base = Path(directory)
    data = base / 'data'
    extension = data / 'gnome-shell/extensions/gnome-radio@local'
    extension.parent.mkdir(parents=True)
    # Install the applet after Shell starts, to test first-install live loading.
    bootstrap = extension.parent / 'radio-test@local'
    bootstrap.mkdir()
    (bootstrap / 'metadata.json').write_text(json.dumps({
        'uuid': 'radio-test@local', 'name': 'Private test bootstrap',
        'description': 'Test-only evaluator access on the disposable bus', 'shell-version': ['49']}))
    (bootstrap / 'extension.js').write_text('''
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
export default class Test extends Extension {
    enable() { global.context.unsafe_mode = true; }
    disable() { global.context.unsafe_mode = false; }
}
''')
    env = dict(os.environ, XDG_RUNTIME_DIR=directory, XDG_DATA_HOME=str(data),
               XDG_CONFIG_HOME=str(base / 'config'), XDG_CACHE_HOME=str(base / 'cache'),
               GSETTINGS_BACKEND='keyfile', GIO_USE_VFS='local',
               GNOME_RADIO_TEST_AUDIO='1', LIBGL_ALWAYS_SOFTWARE='1',
               GST_REGISTRY=str(base / 'gst-registry.bin'))
    subprocess.run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', "['radio-test@local']"],
                   env=env, check=True)
    # The headless virtual pointer starts at (0, 0). Its first motion can trigger
    # the hot corner before reaching a panel button; isolate clicks from that
    # unrelated gesture without changing the user's desktop settings.
    subprocess.run(['gsettings', 'set', 'org.gnome.desktop.interface', 'enable-hot-corners', 'false'],
                   env=env, check=True)
    subprocess.run(['gsettings', 'set', 'org.gnome.desktop.session', 'idle-delay', '0'],
                   env=env, check=True)
    subprocess.run(['gsettings', 'set', 'org.gnome.desktop.screensaver', 'lock-enabled', 'false'],
                   env=env, check=True)
    if env.get('GNOME_RADIO_TEST_THEME') == 'light':
        subprocess.run(['gsettings', 'set', 'org.gnome.desktop.interface', 'color-scheme', 'prefer-light'],
                       env=env, check=True)
    subprocess.run(['dbus-run-session', '--config-file=scripts/test-bus.conf', '--', 'python3', 'tests/e2e/shell.py'],
                   cwd=ROOT, env=env, check=True)
