#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Opt-in Fedora/RPM inventory and vendor advisory query; never installs packages."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RPM_FORMAT = '%{NAME}\t%{EPOCHNUM}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\t%{VENDOR}\n'
ROOT_PACKAGES = ['gjs', 'glib2', 'libsoup3', 'gstreamer1',
                 'gstreamer1-plugins-base', 'gstreamer1-plugins-good']


class CheckError(Exception):
    pass


def command(args, env):
    try:
        result = subprocess.run(args, env=env, text=True, capture_output=True,
                                stdin=subprocess.DEVNULL, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CheckError(f'{args[0]} unavailable or timed out: {type(error).__name__}') from error
    if result.returncode:
        # Reports are private; bounded native diagnostics aid repository failures.
        raise CheckError(f'{args[0]} exited {result.returncode}: {result.stderr[-2000:]}')
    return result.stdout


def json_array(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError) as error:
        raise CheckError('Invalid advisory/repository JSON output') from error
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise CheckError('Unsupported advisory/repository JSON schema')
    return value


def packages(text):
    rows = []
    for line in text.splitlines():
        fields = line.split('\t')
        if len(fields) != 6 or not re.fullmatch(r'[0-9]+', fields[1]):
            raise CheckError('Unsupported RPM inventory format')
        name, epoch, version, release, arch, vendor = fields
        if not all(fields):
            raise CheckError('Incomplete RPM package identity')
        rows.append(dict(name=name, epoch=int(epoch), version=version, release=release,
                         arch=arch, vendor=vendor,
                         nevra=f'{name}-{epoch}:{version}-{release}.{arch}'))
    if not rows:
        raise CheckError('Empty RPM inventory')
    return sorted(rows, key=lambda row: row['nevra'])


def advisories(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError) as error:
        raise CheckError('Invalid DNF5 advisory JSON') from error
    # Fedora 43 uses an advisory-ID keyed map ({} when empty); current upstream
    # documentation specifies an array. Validate both known representations.
    if value == {}:
        rows = []
    elif isinstance(value, list) and all(isinstance(row, dict) for row in value):
        rows = value
    elif isinstance(value, dict) and all(isinstance(row, dict) and row.get('Name') == key
                                        for key, row in value.items()):
        rows = list(value.values())
    else:
        raise CheckError('Unsupported DNF5 advisory detail schema')
    for row in rows:
        if (not isinstance(row.get('Name'), str) or not row['Name'] or
                row.get('Type') != 'security' or
                not isinstance(row.get('collections'), dict) or
                not isinstance(row['collections'].get('packages'), list) or
                not row['collections']['packages'] or
                not all(isinstance(p, str) for p in row['collections']['packages'])):
            raise CheckError('Unsupported DNF5 advisory detail schema')
    return rows


def source_digest():
    digest = hashlib.sha256()
    for directory in ('src', 'extension'):
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file():
                digest.update(str(path.relative_to(ROOT)).encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def os_release():
    release = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep:
            release[key] = value.strip('"')
    return release


def check(report, directory, env):
    release = os_release()
    report['environment'].update(distribution=release.get('ID'), release=release.get('VERSION_ID'),
                                 architecture=platform.machine(), support_end=release.get('SUPPORT_END'))
    if release.get('ID') != 'fedora':
        raise CheckError('Only the Fedora/RPM/DNF5 backend is implemented; this environment is unchecked')
    if release.get('SUPPORT_END') and date.fromisoformat(release['SUPPORT_END']) < date.today():
        report['coverage']['issues'].append('Distribution is past its advertised support end')
    if not release.get('SUPPORT_END'):
        report['coverage']['issues'].append('Distribution support end is not available; confirm support status manually')
    for tool in ('rpm', 'dnf5', 'gjs'):
        if not shutil.which(tool):
            raise CheckError(f'Required existing tool unavailable: {tool}')
    dnf = ['dnf5', '--no-plugins', '--assumeno', '--setopt=assumeyes=False',
           f'--setopt=cachedir={directory}/cache',
           f'--setopt=system_cachedir={directory}/cache', f'--setopt=persistdir={directory}/state',
           f'--setopt=logdir={directory}/log', '--setopt=*.skip_if_unavailable=False',
           '--setopt=optional_metadata_types=updateinfo']
    report['tooling']['dnf5'] = command(dnf + ['--version'], env).splitlines()[0]
    raw = command(['gjs', '-m', str(ROOT / 'scripts/security-inventory.js'),
                   str(ROOT / 'src/service/decoder.js')], env)
    try:
        elements = json.loads(raw)['elements']
        if not elements or not all(isinstance(e, dict) and isinstance(e.get('name'), str) and
                                   e['name'] and 'file' in e and
                                   (e.get('file') is None or isinstance(e['file'], str)) for e in elements):
            raise ValueError('missing factories')
    except (KeyError, ValueError, TypeError) as error:
        raise CheckError('Incomplete installed factory inventory') from error
    report['elements'] = elements
    names = set(ROOT_PACKAGES)
    if report['environment']['kind'] == 'desktop':
        names.add('gnome-shell')
    for file in sorted({e['file'] for e in elements if e['file']}):
        try:
            names.update(command(['rpm', '-qf', '--qf', '%{NAME}\n', file], env).splitlines())
        except CheckError:
            report['coverage']['issues'].append(f'Factory library is not owned by an installed RPM: {file}')
    report['root_packages'] = sorted(names)
    report['packages'] = packages(command(['rpm', '-q', '--qf', RPM_FORMAT, *sorted(names)], env))
    closure = command(dnf + ['--disable-repo=*', 'repoquery', '--installed',
                      '--providers-of=requires', '--recursive', '--queryformat=%{name}\n', *sorted(names)], env)
    names.update(closure.splitlines())
    report['packages'] = packages(command(['rpm', '-q', '--qf', RPM_FORMAT, *sorted(names)], env))
    foreign = sorted({p['vendor'] for p in report['packages'] if p['vendor'] != 'Fedora Project'})
    if foreign:
        report['coverage']['issues'].append('Non-Fedora package vendors require separate advisory coverage: ' + ', '.join(foreign))
    report['inventory_sha256'] = hashlib.sha256(json.dumps(report['packages'], sort_keys=True).encode()).hexdigest()
    repositories = json_array(command(dnf + ['repo', 'list', '--enabled', '--json'], env))
    if not repositories or any(not isinstance(r.get('id'), str) or r.get('is_enabled') is not True for r in repositories):
        raise CheckError('No usable enabled repository inventory')
    if not any(row['id'] == 'updates' for row in repositories):
        report['coverage']['issues'].append('Fedora updates repository is not enabled')
    supported = {'fedora', 'updates', 'fedora-cisco-openh264'}
    excluded = sorted(row['id'] for row in repositories if row['id'] not in supported)
    report['coverage']['unqueried_repository_ids'] = excluded
    if excluded:
        report['coverage']['issues'].append('Enabled repositories outside the Fedora backend need review: ' + ', '.join(excluded))
    successful = []
    for repository in repositories:
        repo = repository['id']
        if repo not in supported:
            continue
        try:
            rows = json_array(command(dnf + [f'--repo={repo}', '--refresh', 'repo', 'info', '--json'], env))
            if len(rows) != 1 or rows[0].get('id') != repo:
                raise CheckError('Repository identity changed')
            # Retain IDs/timestamps, not configured URLs which may contain credentials.
            report['repositories'].append({key: rows[0].get(key) for key in
                ('id', 'timestamp', 'revision', 'max_timestamp', 'repo_gpgcheck', 'pkg_gpgcheck')})
            successful.append(repo)
        except CheckError as error:
            report['coverage']['issues'].append(f'Repository {repo} refresh failed: {error}')
    if not successful:
        raise CheckError('No supported vendor repository could be refreshed')
    selected = ['--repo=' + ','.join(successful)]
    spec = '--contains-pkgs=' + ','.join(sorted(names))
    report['vendor_results']['available'] = advisories(command(dnf + selected + ['advisory', 'info', '--available',
                                                       '--security', spec, '--json'], env))
    report['vendor_results']['installed'] = advisories(command(dnf + selected + ['advisory', 'info', '--installed',
                                                       '--security', spec, '--json'], env))
    metadata = []
    for path in sorted(Path(directory, 'cache').rglob('repomd.xml')):
        try:
            tree = ET.parse(path).getroot()
            entries = [node for node in tree if node.tag.rsplit('}', 1)[-1] == 'data']
            types = [node.get('type') for node in entries]
        except (OSError, ET.ParseError) as error:
            raise CheckError('Invalid cached repository metadata') from error
        metadata.append({'cache_repository': path.parent.parent.name,
                         'metadata_types': types,
                         'cached_updateinfo_files': [p.name for p in path.parent.rglob('*updateinfo*')
                                                     if p.is_file() and p.stat().st_size > 0],
                         'repomd_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    report['metadata'] = metadata
    if not metadata or not any('updateinfo' in item['metadata_types'] for item in metadata):
        raise CheckError('No vendor updateinfo metadata observed; empty advisory results cannot establish coverage')
    if not any(item['cached_updateinfo_files'] for item in metadata):
        raise CheckError('Vendor updateinfo was advertised but no downloaded advisory data was observed')
    report['coverage']['vendor_query_completed_at'] = datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=('desktop', 'container'), default='desktop')
    parser.add_argument('--image-id', default=None)
    parser.add_argument('--output', type=Path, help='Private JSON report; defaults to stdout')
    args = parser.parse_args()
    report = {'schema_version': 1, 'timestamp': datetime.now(timezone.utc).isoformat(),
              'source_sha256': source_digest(), 'environment': {'kind': args.environment, 'image_id': args.image_id},
              'tooling': {'checker_sha256': hashlib.sha256(Path(__file__).read_bytes() +
                          (ROOT / 'scripts/security-inventory.js').read_bytes()).hexdigest()},
              'elements': [], 'root_packages': [], 'packages': [],
              'repositories': [], 'metadata': [], 'vendor_results': {'available': [], 'installed': []},
              'coverage': {'issues': [], 'vendor_query_completed_at': None},
              'manual_review': {'status': 'required', 'tasks': [
                  'Read upstream security notices; map relevant issues to installed package builds and actual code paths',
                  'Verify distribution backports and affected/fixed versions; record justified not-applicable decisions',
                  'Review repositories without updateinfo and native/dynamically selected libraries outside the inventory',
                  'Confirm report freshness and environment/source/package fingerprints before release'],
                  'sources': ['https://gstreamer.freedesktop.org/security/',
                              'https://gitlab.gnome.org/GNOME/glib/-/releases',
                              'https://gitlab.gnome.org/GNOME/libsoup/-/releases',
                              'https://gitlab.gnome.org/GNOME/gjs/-/releases']},
              'limits': ['No automatic upstream CVE applicability assessment or proof of vulnerability freedom',
                         'Package closure is conservative; a package advisory is not proof of exploitability',
                         'Container results do not cover the installed desktop; no runtime sandbox is added',
                         'No package installation/update or applet background monitoring is performed']}
    with tempfile.TemporaryDirectory(prefix='radiolina-security-') as directory:
        env = dict(os.environ, LC_ALL='C.UTF-8', GIO_USE_VFS='local',
                   XDG_CACHE_HOME=directory + '/user-cache', XDG_STATE_HOME=directory + '/user-state',
                   GST_REGISTRY=directory + '/gst-registry.bin')
        try:
            check(report, directory, env)
        except (CheckError, OSError, ValueError) as error:
            report['coverage']['issues'].append(str(error))
    if report['coverage']['issues']:
        report['status'], code = 'incomplete', 2
    elif report['vendor_results']['available']:
        report['status'], code = 'vendor-advisories-found', 1
    else:
        report['status'], code = 'no-outstanding-vendor-advisories', 0
    report['exit_code'] = code
    report['release_approved'] = False
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent, delete=False) as output:
            output.write(text)
            temporary = Path(output.name)
        temporary.replace(args.output)
        count = len(report['vendor_results']['available']) if report['coverage']['vendor_query_completed_at'] else 'unknown'
        print(f'{report["status"]}; {len(report["packages"])} packages; '
              f'{count} available security advisories; '
              f'manual review required. Report: {args.output}', file=sys.stderr)
    else:
        print(text, end='')
    return code


if __name__ == '__main__':
    sys.exit(main())
