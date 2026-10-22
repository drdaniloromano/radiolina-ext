#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a small self-contained source extension; never installs it on the host."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile


def oom_score(value):
    if value == 'inherit':
        return None
    try:
        score = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('use an integer from 0 to 1000, or inherit') from None
    if not 0 <= score <= 1000:
        raise argparse.ArgumentTypeError('use an integer from 0 to 1000, or inherit')
    return score


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--oom-score-adj', type=oom_score, default=500, metavar='0..1000|inherit',
                    help='playback-service kernel OOM adjustment (default: 500; inherit disables adjustment)')
parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1],
                    help='source tree to package (default: repository root)')
parser.add_argument('--build-dir', type=Path, help='output directory (default: SOURCE_ROOT/build)')
args = parser.parse_args()

ROOT = args.source_root.resolve()
BUILD = args.build_dir.resolve() if args.build_dir else ROOT / 'build'
metadata = json.loads((ROOT / 'extension/metadata.json').read_text())
UUID = metadata['uuid']
destination = BUILD / UUID
if destination.exists():
    shutil.rmtree(destination)
shutil.copytree(ROOT / 'extension', destination)
shutil.copytree(ROOT / 'src', destination / 'src')
(destination / 'src/service/build-config.js').write_text(
    '// SPDX-License-Identifier: MIT\n'
    '// Build-time playback-service policy; null preserves the inherited setting.\n'
    f'export const OOM_SCORE_ADJ = {json.dumps(args.oom_score_adj)};\n')
shutil.copyfile(ROOT / 'LICENSE', destination / 'LICENSE')
source = (destination / 'extension.js').read_bytes()
styles = (destination / 'stylesheet.css').read_bytes()
stylesheet = f'radio-style-{hashlib.sha256(styles).hexdigest()[:12]}.css'
(destination / stylesheet).write_bytes(styles)
# Replace older installed styles; the extension loads its versioned CSS directly.
(destination / 'stylesheet.css').write_text('/* SPDX-License-Identifier: MIT */\n'
                                           '/* Layout is loaded from the versioned radio stylesheet. */\n')
runtime_hash = hashlib.sha256(source + b'\0' + styles).hexdigest()[:12]
runtime = f'radio-{runtime_hash}.js'
(destination / runtime).write_bytes(source)
(destination / 'extension.js').write_text('// SPDX-License-Identifier: MIT\n'
                                         f"export {{default}} from './{runtime}';\n")
metadata['radio-runtime'] = runtime
metadata['radio-stylesheet'] = stylesheet
(destination / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
with zipfile.ZipFile(BUILD / f'{UUID}.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(destination.rglob('*')):
        if path.is_file():
            archive.write(path, path.relative_to(destination))
print(f'Built {BUILD / (UUID + ".zip")}')
