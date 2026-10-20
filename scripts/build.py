#!/usr/bin/env python3
"""Build a small self-contained source extension; never installs it on the host."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
UUID = 'gnome-radio@local'
destination = BUILD / UUID
if destination.exists():
    shutil.rmtree(destination)
shutil.copytree(ROOT / 'extension', destination)
shutil.copytree(ROOT / 'src', destination / 'src')
source = (destination / 'extension.js').read_bytes()
styles = (destination / 'stylesheet.css').read_bytes()
stylesheet = f'radio-style-{hashlib.sha256(styles).hexdigest()[:12]}.css'
(destination / stylesheet).write_bytes(styles)
# Replace older installed styles; the extension loads its versioned CSS directly.
(destination / 'stylesheet.css').write_text('/* Layout is loaded from the versioned radio stylesheet. */\n')
runtime_hash = hashlib.sha256(source + b'\0' + styles).hexdigest()[:12]
runtime = f'radio-{runtime_hash}.js'
(destination / runtime).write_bytes(source)
(destination / 'extension.js').write_text(f"export {{default}} from './{runtime}';\n")
metadata = json.loads((destination / 'metadata.json').read_text())
metadata['radio-runtime'] = runtime
metadata['radio-stylesheet'] = stylesheet
(destination / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
with zipfile.ZipFile(BUILD / f'{UUID}.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(destination.rglob('*')):
        if path.is_file():
            archive.write(path, path.relative_to(destination))
print(f'Built {BUILD / (UUID + ".zip")}')
