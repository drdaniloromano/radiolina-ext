#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Promote an existing verified main artifact; never build, tag or publish a release."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

import ci

UUID = 'radiolina@drdaniloromano.github.io'
FILES = (f'{UUID}.zip', 'SHA256SUMS', 'verification.json')
LIMIT = 5 * 1024 * 1024


class ReleaseError(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def version_tag(value):
    if not re.fullmatch(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value) or len(value) > 64:
        raise ReleaseError('Use a version tag such as v0.5.0')
    return value


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        redirected = super().redirect_request(request, fp, code, message, headers, newurl)
        if redirected and urlsplit(request.full_url).hostname != urlsplit(newurl).hostname:
            redirected.remove_header('Authorization')
        return redirected


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not token:
            raise ReleaseError('GitHub repository and workflow token are required')
        self.repository, self.token = repository, token
        self.opener = build_opener(SafeRedirect())

    def request(self, path, *, data=None, binary=False, upload=False):
        host = 'uploads.github.com' if upload else 'api.github.com'
        headers = {'Authorization': 'Bearer ' + self.token, 'User-Agent': 'radiolina-release',
                   'Accept': ('application/octet-stream' if path.startswith('releases/assets/') and binary
                              else 'application/vnd.github+json'),
                   'X-GitHub-Api-Version': '2026-03-10'}
        if data is not None:
            headers['Content-Type'] = 'application/octet-stream'
        request = Request(f'https://{host}/repos/{self.repository}/{path}', data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                result = response.read(LIMIT + 1)
        except HTTPError as error:
            raise ReleaseError(f'GitHub request failed (HTTP {error.code})') from None
        if len(result) > LIMIT:
            raise ReleaseError('GitHub response exceeds the size limit')
        return result if binary else json.loads(result)


def git(*arguments):
    return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', *arguments],
                                   text=True, stderr=subprocess.DEVNULL).strip()


def tagged_commit(tag):
    commit = git('rev-parse', '--verify', f'refs/tags/{version_tag(tag)}^{{commit}}')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ReleaseError('Unexpected tag commit identity')
    subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'origin/main'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return commit


def remote_commit(api, tag):
    obj = api.request('git/ref/tags/' + version_tag(tag))['object']
    for _ in range(8):
        if obj['type'] == 'commit':
            return obj['sha']
        if obj['type'] != 'tag' or not re.fullmatch(r'[0-9a-f]{40}', obj['sha']):
            break
        obj = api.request('git/tags/' + obj['sha'])['object']
    raise ReleaseError('Unsupported tag object chain')


def select_artifact(api, commit):
    query = urlencode({'branch': 'main', 'event': 'push', 'head_sha': commit, 'per_page': 100})
    runs = api.request('actions/workflows/ci.yml/runs?' + query)['workflow_runs']
    runs = [run for run in runs if run['head_sha'] == commit and run['event'] == 'push'
            and run['head_branch'] == 'main' and run['head_repository']['full_name'] == api.repository]
    if not runs:
        raise ReleaseError('No main push build exists for this tag; run its CI first')
    run = max(runs, key=lambda item: item['id'])
    if run['status'] != 'completed' or run['conclusion'] != 'success':
        raise ReleaseError('The latest main build for this commit must complete successfully')
    artifacts = api.request(f'actions/runs/{run["id"]}/artifacts?per_page=100')['artifacts']
    matches = [item for item in artifacts if item['name'] == 'radiolina-install-' + commit
               and not item['expired']]
    if len(matches) != 1:
        raise ReleaseError('The exact installation artifact is missing or expired; rerun its main CI')
    artifact = matches[0]
    if artifact['size_in_bytes'] > LIMIT:
        raise ReleaseError('Installation artifact exceeds the size limit')
    data = api.request(f'actions/artifacts/{artifact["id"]}/zip', binary=True)
    if artifact.get('digest') != 'sha256:' + sha(data):
        raise ReleaseError('Downloaded artifact differs from its GitHub digest')
    return data, run['id']


def unpack(data, output):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if (len(archive.namelist()) != len(FILES) or set(archive.namelist()) != set(FILES)
                or sum(item.file_size for item in archive.infolist()) > LIMIT):
            raise ReleaseError('Installation artifact contains unexpected files or exceeds its budget')
        for item in archive.infolist():
            if ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise ReleaseError('Artifact symlinks are not allowed')
            (output / item.filename).write_bytes(archive.read(item))


def verify_files(directory, tag, commit):
    if {p.name for p in directory.iterdir()} - set(FILES) - {'release-plan.json'}:
        raise ReleaseError('Unexpected files in release staging')
    data = {}
    for name in FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > LIMIT:
            raise ReleaseError('Missing or oversized release file')
        data[name] = path.read_bytes()
    metadata = json.loads(data['verification.json'])
    if metadata['source_commit'] != commit or metadata['zip_sha256'] != sha(data[FILES[0]]):
        raise ReleaseError('Release manifest does not match the tagged commit and ZIP')
    if data['SHA256SUMS'] != f'{sha(data[FILES[0]])}  {FILES[0]}\n'.encode():
        raise ReleaseError('Installer checksum file does not match')
    with zipfile.ZipFile(io.BytesIO(data[FILES[0]])) as archive:
        if sum(item.file_size for item in archive.infolist()) > 20 * 1024 * 1024:
            raise ReleaseError('Unpacked installation exceeds its budget')
        package = json.loads(archive.read('metadata.json'))
        if package['uuid'] != UUID or package['version-name'] != version_tag(tag)[1:]:
            raise ReleaseError('Version tag does not match installation metadata')
    return data, metadata


def prepare(api, tag, output):
    commit = tagged_commit(tag)
    if remote_commit(api, tag) != commit:
        raise ReleaseError('Remote tag differs from the verified checkout')
    data, run_id = select_artifact(api, commit)
    output.mkdir(parents=True, exist_ok=False)
    unpack(data, output)
    files, metadata = verify_files(output, tag, commit)
    with tempfile.TemporaryDirectory(prefix='radiolina-release-source-') as directory:
        source = Path(directory) / 'source'
        git('worktree', 'add', '--quiet', '--detach', str(source), commit)
        try:
            if (ci.source_id(source) != metadata['source_sha256'] or
                    ci.verify_bundle(output / FILES[0], source) != metadata['package_payload_sha256']):
                raise ReleaseError('Build artifact does not match the complete tagged source')
        finally:
            git('worktree', 'remove', '--force', str(source))
    plan = {'tag': tag, 'commit': commit, 'repository': api.repository, 'ci_run_id': run_id,
            'assets': {name: sha(value) for name, value in files.items()}}
    (output / 'release-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(f'Verified {tag} from successful main build {run_id}')


def attach(api, tag, directory, *, dry_run=False):
    plan_file = directory / 'release-plan.json'
    if plan_file.is_symlink() or not plan_file.is_file() or plan_file.stat().st_size > 65536:
        raise ReleaseError('Missing or oversized release plan')
    plan = json.loads(plan_file.read_text())
    if plan['tag'] != version_tag(tag) or plan['repository'] != api.repository:
        raise ReleaseError('Staged files belong to another release or repository')
    files, _ = verify_files(directory, tag, plan['commit'])
    if plan['assets'] != {name: sha(value) for name, value in files.items()}:
        raise ReleaseError('Staged release assets changed after verification')
    if remote_commit(api, tag) != plan['commit']:
        raise ReleaseError('Tag moved after artifact verification')
    release = api.request('releases/tags/' + version_tag(tag))
    pending = []
    for name, data in files.items():
        matches = [item for item in release['assets'] if item['name'] == name]
        if len(matches) > 1:
            raise ReleaseError('Duplicate release asset names need manual repair')
        if not matches:
            pending.append((name, data))
            continue
        asset = matches[0]
        if asset['state'] != 'uploaded' or asset['size'] != len(data):
            raise ReleaseError('An existing asset differs or is incomplete; no files were overwritten')
        digest = asset.get('digest')
        if not digest:
            digest = 'sha256:' + sha(api.request(f'releases/assets/{asset["id"]}', binary=True))
        if digest != 'sha256:' + sha(data):
            raise ReleaseError('An existing asset differs; no files were overwritten')
    if pending and release.get('immutable'):
        raise ReleaseError('This published release is immutable and cannot accept new assets')
    if dry_run:
        print(f'{tag}: {len(pending)} files would be attached; no release changes made')
        return
    for name, data in pending:
        asset = api.request(f'releases/{release["id"]}/assets?name=' + quote(name), data=data, upload=True)
        if (asset['name'] != name or asset['state'] != 'uploaded' or asset['size'] != len(data)
                or asset.get('digest') != 'sha256:' + sha(data)):
            raise ReleaseError('GitHub did not confirm the uploaded asset checksum')
        print('Attached ' + name)
    print(f'{tag}: verified assets present; release notes and publication state unchanged')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'attach'))
    parser.add_argument('--tag', required=True, type=version_tag)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--dry-run', action='store_true', help='validate attachment without writing to GitHub')
    args = parser.parse_args()
    if args.dry_run and args.action != 'attach':
        parser.error('--dry-run applies only to attach')
    api = GitHub(os.environ.get('GITHUB_REPOSITORY', ''), os.environ.get('GH_TOKEN', ''))
    try:
        if args.action == 'prepare':
            prepare(api, args.tag, args.directory)
        else:
            attach(api, args.tag, args.directory, dry_run=args.dry_run)
    except ReleaseError as error:
        raise SystemExit(str(error)) from None
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, subprocess.CalledProcessError):
        # No remote bodies, input URLs, signed download URLs or credentials in logs.
        raise SystemExit('Release attachment failed. Check tag/version, successful main CI, artifact expiry, '
                         'release mutability and existing asset checksums; no assets are overwritten.') from None


if __name__ == '__main__':
    main()
