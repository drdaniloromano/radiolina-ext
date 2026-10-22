# SPDX-License-Identifier: MIT
"""Exercise image account creation without host files or account tools."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class IdentityE2E(unittest.TestCase):
    def test_unknown_numeric_user_is_added_idempotently_without_changing_existing_accounts(self):
        with tempfile.TemporaryDirectory(prefix='radiolina-identity-') as directory:
            base = Path(directory)
            (base / 'etc').mkdir()
            passwd, group = base / 'etc/passwd', base / 'etc/group'
            passwd.write_text('root:x:0:0:root:/root:/bin/sh\n')
            group.write_text('root:x:0:\n')
            command = [sys.executable, str(ROOT / 'scripts/container-identity.py'),
                       '1001', '1002', '--root', str(base)]
            subprocess.run(command, check=True)
            self.assertIn('radiolina-test-1001:x:1001:1002:', passwd.read_text())
            self.assertIn('radiolina-test-1002:x:1002:', group.read_text())
            original = passwd.read_bytes(), group.read_bytes()
            subprocess.run(command, check=True)
            self.assertEqual((passwd.read_bytes(), group.read_bytes()), original)
            subprocess.run([*command[:2], '0', '0', '--root', str(base)], check=True)
            self.assertEqual((passwd.read_bytes(), group.read_bytes()), original)
            for invalid in ('-1', 'invalid', '4294967295'):
                result = subprocess.run([*command[:2], invalid, '1002', '--root', str(base)],
                                        capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((passwd.read_bytes(), group.read_bytes()), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
