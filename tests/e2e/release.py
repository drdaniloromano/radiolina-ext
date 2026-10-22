# SPDX-License-Identifier: MIT
"""Release build/upload E2E with real Git/ZIPs and an offline GitHub API boundary."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import release as release_tools


class FakeGitHub:
    repository = 'fixture/radiolina'

    def __init__(self, commit):
        self.commit = commit
        self.calls = []
        self.annotated = False
        self.runs = [{'id': 17, 'head_sha': commit, 'event': 'push', 'head_branch': 'main',
                      'head_repository': {'full_name': self.repository},
                      'status': 'completed', 'conclusion': 'success'}]
        self.release = {'id': 31, 'assets': [], 'immutable': False}

    def request(self, path, **options):
        self.calls.append((path, options))
        if path.startswith('git/ref/tags/'):
            return {'object': {'type': 'tag', 'sha': 'a' * 40} if self.annotated else
                    {'type': 'commit', 'sha': self.commit}}
        if path == 'git/tags/' + 'a' * 40:
            return {'object': {'type': 'commit', 'sha': self.commit}}
        if path.startswith('actions/workflows/ci.yml/runs?'):
            return {'workflow_runs': self.runs}
        if path.startswith('releases/tags/'):
            return self.release
        if path.startswith('releases/31/assets?name=') and options.get('upload'):
            from urllib.parse import unquote
            data = options['data']
            asset = {'id': 100 + len(self.release['assets']), 'name': unquote(path.split('name=')[1]),
                     'size': len(data), 'state': 'uploaded', 'digest': 'sha256:' + release_tools.sha(data)}
            self.release['assets'].append(asset)
            return asset
        raise AssertionError('Unexpected GitHub operation: ' + path)


class ReleaseE2E(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='radiolina-release-e2e-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repo'
        self.root.mkdir()
        for name in ('src', 'extension', 'scripts', 'tests', '.github'):
            shutil.copytree(ROOT / name, self.root / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('LICENSE', 'Makefile', 'Dockerfile', 'Dockerfile.shell', 'Dockerfile.aac', 'Dockerfile.shexli',
                     '.dockerignore', '.gitignore'):
            shutil.copyfile(ROOT / name, self.root / name)
        self.git('init', '--quiet', '--initial-branch=main')
        for key, value in (('user.name', 'Fixture'), ('user.email', 'fixture@example.test'),
                           ('commit.gpgsign', 'false'), ('tag.gpgsign', 'false'),
                           ('core.hooksPath', '/dev/null')):
            self.git('config', key, value)
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'Reviewed source fixture')
        self.commit = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', self.commit)
        self.tag = 'v' + json.loads((self.root / 'extension/metadata.json').read_text())['version-name']
        self.git('tag', '-a', self.tag, '-m', 'Fixture version')
        subprocess.run([sys.executable, 'scripts/build.py'], cwd=self.root, check=True, capture_output=True)
        bundle = self.root / 'build' / release_tools.FILES[0]
        self.expected_payload = release_tools.ci.verify_bundle(bundle, self.root)
        self.api = FakeGitHub(self.commit)
        self.output = Path(self.temporary.name) / 'approved'
        self.previous_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.previous_cwd)

    def git(self, *arguments):
        return subprocess.check_output(['git', '-C', str(self.root), *arguments], text=True,
                                       stderr=subprocess.DEVNULL).strip()

    def test_real_tag_is_built_and_verified_without_old_artifacts_and_retries_are_identical(self):
        self.api.annotated = True
        release_tools.prepare(self.api, self.tag, self.output)
        self.assertEqual(self.git('worktree', 'list', '--porcelain').count('worktree '), 1)
        files = {name: (self.output / name).read_bytes() for name in release_tools.FILES}
        metadata = json.loads(files['verification.json'])
        self.assertEqual(metadata['package_payload_sha256'],
                         self.expected_payload)
        self.assertFalse(metadata['release_approved'])
        self.assertIn('not run in GNOME', metadata['verification_scope'])
        self.assertFalse(any('artifacts' in path for path, _ in self.api.calls))
        release_tools.attach(self.api, self.tag, self.output, dry_run=True)
        self.assertFalse(any('data' in options for _, options in self.api.calls))
        release_tools.attach(self.api, self.tag, self.output)
        writes = [(path, options) for path, options in self.api.calls if 'data' in options]
        self.assertEqual(len(writes), 3)
        self.assertEqual({item['name'] for item in self.api.release['assets']}, set(release_tools.FILES))
        for _, options in writes:
            self.assertIn(options['data'], files.values())
        # Fresh worktree and different timestamps still produce identical assets.
        retry = self.output.with_name('retry')
        release_tools.prepare(self.api, self.tag, retry)
        self.assertEqual({name: (retry / name).read_bytes() for name in release_tools.FILES}, files)
        release_tools.attach(self.api, self.tag, retry)
        self.assertEqual(sum('data' in options for _, options in self.api.calls), 3)

    def test_wrong_failed_pending_or_foreign_main_checks_cannot_build(self):
        mutations = [lambda a: a.runs.clear(),
                     lambda a: a.runs[0].update(conclusion='failure'),
                     lambda a: a.runs[0].update(status='in_progress', conclusion=None),
                     lambda a: a.runs[0].update(event='pull_request'),
                     lambda a: a.runs[0].update(head_sha='f' * 40),
                     lambda a: a.runs[0]['head_repository'].update(full_name='foreign/repo'),
                     lambda a: a.runs.append(dict(a.runs[0], id=18, conclusion='failure'))]
        for change in mutations:
            api = FakeGitHub(self.commit)
            change(api)
            with self.subTest(change=change), self.assertRaises(release_tools.ReleaseError):
                release_tools.prepare(api, self.tag, self.output)
            self.assertFalse(self.output.exists())
            self.assertFalse(any('data' in options for _, options in api.calls))

    def test_unreviewed_tags_and_mismatched_versions_are_rejected(self):
        self.git('commit', '--allow-empty', '--quiet', '-m', 'Unmerged fixture')
        unmerged = self.git('rev-parse', 'HEAD')
        self.git('tag', 'v999.0.0')
        with self.assertRaises(subprocess.CalledProcessError):
            release_tools.prepare(FakeGitHub(unmerged), 'v999.0.0', self.output)
        self.git('update-ref', 'refs/remotes/origin/main', unmerged)
        with self.assertRaisesRegex(release_tools.ReleaseError, 'metadata'):
            release_tools.prepare(FakeGitHub(unmerged), 'v999.0.0', self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.git('worktree', 'list', '--porcelain').count('worktree '), 1)

    def test_tagged_build_scripts_are_not_executed_and_bad_packages_are_rejected(self):
        (self.root / 'scripts/build.py').write_text('raise RuntimeError("Untrusted tagged builder")')
        self.git('add', 'scripts/build.py')
        self.git('commit', '--quiet', '-m', 'Different historical build tooling')
        commit = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', commit)
        self.git('tag', '--force', self.tag)
        api = FakeGitHub(commit)
        release_tools.prepare(api, self.tag, self.output)
        self.assertTrue((self.output / release_tools.FILES[0]).is_file())
        with patch.object(release_tools.ci, 'verify_bundle', side_effect=ValueError('Bad payload')):
            with self.assertRaises(ValueError):
                release_tools.prepare(api, self.tag, self.output.with_name('invalid-payload'))
        self.assertEqual(self.git('worktree', 'list', '--porcelain').count('worktree '), 1)
        # Never admit private files or paths that point outside the tagged checkout.
        (self.root / 'src/unsafe').symlink_to('/etc/passwd')
        self.git('add', 'src/unsafe')
        self.git('commit', '--quiet', '-m', 'Invalid source fixture')
        commit = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', commit)
        self.git('tag', '--force', self.tag)
        with self.assertRaisesRegex(release_tools.ReleaseError, 'symlinks'):
            release_tools.prepare(FakeGitHub(commit), self.tag,
                              self.output.with_name('invalid-link'))

    def test_existing_conflicts_moved_tags_immutable_releases_and_staging_changes_never_overwrite(self):
        release_tools.prepare(self.api, self.tag, self.output)
        for mode in ('conflict', 'moved', 'immutable', 'staging'):
            api = FakeGitHub(self.commit)
            if mode == 'conflict':
                api.release['assets'] = [{'name': 'verification.json', 'id': 45, 'state': 'uploaded',
                                          'size': (self.output / 'verification.json').stat().st_size,
                                          'digest': 'sha256:' + 'f' * 64}]
            elif mode == 'moved':
                api.commit = 'f' * 40
            elif mode == 'immutable':
                api.release['immutable'] = True
            else:
                (self.output / 'verification.json').write_bytes(b'{}')
            with self.subTest(mode=mode), self.assertRaises((release_tools.ReleaseError, KeyError)):
                release_tools.attach(api, self.tag, self.output)
            self.assertFalse(any('data' in options for _, options in api.calls))

    def test_staging_file_version_checksum_and_size_bounds_are_enforced(self):
        release_tools.prepare(self.api, self.tag, self.output)
        originals = {name: (self.output / name).read_bytes() for name in release_tools.FILES}
        modes = ('extra', 'checksum', 'oversized', 'symlink', 'manifest')
        for mode in modes:
            with self.subTest(mode=mode):
                directory = self.output.with_name(mode)
                directory.mkdir()
                for name, data in originals.items():
                    (directory / name).write_bytes(data)
                if mode == 'extra':
                    (directory / 'private.txt').write_text('private fixture')
                elif mode == 'checksum':
                    (directory / 'SHA256SUMS').write_text('wrong')
                elif mode == 'oversized':
                    (directory / 'SHA256SUMS').write_bytes(b'x' * (release_tools.LIMIT + 1))
                elif mode == 'symlink':
                    (directory / 'SHA256SUMS').unlink()
                    (directory / 'SHA256SUMS').symlink_to(self.output / 'SHA256SUMS')
                else:
                    metadata = json.loads(originals['verification.json'])
                    metadata['source_commit'] = 'f' * 40
                    (directory / 'verification.json').write_text(json.dumps(metadata))
                with self.assertRaises(release_tools.ReleaseError):
                    release_tools.verify_files(directory, self.tag, self.commit)

    def test_invalid_tag_inputs_and_cross_host_redirects_cannot_expose_credentials(self):
        for tag in ('main', 'v01.2.3', 'v1.2.3;echo bad', 'v1.2.3\n', '../v1.2.3'):
            with self.assertRaises(release_tools.ReleaseError):
                release_tools.version_tag(tag)
        request = Request('https://api.github.com/repos/fixture/radiolina/actions/artifacts/1/zip',
                          headers={'Authorization': 'Bearer private-fixture'})
        redirected = release_tools.SafeRedirect().redirect_request(
            request, None, 302, 'Found', {}, 'https://artifact.example.test/signed')
        self.assertIsNone(redirected.get_header('Authorization'))

    def test_api_download_media_types_upload_host_and_response_bounds(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *arguments):
                self.close()

        class Opener:
            def __init__(self):
                self.requests = []
                self.response = b'fixture bytes'

            def open(self, request, timeout):
                self.requests.append(request)
                return Response(self.response)

        api = release_tools.GitHub('fixture/radiolina', 'private-fixture')
        api.opener = Opener()
        api.request('actions/artifacts/23/zip', binary=True)
        self.assertEqual(api.opener.requests[-1].get_header('Accept'), 'application/vnd.github+json')
        api.request('releases/assets/23', binary=True)
        self.assertEqual(api.opener.requests[-1].get_header('Accept'), 'application/octet-stream')
        api.opener.response = b'{}'
        api.request('releases/31/assets?name=fixture.zip', data=b'zip', upload=True)
        request = api.opener.requests[-1]
        self.assertEqual(request.host, 'uploads.github.com')
        self.assertEqual(request.get_method(), 'POST')
        api.opener.response = b'x' * (release_tools.LIMIT + 1)
        with self.assertRaisesRegex(release_tools.ReleaseError, 'size limit'):
            api.request('actions/artifacts/23/zip', binary=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
