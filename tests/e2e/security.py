# SPDX-License-Identifier: MIT
"""Offline command-boundary tests for advisory coverage and release reporting."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FAKE = r'''#!/usr/bin/python3
import json, os
from pathlib import Path
import sys
args = sys.argv[1:]
tool = Path(sys.argv[0]).name
mode = os.environ['RADIO_SECURITY_TEST_MODE']
with open(os.environ['RADIO_SECURITY_TEST_CALLS'], 'a') as out:
    out.write(json.dumps([tool, *args]) + '\n')
assert not any(a in ('install', 'upgrade', 'distro-sync', '--assumeyes') for a in args)
if tool == 'rpm':
    if '-qf' in args: print('gstreamer1-plugins-good')
    elif mode != 'empty-inventory':
        for name in args[args.index('--qf') + 2:]:
            print('\t'.join([name, '0', '1.0', '1.fc43', 'x86_64', 'Fedora Project']))
elif tool == 'gjs':
    print(json.dumps({'elements':[{'name':'mpg123audiodec'}] if mode == 'bad-factory' else
                                [{'name':'mpg123audiodec', 'file':'/usr/lib64/libgstmpg123.so'}]}))
elif '--version' in args:
    print('dnf5 test fixture')
elif 'repoquery' in args:
    assert '--disable-repo=*' in args
    print('mpg123-libs')
elif 'repo' in args:
    repos = [{'id':'fedora','is_enabled':True}, {'id':'updates','is_enabled':True}]
    if 'list' in args:
        print(json.dumps([] if mode == 'no-repos' else repos[:1] if mode == 'no-updates' else repos))
    else:
        repo = next(a.split('=',1)[1] for a in args if a.startswith('--repo='))
        if mode == 'partial' and repo == 'updates':
            sys.stderr.write('Synthetic repository unavailable')
            sys.exit(1)
        cache = next(a.split('=',2)[2] for a in args if a.startswith('--setopt=cachedir='))
        metadata = Path(cache,repo+'-fixture','repodata'); metadata.mkdir(parents=True)
        kind = 'primary' if mode == 'missing-feed' else 'updateinfo'
        (metadata/'repomd.xml').write_text('<repomd><data type="'+kind+'"/></repomd>')
        if kind == 'updateinfo' and mode != 'undownloaded-feed':
            (metadata/'updateinfo.xml').write_text('<updates/>')
        print(json.dumps([{'id':repo,'is_enabled':True,'timestamp':1}]))
else:
    assert 'advisory' in args and '--assumeno' in args and '--security' in args
    if mode == 'malformed': print('{"unexpected":1}')
    elif mode == 'empty-object': print('{}')
    elif '--available' in args and mode in ('finding', 'finding-map', 'partial'):
        row = {'Name':'FEDORA-fixture', 'Type':'security', 'Severity':'Important',
            'collections':{'packages':['mpg123-libs-0:1.1-1.fc43.x86_64']},
            'references':[{'Id':'CVE-2099-0001','Type':'cve'}]}
        print(json.dumps({'FEDORA-fixture':row} if mode == 'finding-map' else [row]))
    else: print('[]')
'''


class SecurityE2E(unittest.TestCase):
    def run_check(self, mode):
        directory = tempfile.TemporaryDirectory(prefix='radiolina-security-e2e-')
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        for tool in ('dnf5', 'rpm', 'gjs'):
            file = base / tool
            file.write_text(FAKE)
            file.chmod(0o755)
        report = base / 'report.json'
        # Only the OS identity is mocked; the CLI, command graph, report writer
        # and subprocess error handling execute through real process boundaries.
        identity = {'ID': 'other' if mode == 'unsupported' else 'fedora', 'VERSION_ID': '43',
                    'SUPPORT_END': '2000-01-01' if mode == 'expired' else '2099-01-01'}
        bootstrap = (
            'import importlib.util,sys; '
            f's=importlib.util.spec_from_file_location("security",{str(ROOT / "scripts/security-check.py")!r}); '
            'm=importlib.util.module_from_spec(s);s.loader.exec_module(m); '
            f'm.os_release=lambda:{identity!r}; '
            'sys.exit(m.main())')
        calls = base / 'calls.jsonl'
        result = subprocess.run([sys.executable, '-c', bootstrap, '--output', str(report)],
            env=dict(os.environ, PATH=str(base) + os.pathsep + os.environ['PATH'],
                     RADIO_SECURITY_TEST_MODE=mode, RADIO_SECURITY_TEST_CALLS=str(calls)),
            capture_output=True, text=True, timeout=20)
        self.assertTrue(report.exists(), result.stderr)
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        return result, json.loads(report.read_text()), [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []

    def test_vendor_success_is_scoped_and_never_approves_release(self):
        for mode in ('complete', 'empty-object'):
            with self.subTest(mode=mode):
                result, report, calls = self.run_check(mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(report['status'], 'no-outstanding-vendor-advisories')
                self.assertFalse(report['release_approved'])
                self.assertEqual(report['manual_review']['status'], 'required')
                self.assertIn('mpg123-libs', [p['name'] for p in report['packages']])
                self.assertTrue(report['coverage']['vendor_query_completed_at'])
                self.assertTrue(all('--assumeno' in c and '--no-plugins' in c for c in calls if c[0] == 'dnf5'))

    def test_findings_and_partial_failures_remain_visible(self):
        for mode, code, status in [('finding', 1, 'vendor-advisories-found'),
                                   ('finding-map', 1, 'vendor-advisories-found'), ('partial', 2, 'incomplete')]:
            with self.subTest(mode=mode):
                result, report, _ = self.run_check(mode)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(report['status'], status)
                self.assertEqual(report['vendor_results']['available'][0]['Name'], 'FEDORA-fixture')
                self.assertFalse(report['release_approved'])

    def test_missing_inventory_repositories_feeds_or_valid_json_cannot_pass(self):
        for mode in ('empty-inventory', 'bad-factory', 'no-repos', 'missing-feed', 'undownloaded-feed',
                     'malformed', 'unsupported', 'expired', 'no-updates'):
            with self.subTest(mode=mode):
                result, report, _ = self.run_check(mode)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(report['status'], 'incomplete')
                self.assertTrue(report['coverage']['issues'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
