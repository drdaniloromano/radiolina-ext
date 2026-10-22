#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Add numeric test identities inside an image; never import host account files."""
import argparse
from pathlib import Path


def ensure_account(root, uid, gid):
    updates = []
    for relative, number, index, entry in (
            ('etc/group', gid, 2, f'radiolina-test-{gid}:x:{gid}:\n'),
            ('etc/passwd', uid, 2,
             f'radiolina-test-{uid}:x:{uid}:{gid}:Container test account:/tmp/radiolina-home:/usr/sbin/nologin\n')):
        path = root / relative
        lines = path.read_text().splitlines()
        if any(len(fields := line.split(':')) > index and fields[index] == str(number)
               for line in lines):
            continue
        name = entry.split(':')[0]
        if any(line.split(':')[0] == name for line in lines):
            raise ValueError('Container test account name already belongs to another ID')
        updates.append((path, entry))
    for path, entry in updates:
        with path.open('a') as output:
            if path.stat().st_size and path.read_bytes()[-1:] != b'\n':
                output.write('\n')
            output.write(entry)


def numeric_id(value):
    if not value.isascii() or not value.isdecimal() or not 0 <= int(value) < 2 ** 32 - 1:
        raise argparse.ArgumentTypeError('expected a nonnegative Linux UID/GID')
    return int(value)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('uid', type=numeric_id)
    parser.add_argument('gid', type=numeric_id)
    parser.add_argument('--root', type=Path, default=Path('/'), help='image root (fixture root in tests)')
    args = parser.parse_args()
    ensure_account(args.root, args.uid, args.gid)
