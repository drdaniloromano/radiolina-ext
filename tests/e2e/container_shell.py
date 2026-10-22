# SPDX-License-Identifier: MIT
"""Exercise the real launcher with fake engines; no daemon or network required."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENGINE = '''#!/usr/bin/env python3
import json, os, signal, sys, time
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['FAKE_CALLS']).open('a') as output:
    output.write(json.dumps(args) + '\\n')
if args == ['--version']:
    print(os.environ.get('FAKE_VERSION', 'podman version 5.7.0'))
elif args[0] == 'info':
    print(os.environ.get('FAKE_SECURITY', '[]'))
elif args[:2] == ['image', 'inspect']:
    print('sha256:fixture-image')
elif args[0] == 'run':
    if os.environ.get('FAKE_RUN_PID'):
        Path(os.environ['FAKE_RUN_PID']).write_text(str(os.getpid()))
        time.sleep(30)
    sys.exit(int(os.environ.get('FAKE_RUN_EXIT', '0')))
elif args[0] == 'rm' and os.environ.get('FAKE_RUN_PID'):
    os.kill(int(Path(os.environ['FAKE_RUN_PID']).read_text()), signal.SIGTERM)
elif args[0] not in ('build', 'rm'):
    sys.exit(99)
'''


class ContainerShellE2E(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='radiolina-container-shell-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'scripts').mkdir()
        for name in ('container-shell.py', 'container-user-flags.sh'):
            shutil.copyfile(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        for name in ('extension', 'src', 'tests'):
            (self.root / name).mkdir()
            (self.root / name / 'fixture').write_text('Allowlisted input\n')
        (self.root / 'LICENSE').write_text('Fixture\n')
        (self.root / 'workspace').mkdir()
        (self.root / 'workspace/private.txt').write_text('Must never be mounted\n')
        self.engine = self.root / 'engine'
        self.engine.write_text(ENGINE)
        self.engine.chmod(0o700)
        self.calls = self.root / 'calls.jsonl'
        self.env = dict(os.environ, FAKE_CALLS=str(self.calls))

    def launch(self, action='test', versions=('49',), extra=()):
        return subprocess.run([sys.executable, 'scripts/container-shell.py', action,
                               '--engine', str(self.engine), '--gnome', *versions, *extra],
                              cwd=self.root, env=self.env, capture_output=True, text=True, timeout=15)

    def commands(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_sequential_versions_private_mounts_and_owned_cleanup(self):
        result = self.launch(versions=('49', '50'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        operations = [args for args in self.commands() if args[0] in ('run', 'rm')]
        self.assertEqual([args[0] for args in operations], ['run', 'rm', 'run', 'rm'])
        for major, command, cleanup in zip(('49', '50'), operations[::2], operations[1::2]):
            for flag in ('--network=none', '--read-only', '--cap-drop=all',
                         '--security-opt=no-new-privileges', '--memory=1g', '--cpus=2', '--pids-limit=256'):
                self.assertIn(flag, command)
            self.assertEqual(cleanup, ['rm', '--force', command[command.index('--name') + 1]])
            mounts = [command[index + 1] for index, value in enumerate(command) if value == '-v']
            self.assertEqual(len(mounts), 6)
            self.assertEqual(sum(mount.endswith(':rw') for mount in mounts), 1)
            for mount in mounts:
                source, target, mode = mount.rsplit(':', 2)
                self.assertNotIn('workspace', source)
                self.assertNotIn('.git', source)
                if target == '/results':
                    self.assertTrue(Path(source).is_relative_to(self.root / 'build/shell-tests' / major))
                    self.assertEqual(mode, 'rw')
                    report = json.loads((Path(source) / 'container.json').read_text())
                    self.assertEqual(report['gnome_major'], major)
                    self.assertFalse(report['release_approved'])
                else:
                    self.assertIn(target, ['/input/' + name for name in ('extension', 'src', 'scripts', 'tests', 'LICENSE')])
                    self.assertEqual(mode, 'ro')
            self.assertNotIn('--privileged', command)

    def test_failed_version_stops_matrix_and_retains_failure_manifest(self):
        self.env['FAKE_RUN_EXIT'] = '7'
        result = self.launch(versions=('49', '50'))
        self.assertEqual(result.returncode, 7, result.stderr)
        operations = [args for args in self.commands() if args[0] in ('run', 'rm')]
        self.assertEqual([args[0] for args in operations], ['run', 'rm'])
        reports = list((self.root / 'build/shell-tests').glob('*/*/container.json'))
        self.assertEqual(len(reports), 1)
        self.assertEqual(json.loads(reports[0].read_text())['exit_code'], 7)

    def test_parallel_invocation_fails_without_starting_a_container(self):
        artifacts = self.root / 'build/shell-tests'
        artifacts.mkdir(parents=True)
        with (artifacts / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('another Shell container', result.stderr)
        self.assertFalse(any(args[0] in ('run', 'build') for args in self.commands()))

    def test_interruption_cleans_up_only_the_owned_container(self):
        pid_file = self.root / 'fake-run.pid'
        self.env['FAKE_RUN_PID'] = str(pid_file)
        process = subprocess.Popen([sys.executable, 'scripts/container-shell.py', 'test',
                                    '--engine', str(self.engine)], cwd=self.root, env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if process.poll() is None:
                process.kill()
                process.wait()
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 5
        while not pid_file.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(pid_file.exists(), 'Fake engine reached the container run')
        process.send_signal(signal.SIGTERM)
        output, error = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 130, output + error)
        operations = [args for args in self.commands() if args[0] in ('run', 'rm')]
        self.assertEqual([args[0] for args in operations], ['run', 'rm'])
        self.assertEqual(operations[1], ['rm', '--force', operations[0][operations[0].index('--name') + 1]])

    def test_engine_specific_refresh_and_identity(self):
        for flavor, pull, identity in (
                ('podman version 5.7.0', '--pull=always', '--userns=keep-id'),
                ('Docker version 28.0.0', '--pull', f'--user={os.getuid()}:{os.getgid()}')):
            with self.subTest(flavor=flavor):
                self.calls.unlink(missing_ok=True)
                self.env['FAKE_VERSION'] = flavor
                result = self.launch(action='build', extra=('--refresh',))
                self.assertEqual(result.returncode, 0, result.stderr)
                build = next(args for args in self.commands() if args[0] == 'build')
                self.assertIn(pull, build)
                self.assertIn('--no-cache', build)
                self.assertIn('FEDORA_VERSION=43', build)
                self.assertIn('GNOME_VERSION=49', build)
                self.assertIn(f'TEST_UID={os.getuid()}', build)
                self.assertIn(f'TEST_GID={os.getgid()}', build)
                result = self.launch()
                self.assertEqual(result.returncode, 0, result.stderr)
                command = next(args for args in self.commands() if args[0] == 'run')
                self.assertIn(identity, command)
        self.env.update(FAKE_VERSION='Docker version 28.0.0', FAKE_SECURITY='["name=rootless"]')
        self.calls.unlink()
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--user=0:0', next(args for args in self.commands() if args[0] == 'run'))

    def test_unknown_profile_and_engine_fail_before_running(self):
        result = self.launch(versions=('999',))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.commands(), [])
        self.env['FAKE_VERSION'] = 'unrecognized engine'
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(args[0] in ('run', 'build') for args in self.commands()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
