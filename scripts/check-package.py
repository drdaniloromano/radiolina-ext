#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Analyze the built ZIP in an offline container; never approve publication."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'localhost/radiolina-shexli:0.2.1'
LIMIT = 5 * 1024 * 1024


def review_report(data):
    """Shexli 0.2.1 exits zero even for findings: validate its actual report."""
    if not isinstance(data, dict) or data.get('spec_version') != '2026-04-02':
        raise ValueError('Unsupported or missing Shexli report schema')
    findings, summary, artifacts = data['findings'], data['summary'], data['artifacts']
    if (not isinstance(findings, list) or not isinstance(summary, dict) or
            not isinstance(artifacts, dict)):
        raise ValueError('Invalid Shexli findings')
    counts = Counter()
    for finding in findings:
        if (not isinstance(finding, dict) or finding.get('severity') not in
                ('error', 'warning', 'manual_review') or
                not isinstance(finding.get('rule_id'), str) or not finding['rule_id'] or
                not isinstance(finding.get('message'), str) or
                not isinstance(finding.get('evidence'), list)):
            raise ValueError('Invalid or unknown Shexli finding')
        counts[finding['severity']] += 1
    status = 'issues_found' if findings else 'clean'
    if (type(summary.get('finding_count')) is not int or
            summary['finding_count'] != len(findings) or summary.get('status') != status or
            summary.get('severity_counts') != dict(counts) or
            any(type(value) is not int for value in summary['severity_counts'].values()) or
            type(artifacts.get('js_file_count')) is not int or artifacts['js_file_count'] < 1 or
            type(artifacts.get('file_count')) is not int or
            artifacts['file_count'] < artifacts['js_file_count']):
        raise ValueError('Incomplete or inconsistent Shexli report')
    return {'status': status, 'errors': counts['error'], 'warnings': counts['warning'],
            'manual_review': counts['manual_review'],
            'review_required': bool(findings), 'release_approved': False,
            'analyzed_js_files': artifacts['js_file_count']}


def check_package(engine, bundle, output):
    if bundle.is_symlink() or not bundle.is_file() or bundle.stat().st_size > LIMIT:
        raise ValueError('Expected a regular installation ZIP of at most 5 MiB')
    output.mkdir(parents=True, exist_ok=True)
    previous = list(output.iterdir())
    if any(path.name not in ('report.json', 'summary.json', 'stderr.log') or
           path.is_symlink() or not path.is_file() for path in previous):
        raise ValueError('Report directory contains unrelated files; choose a dedicated directory')
    for path in previous:
        path.unlink()
    subprocess.run([engine, 'build', '-t', IMAGE, '-f', str(ROOT / 'Dockerfile.shexli'),
                    str(ROOT)], check=True, timeout=300)
    image_id = subprocess.check_output([engine, 'image', 'inspect', '--format', '{{.Id}}', IMAGE],
                                       text=True, timeout=30).strip()
    # Only a snapshot of the public package enters the container, never workspace/home.
    with tempfile.TemporaryDirectory(prefix='radiolina-package-check-') as directory:
        snapshot = Path(directory) / 'extension.zip'
        snapshot.write_bytes(bundle.read_bytes())
        snapshot.chmod(0o444)
        Path(directory).chmod(0o755)
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        name = 'radiolina-package-check-' + uuid.uuid4().hex[:12]
        try:
            result = subprocess.run([
                engine, 'run', '--rm', '--name', name, '--network=none', '--read-only',
                '--cap-drop=all', '--security-opt=no-new-privileges', '--security-opt=label=disable',
                '--memory=512m', '--cpus=1', '--pids-limit=64', '--ulimit=core=0:0',
                '--tmpfs=/tmp:rw,size=128m', '-v', f'{snapshot}:/input/extension.zip:ro',
                image_id, '/input/extension.zip', '--format=json'],
                capture_output=True, timeout=120)
        finally:
            subprocess.run([engine, 'rm', '--force', name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)
    if len(result.stdout) > LIMIT or len(result.stderr) > LIMIT:
        raise ValueError('Shexli output exceeds the report budget')
    (output / 'report.json').write_bytes(result.stdout)
    (output / 'stderr.log').write_bytes(result.stderr)
    if result.returncode:
        raise ValueError('Shexli did not complete; its exit code cannot pass this check')
    summary = review_report(json.loads(result.stdout))
    summary.update(zip_sha256=digest, analyzer='shexli==0.2.1', image_id=image_id,
                   requirements_sha256=hashlib.sha256(
                       (ROOT / 'scripts/shexli-requirements.txt').read_bytes()).hexdigest())
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    if hashlib.sha256(bundle.read_bytes()).hexdigest() != digest:
        raise ValueError('Installation ZIP changed during analysis')
    if summary['errors']:
        raise ValueError('Shexli errors block package upload; inspect the report')
    if summary['review_required']:
        print('Shexli findings require human review; this is not a clean analysis or publication approval.')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('podman', 'docker'), default='podman')
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/package-check')
    args = parser.parse_args()
    try:
        check_package(args.engine, args.zip.absolute(), args.output.resolve())
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f'Package analysis failed: {error}') from None


if __name__ == '__main__':
    main()
