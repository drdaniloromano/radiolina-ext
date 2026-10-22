# SPDX-License-Identifier: MIT
"""Release promotion E2E with real Git/ZIPs and an offline GitHub API boundary."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.request import Request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import release as promotion


class FakeGitHub:
    repository = 'fixture/radiolina'

    def __init__(self, commit, artifact):
        self.commit, self.artifact = commit, artifact
        self.calls = []
        self.annotated = False
        self.runs = [{'id': 17, 'head_sha': commit, 'event': 'push', 'head_branch': 'main',
                      'head_repository': {'full_name': self.repository},
                      'status': 'completed', 'conclusion': 'success'}]
        self.artifacts = [{'id': 23, 'name': 'radiolina-install-' + commit, 'expired': False,
                           'size_in_bytes': len(artifact), 'digest': 'sha256:' + promotion.sha(artifact)}]
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
        if path == 'actions/runs/17/artifacts?per_page=100':
            return {'artifacts': self.artifacts}
        if path == 'actions/artifacts/23/zip':
            return self.artifact
        if path.startswith('releases/tags/'):
            return self.release
        if path.startswith('releases/31/assets?name=') and options.get('upload'):
            from urllib.parse import unquote
            data = options['data']
            asset = {'id': 100 + len(self.release['assets']), 'name': unquote(path.split('name=')[1]),
                     'size': len(data), 'state': 'uploaded', 'digest': 'sha256:' + promotion.sha(data)}
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
        for name in ('LICENSE', 'Makefile', 'Dockerfile', 'Dockerfile.shell', 'Dockerfile.aac',
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
        bundle = self.root / 'build' / promotion.FILES[0]
        self.files = {promotion.FILES[0]: bundle.read_bytes(),
                      'SHA256SUMS': f'{promotion.sha(bundle.read_bytes())}  {bundle.name}\n'.encode(),
                      'verification.json': json.dumps({
                          'source_commit': self.commit, 'source_sha256': promotion.ci.source_id(self.root),
                          'zip_sha256': promotion.sha(bundle.read_bytes()),
                          'package_payload_sha256': promotion.ci.verify_bundle(bundle, self.root),
                          'release_approved': False}).encode()}
        self.api = FakeGitHub(self.commit, self.archive())
        self.output = Path(self.temporary.name) / 'approved'
        self.previous_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.previous_cwd)

    def git(self, *arguments):
        return subprocess.check_output(['git', '-C', str(self.root), *arguments], text=True,
                                       stderr=subprocess.DEVNULL).strip()

    def archive(self, files=None):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, content in (self.files if files is None else files).items():
                archive.writestr(name, content)
        return data.getvalue()

    def test_real_tag_source_and_zip_are_promoted_without_rebuild_and_retries_are_idempotent(self):
        self.api.annotated = True
        self.api.artifacts.append(dict(self.api.artifacts[0], id=22, expired=True))
        promotion.prepare(self.api, self.tag, self.output)
        self.assertEqual(self.git('worktree', 'list', '--porcelain').count('worktree '), 1)
        promotion.attach(self.api, self.tag, self.output, dry_run=True)
        self.assertFalse(any('data' in options for _, options in self.api.calls))
        promotion.attach(self.api, self.tag, self.output)
        writes = [(path, options) for path, options in self.api.calls if 'data' in options]
        self.assertEqual(len(writes), 3)
        self.assertEqual({item['name'] for item in self.api.release['assets']}, set(promotion.FILES))
        for _, options in writes:
            self.assertIn(options['data'], self.files.values())
        promotion.attach(self.api, self.tag, self.output)
        self.assertEqual(sum('data' in options for _, options in self.api.calls), 3)

    def test_wrong_failed_pending_or_foreign_builds_and_expired_artifacts_cannot_promote(self):
        mutations = [lambda a: a.runs[0].update(conclusion='failure'),
                     lambda a: a.runs[0].update(status='in_progress', conclusion=None),
                     lambda a: a.runs[0].update(event='pull_request'),
                     lambda a: a.runs[0].update(head_sha='f' * 40),
                     lambda a: a.runs[0]['head_repository'].update(full_name='foreign/repo'),
                     lambda a: a.runs.append(dict(a.runs[0], id=18, conclusion='failure')),
                     lambda a: a.artifacts[0].update(expired=True),
                     lambda a: a.artifacts[0].update(digest='sha256:' + 'f' * 64)]
        for change in mutations:
            api = FakeGitHub(self.commit, self.archive())
            change(api)
            with self.subTest(change=change), self.assertRaises(promotion.ReleaseError):
                promotion.prepare(api, self.tag, self.output)
            self.assertFalse(self.output.exists())
            self.assertFalse(any('data' in options for _, options in api.calls))

    def test_unreviewed_tags_and_mismatched_or_unexpected_artifact_contents_are_rejected(self):
        self.git('update-ref', 'refs/remotes/origin/main', self.commit)
        self.git('commit', '--allow-empty', '--quiet', '-m', 'Unmerged fixture')
        unmerged = self.git('rev-parse', 'HEAD')
        self.git('tag', 'v999.0.0')
        with self.assertRaises(subprocess.CalledProcessError):
            promotion.prepare(FakeGitHub(unmerged, self.archive()), 'v999.0.0', self.output)
        for index, files in enumerate((dict(self.files, **{'../private': b'bad'}),
                                        dict(self.files, SHA256SUMS=b'wrong checksum'))):
            output = self.output.with_name('invalid-' + str(index))
            with self.assertRaises(promotion.ReleaseError):
                promotion.prepare(FakeGitHub(self.commit, self.archive(files)), self.tag, output)
        bad = copy.deepcopy(self.files)
        metadata = json.loads(bad['verification.json'])
        metadata['source_sha256'] = 'f' * 64
        bad['verification.json'] = json.dumps(metadata).encode()
        with self.assertRaisesRegex(promotion.ReleaseError, 'tagged source'):
            promotion.prepare(FakeGitHub(self.commit, self.archive(bad)), self.tag,
                              self.output.with_name('wrong-source'))

    def test_existing_conflicts_moved_tags_immutable_releases_and_staging_changes_never_overwrite(self):
        promotion.prepare(self.api, self.tag, self.output)
        for mode in ('conflict', 'moved', 'immutable', 'staging'):
            api = FakeGitHub(self.commit, self.archive())
            if mode == 'conflict':
                api.release['assets'] = [{'name': 'verification.json', 'id': 45, 'state': 'uploaded',
                                          'size': len(self.files['verification.json']),
                                          'digest': 'sha256:' + 'f' * 64}]
            elif mode == 'moved':
                api.commit = 'f' * 40
            elif mode == 'immutable':
                api.release['immutable'] = True
            else:
                (self.output / 'verification.json').write_bytes(b'{}')
            with self.subTest(mode=mode), self.assertRaises((promotion.ReleaseError, KeyError)):
                promotion.attach(api, self.tag, self.output)
            self.assertFalse(any('data' in options for _, options in api.calls))

    def test_invalid_tag_inputs_and_cross_host_redirects_cannot_expose_credentials(self):
        for tag in ('main', 'v01.2.3', 'v1.2.3;echo bad', 'v1.2.3\n', '../v1.2.3'):
            with self.assertRaises(promotion.ReleaseError):
                promotion.version_tag(tag)
        request = Request('https://api.github.com/repos/fixture/radiolina/actions/artifacts/1/zip',
                          headers={'Authorization': 'Bearer private-fixture'})
        redirected = promotion.SafeRedirect().redirect_request(
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

        api = promotion.GitHub('fixture/radiolina', 'private-fixture')
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
        api.opener.response = b'x' * (promotion.LIMIT + 1)
        with self.assertRaisesRegex(promotion.ReleaseError, 'size limit'):
            api.request('actions/artifacts/23/zip', binary=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
