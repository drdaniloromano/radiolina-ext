# SPDX-License-Identifier: MIT
"""Final-ZIP check boundaries with a local container-engine fixture."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('package_check', ROOT / 'scripts/check-package.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PackageCheckE2E(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='radiolina-package-e2e-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / 'extension.zip'
        self.bundle.write_bytes(b'ZIP fixture: engine output is mocked, never the checked boundary')
        self.output = self.root / 'reports'
        self.report = {'spec_version': '2026-04-02', 'findings': [],
                       'summary': {'status': 'clean', 'finding_count': 0, 'severity_counts': {}},
                       'artifacts': {'file_count': 25, 'js_file_count': 2}}
        self.exit_code = 0
        self.calls = []

    def run_engine(self, command, **kwargs):
        self.calls.append(command)
        if 'run' in command:
            mount = command[command.index('-v') + 1]
            snapshot = Path(mount.split(':/input/')[0])
            self.assertEqual(snapshot.read_bytes(), self.bundle.read_bytes())
            self.assertNotIn('workspace', snapshot.parts)
            return subprocess.CompletedProcess(command, self.exit_code,
                                               json.dumps(self.report).encode(), b'')
        return subprocess.CompletedProcess(command, 0)

    def analyze(self):
        with patch.object(checker.subprocess, 'run', side_effect=self.run_engine), \
                patch.object(checker.subprocess, 'check_output', return_value='sha256:fixture\n'):
            return checker.check_package('podman', self.bundle, self.output)

    def finding(self, severity):
        self.report['findings'] = [{'rule_id': 'EGO-fixture', 'severity': severity,
                                    'message': 'Fixture finding', 'evidence': []}]
        self.report['summary'] = {'status': 'issues_found', 'finding_count': 1,
                                  'severity_counts': {severity: 1}}

    def test_actual_package_snapshot_is_only_mount_and_analysis_is_offline_and_bounded(self):
        summary = self.analyze()
        self.assertEqual(summary['status'], 'clean')
        self.assertFalse(summary['release_approved'])
        command = next(command for command in self.calls if command[1] == 'run')
        self.assertIn('--network=none', command)
        self.assertIn('--read-only', command)
        self.assertIn('--memory=512m', command)
        self.assertIn('--pids-limit=64', command)
        self.assertEqual(command.count('-v'), 1)
        self.assertEqual({p.name for p in self.output.iterdir()},
                         {'report.json', 'summary.json', 'stderr.log'})

    def test_zero_cli_exit_does_not_hide_errors_or_manual_findings(self):
        self.finding('error')
        with self.assertRaisesRegex(ValueError, 'errors block'):
            self.analyze()
        self.assertEqual(json.loads((self.output / 'summary.json').read_text())['errors'], 1)
        for severity in ('warning', 'manual_review'):
            self.finding(severity)
            result = self.analyze()
            self.assertTrue(result['review_required'])
            self.assertEqual(result['status'], 'issues_found')
            self.assertFalse(result['release_approved'])

    def test_crashes_and_incomplete_or_unknown_reports_fail_without_stale_success(self):
        self.analyze()
        self.exit_code = 139
        with self.assertRaisesRegex(ValueError, 'did not complete'):
            self.analyze()
        self.assertFalse((self.output / 'summary.json').exists())
        self.exit_code = 0
        for field, value in (('spec_version', 'future'), ('summary', {}), ('findings', None),
                             ('artifacts', {'file_count': 25, 'js_file_count': 0})):
            original = copy.deepcopy(self.report)
            self.report[field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                self.analyze()
            self.report = original
        self.finding('unknown-severity')
        with self.assertRaises(ValueError):
            self.analyze()

    def test_unrelated_outputs_and_oversized_inputs_are_preserved_and_rejected(self):
        self.output.mkdir()
        private = self.output / 'private.txt'
        private.write_text('Preserve unrelated files')
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            self.analyze()
        self.assertEqual(private.read_text(), 'Preserve unrelated files')
        self.bundle.write_bytes(b'x' * (checker.LIMIT + 1))
        with self.assertRaisesRegex(ValueError, '5 MiB'):
            self.analyze()
        self.assertFalse(self.calls)

    def test_timeout_removes_only_the_owned_analysis_container(self):
        original = self.run_engine

        def timeout(command, **kwargs):
            if command[1] == 'run':
                self.calls.append(command)
                raise subprocess.TimeoutExpired(command, 120)
            return original(command, **kwargs)

        with patch.object(checker.subprocess, 'run', side_effect=timeout), \
                patch.object(checker.subprocess, 'check_output', return_value='sha256:fixture\n'):
            with self.assertRaises(subprocess.TimeoutExpired):
                checker.check_package('podman', self.bundle, self.output)
        command = next(command for command in self.calls if command[1] == 'run')
        name = command[command.index('--name') + 1]
        self.assertTrue(name.startswith('radiolina-package-check-'))
        self.assertEqual(self.calls[-1], ['podman', 'rm', '--force', name])
        self.assertFalse((self.output / 'summary.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
