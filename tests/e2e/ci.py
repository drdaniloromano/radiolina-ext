# SPDX-License-Identifier: MIT
"""CI boundary E2E: stale/failing runs, cache integrity and artifact privacy."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CiE2E(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='radiolina-ci-check-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ('src', 'extension'):
            shutil.copytree(ROOT / name, self.root / name)
        for name in ('scripts/build.py', 'scripts/ci.py', 'scripts/container-shell.py',
                     'scripts/container-identity.py', 'LICENSE'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, path)
        for name in ('Makefile', 'Dockerfile', 'Dockerfile.shell', 'Dockerfile.aac',
                     '.dockerignore', '.github/ci-image-generation'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('CI fixture\n')
        (self.root / 'tests').mkdir()
        self.state = self.root / 'build/ci'
        self.state.mkdir(parents=True)
        spec = importlib.util.spec_from_file_location('ci_fixture', self.root / 'scripts/ci.py')
        self.ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ci)
        self.ci.ROOT, self.ci.STATE = self.root, self.state

    def command(self, action, **changes):
        env = dict(os.environ, **changes)
        env.pop('GITHUB_ACTIONS', None)
        return subprocess.run([sys.executable, 'scripts/ci.py', action, '--engine', 'podman'],
                              cwd=self.root, env=env, capture_output=True, text=True)

    def test_missing_failed_and_stale_results_cannot_package(self):
        destination = self.state / 'artifacts/package'
        destination.mkdir(parents=True)
        (destination / 'stale.zip').write_bytes(b'stale')
        result = self.command('package')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(destination.exists())
        for passed, fingerprint in ((False, self.ci.source_id()), (True, 'old source')):
            (self.state / 'test-49.json').write_text(json.dumps({
                'passed': passed, 'source_sha256': fingerprint}))
            result = self.command('package')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('All current profile tests must pass', result.stderr)
            self.assertFalse(destination.exists())

    def test_real_zip_verification_rejects_extra_or_changed_sources(self):
        subprocess.run([sys.executable, 'scripts/build.py'], cwd=self.root,
                       check=True, capture_output=True)
        bundle = next((self.root / 'build').glob('*.zip'))
        self.assertEqual(len(self.ci.verify_bundle(bundle)), 64)
        (self.root / 'src/core/ci-corruption.js').write_text('changed source')
        with self.assertRaisesRegex(ValueError, 'unexpected files'):
            self.ci.verify_bundle(bundle)
        (self.root / 'src/core/ci-corruption.js').unlink()
        import zipfile
        with zipfile.ZipFile(bundle, 'a') as archive:
            archive.writestr('workspace/private.txt', 'must not ship')
        with self.assertRaisesRegex(ValueError, 'unexpected files'):
            self.ci.verify_bundle(bundle)

    def test_evidence_is_allowlisted_bounded_and_redacts_urls(self):
        (self.root / 'workspace').mkdir()
        (self.root / 'workspace/stations.json').write_text('PRIVATE_STATION_MARKER')
        (self.state / 'service-49.log').write_text('failure https://user:secret@example.test/live\n')
        (self.state / 'private.txt').write_text('PRIVATE_STATE_MARKER')
        self.ci.run = lambda *_args, **_kwargs: 'fixture commit'
        self.ci.evidence(None)
        files = list((self.state / 'artifacts/test-evidence').glob('*'))
        content = b''.join(path.read_bytes() for path in files)
        self.assertIn(b'<url>', content)
        for private in (b'PRIVATE_STATION_MARKER', b'PRIVATE_STATE_MARKER', b'user:secret'):
            self.assertNotIn(private, content)
        run = self.root / 'build/shell-tests/49/failed-run'
        (run / 'evidence').mkdir(parents=True)
        screenshot = run / 'evidence/shell-final.png'
        screenshot.write_bytes(b'fixture failure screenshot')
        (run / 'evidence/stations.json').write_text('PRIVATE_FAILURE_STATIONS')
        (self.state / 'test-49.json').write_text(json.dumps({
            'passed': False, 'runs': [str(run.relative_to(self.root))]}))
        self.ci.evidence(None)
        files = list((self.state / 'artifacts/test-evidence').glob('*'))
        self.assertTrue(any(p.name.endswith('shell-final.png') for p in files))
        self.assertNotIn(b'PRIVATE_FAILURE_STATIONS', b''.join(p.read_bytes() for p in files))
        (self.state / 'test-49.json').write_text(json.dumps({'runs': ['workspace']}))
        with self.assertRaisesRegex(ValueError, 'Unexpected evidence directory'):
            self.ci.evidence(None)

    def fake_tools(self):
        directory = self.root / 'bin'
        directory.mkdir()
        engine = directory / 'podman'
        engine.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with Path(os.environ['FAKE_CALLS']).open('a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
args=sys.argv[1:]
if args == ['--version']: print('podman version fixture')
elif args[:2] == ['image','inspect']: print('sha256:' + '1'*64)
elif args[:1] == ['save']: sys.stdout.buffer.write(b'fake image layer')
elif args[:1] == ['run']: print('gnome-shell-fixture')
''')
        engine.chmod(0o755)
        make = directory / 'make'
        make.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with Path(os.environ['FAKE_CALLS']).open('a') as f:
    f.write(json.dumps(['make', *sys.argv[1:]]) + '\\n')
sys.exit(int(os.environ.get('FAKE_MAKE_FAIL', '0')))
''')
        make.chmod(0o755)
        return {'PATH': str(directory) + os.pathsep + os.environ['PATH'],
                'FAKE_CALLS': str(self.root / 'calls.jsonl')}

    def test_cache_hit_refresh_corruption_and_failed_service_cleanup(self):
        env = self.fake_tools()
        cold = self.command('image', **env)
        self.assertEqual(cold.returncode, 0, cold.stderr)
        warm = self.command('image', **env)
        self.assertEqual(warm.returncode, 0, warm.stderr)
        self.assertEqual(json.loads((self.state / 'image-49.json').read_text())['origin'], 'cache')
        refreshed = subprocess.run([sys.executable, 'scripts/ci.py', 'image', '--refresh'],
            cwd=self.root, env=dict(os.environ, **env), capture_output=True, text=True)
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        calls = [json.loads(row) for row in (self.root / 'calls.jsonl').read_text().splitlines()]
        self.assertTrue(any(row[:2] == ['make', 'container-shell-refresh'] for row in calls))
        self.assertTrue(any(row[:1] == ['load'] for row in calls))
        with (self.root / 'build/ci-cache/49/image.tar.gz').open('ab') as f:
            f.write(b'corruption')
        bad = self.command('image', **env)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('cache integrity/input mismatch', bad.stderr)
        failed = self.command('test', **env, FAKE_MAKE_FAIL='7')
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse(json.loads((self.state / 'test-49.json').read_text())['passed'])
        calls = [json.loads(row) for row in (self.root / 'calls.jsonl').read_text().splitlines()]
        self.assertTrue(any(row[:2] == ['rm', '--force'] and
                            row[2].startswith('radiolina-ci-service-') for row in calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
