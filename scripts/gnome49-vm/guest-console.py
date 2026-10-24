#!/usr/bin/env python3
"""Run a command solely in the private live guest over its serial console."""
# SPDX-License-Identifier: MIT
import argparse
from pathlib import Path
import re
import shlex
import socket
import sys
import time

SCRIPTS = Path(__file__).resolve().parent
VM = SCRIPTS.parents[1] / 'workspace' / 'gnome49-vm'
ANSI = re.compile(rb'\x1b\[[0-?]*[ -/]*[@-~]')
OSC = re.compile(rb'\x1b\].*?(?:\x07|\x1b\\)', re.S)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command')
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--logout', action='store_true')
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    output = bytearray()
    clean = b''
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        connection.connect(str(VM / 'console.sock'))
        connection.sendall(b'\n')
        while time.monotonic() < deadline:
            try:
                data = connection.recv(65536)
            except socket.timeout:
                continue
            if not data:
                raise RuntimeError('Guest console disconnected.')
            output.extend(data)
            clean = ANSI.sub(b'', OSC.sub(b'', output)).replace(b'\r', b'')
            last = clean.rstrip().split(b'\n')[-1]
            if last.endswith(b'login:'):
                connection.sendall(b'liveuser\n')
                output.clear()
            elif last.endswith(b'Password:'):
                connection.sendall(b'246810\n')
                output.clear()
            elif re.search(rb'\[liveuser@[^\n]+\][\$#]$', last):
                break
        else:
            raise RuntimeError('Guest login timeout: ' + clean[-1500:].decode(errors='replace'))
        output.clear()
        wrapped = ('stty -echo; bash -c ' + shlex.quote(args.command) +
                   '; radio_rc=$?; printf "\\nRADIOLINA_COMMAND_DONE=%s\\n" "$radio_rc"; stty echo\n')
        connection.sendall(wrapped.encode())
        while time.monotonic() < deadline:
            try:
                data = connection.recv(65536)
            except socket.timeout:
                continue
            if not data:
                raise RuntimeError('Guest console disconnected during command.')
            output.extend(data)
            clean = ANSI.sub(b'', OSC.sub(b'', output)).replace(b'\r', b'')
            match = re.search(rb'\nRADIOLINA_COMMAND_DONE=(\d+)\n', clean)
            if match:
                text = clean[:match.start()].decode(errors='replace')
                (VM / 'guest-console-last.txt').write_text(text)
                print(text)
                if args.logout:
                    connection.sendall(b'exit\n')
                return int(match[1])
        raise RuntimeError('Guest command timeout: ' + clean[-2000:].decode(errors='replace'))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
