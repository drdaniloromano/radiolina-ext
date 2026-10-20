# SPDX-License-Identifier: MIT
"""Build the real release ZIP in a temporary checkout and check its contents."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]


class PackageE2E(unittest.TestCase):
    def test_licensed_source_package_excludes_private_and_development_files(self):
        with tempfile.TemporaryDirectory(prefix='gnome-radio-package-') as directory:
            checkout = Path(directory)
            for name in ('extension', 'src'):
                shutil.copytree(ROOT / name, checkout / name)
            (checkout / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'scripts/build.py', checkout / 'scripts/build.py')
            shutil.copyfile(ROOT / 'LICENSE', checkout / 'LICENSE')
            for name in ('workspace/private.txt', '.git/config', '.aws',
                         'tests/development.py', 'README.md', 'AGENTS.md'):
                path = checkout / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('Packaging exclusion fixture\n')

            result = subprocess.run([sys.executable, 'scripts/build.py'], cwd=checkout,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            metadata = json.loads((checkout / 'extension/metadata.json').read_text())
            with zipfile.ZipFile(checkout / 'build' / f'{metadata["uuid"]}.zip') as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read('LICENSE'), (ROOT / 'LICENSE').read_bytes())
                self.assertTrue(archive.read('LICENSE').startswith(b'MIT License\n'))
                packaged = json.loads(archive.read('metadata.json'))
                sources = {str(path.relative_to(checkout / 'extension')): path
                           for path in (checkout / 'extension').rglob('*') if path.is_file()}
                sources.update({'src/' + str(path.relative_to(checkout / 'src')): path
                                for path in (checkout / 'src').rglob('*') if path.is_file()})
                self.assertEqual(set(archive.namelist()), set(sources) | {
                    'LICENSE', packaged['radio-runtime'], packaged['radio-stylesheet']})
                for name, source in sources.items():
                    if name not in ('extension.js', 'stylesheet.css', 'metadata.json'):
                        self.assertEqual(archive.read(name), source.read_bytes(), name)
                self.assertEqual(archive.read(packaged['radio-runtime']),
                                 (checkout / 'extension/extension.js').read_bytes())
                self.assertEqual(archive.read(packaged['radio-stylesheet']),
                                 (checkout / 'extension/stylesheet.css').read_bytes())
                for name in ('extension.js', 'stylesheet.css'):
                    self.assertIn(b'SPDX-License-Identifier: MIT', archive.read(name))


if __name__ == '__main__':
    unittest.main(verbosity=2)
