#!/usr/bin/env python3
"""Machine-local disposable GNOME 49 live VM. No installed guest system disk."""
# SPDX-License-Identifier: MIT
import argparse
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import time

SCRIPTS = Path(__file__).resolve().parent
VM = SCRIPTS.parents[1] / 'workspace' / 'gnome49-vm'
ISO = VM / 'Fedora-Workstation-Live-43-1.6.x86_64.iso'
NAME = 'radiolina-gnome49-test'


def qmp(command, **arguments):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(15)
        connection.connect(str(VM / 'qmp.sock'))
        stream = connection.makefile('rwb', buffering=0)
        json.loads(stream.readline())
        for message in ({'execute': 'qmp_capabilities'},
                        {'execute': command, 'arguments': arguments}):
            stream.write(json.dumps(message).encode() + b'\n')
            while True:
                line = stream.readline()
                if not line:
                    return None
                response = json.loads(line)
                if 'error' in response:
                    raise RuntimeError(response['error'])
                if 'return' in response:
                    result = response['return']
                    break
        return result


def running():
    try:
        pid = int((VM / 'qemu.pid').read_text())
        arguments = Path(f'/proc/{pid}/cmdline').read_bytes()
        return pid if NAME.encode() in arguments and str(VM / 'qmp.sock').encode() in arguments else None
    except (OSError, ValueError):
        return None


def start():
    if running():
        print('The VM is already running.')
        return
    if not VM.is_dir():
        raise RuntimeError('Prepare media with scripts/gnome49-vm/rebuild.py first.')
    payload_iso = VM / 'payload.iso'
    payload_sources = list((VM / 'payload').iterdir())
    expected = {'prepare-guest.sh', 'radiolina@drdaniloromano.github.io.zip'}
    if ({path.name for path in payload_sources} != expected or
            any(path.is_symlink() or not path.is_file() for path in payload_sources)):
        raise RuntimeError('Unexpected payload files; rebuild the allowlisted guest payload.')
    if not payload_iso.exists() or any(path.stat().st_mtime_ns > payload_iso.stat().st_mtime_ns
                                       for path in payload_sources):
        subprocess.run(['xorriso', '-as', 'mkisofs', '-quiet', '-V', 'RADIOLINA_TEST',
                        '-o', str(payload_iso), str(VM / 'payload')], check=True)
    for name in ('qmp.sock', 'spice.sock', 'console.sock', 'qemu.pid', 'configured.pid', 'ready.pid'):
        (VM / name).unlink(missing_ok=True)
    for path in (ISO, VM / 'payload.iso', VM / 'boot/vmlinuz', VM / 'boot/initrd.img'):
        if not path.is_file():
            raise RuntimeError(f'Missing prepared VM asset: {path}')
    if not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('KVM is required; CPU-heavy software emulation is intentionally disabled.')
    rendernode = '/dev/dri/renderD128'
    command = ['qemu-system-x86_64', '-name', NAME, '-machine', 'q35,accel=kvm',
        '-cpu', 'host', '-smp', '2', '-m', '2048', '-nodefaults',
        '-device', 'virtio-vga-gl,xres=1280,yres=720,max_outputs=1',
        '-display', 'none',
        '-spice', f'unix=on,addr={VM}/spice.sock,disable-ticketing=on,gl=on,rendernode={rendernode},disable-copy-paste=on,disable-agent-file-xfer=on',
        '-audiodev', 'spice,id=audio0', '-device', 'ich9-intel-hda',
        '-device', 'hda-output,audiodev=audio0',
        '-device', 'virtio-balloon-pci,free-page-reporting=on,deflate-on-oom=on',
        '-device', 'virtio-scsi-pci,id=scsi',
        '-drive', f'file={ISO},if=none,id=live,media=cdrom,format=raw,readonly=on',
        '-device', 'scsi-cd,drive=live',
        '-drive', f'file={VM}/payload.iso,if=none,id=payload,media=cdrom,format=raw,readonly=on',
        '-device', 'scsi-cd,drive=payload',
        '-netdev', 'user,id=net0', '-device', 'virtio-net-pci,netdev=net0',
        '-device', 'qemu-xhci,id=usb', '-device', 'usb-tablet',
        '-kernel', str(VM / 'boot/vmlinuz'), '-initrd', str(VM / 'boot/initrd.img'),
        '-append', 'root=live:CDLABEL=Fedora-WS-Live-43 rd.live.image quiet rhgb console=tty0 console=ttyS0,115200n8 systemd.unit=multi-user.target',
        '-chardev', f'socket,id=serial0,path={VM}/console.sock,server=on,wait=off,logfile={VM}/serial.log',
        '-serial', 'chardev:serial0', '-monitor', 'none',
        '-qmp', f'unix:{VM}/qmp.sock,server=on,wait=off',
        '-pidfile', str(VM / 'qemu.pid'), '-daemonize']
    (VM / 'qemu-command.json').write_text(json.dumps(command, indent=2) + '\n')
    environment = dict(os.environ, XDG_CACHE_HOME=str(VM / 'cache'))
    subprocess.run(command, check=True, env=environment)
    print('Started: 2 vCPUs, 2 GiB RAM, KVM + GPU rendering, no installed system disk.')


def view():
    if not running():
        raise RuntimeError('Start the VM first.')
    pidfile = VM / 'viewer.pid'
    try:
        pid = int(pidfile.read_text())
        if str(VM / 'spice.sock').encode() in Path(f'/proc/{pid}/cmdline').read_bytes():
            return
    except (OSError, ValueError):
        pass
    with (VM / 'viewer.log').open('a') as output:
        process = subprocess.Popen(['remote-viewer', f'spice+unix://{VM}/spice.sock'],
                                   stdout=output, stderr=output, start_new_session=True)
    pidfile.write_text(str(process.pid) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'ready', 'stop', 'status', 'view', 'wake'])
    parser.add_argument('--view', action='store_true')
    args = parser.parse_args()
    if args.action == 'start':
        start()
    elif args.action == 'ready':
        start()
        if args.view:
            view()
        try:
            configured = (VM / 'ready.pid').read_text().strip() == str(running())
        except OSError:
            configured = False
        if not configured:
            print('Preparing the ephemeral guest; wait for the desktop readiness check.', flush=True)
            command = ('sudo mkdir -p /mnt/radiolina-test; '
                       'mountpoint -q /mnt/radiolina-test || sudo mount -o ro '
                       '/dev/disk/by-label/RADIOLINA_TEST /mnt/radiolina-test; '
                       'bash /mnt/radiolina-test/prepare-guest.sh')
            if not (VM / 'configured.pid').exists() or (VM / 'configured.pid').read_text().strip() != str(running()):
                subprocess.run([sys.executable, str(SCRIPTS / 'guest-console.py'), command,
                                '--timeout', '240', '--logout'], check=True)
                (VM / 'configured.pid').write_text(str(running()) + '\n')
                time.sleep(60)
            check = ('set -e; export XDG_RUNTIME_DIR=/run/user/1000 '
                     'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus; '
                     'gnome-extensions enable radiolina@drdaniloromano.github.io; '
                     'for attempt in $(seq 1 65); do '
                     'gdbus call --session --timeout 5 --dest org.mpris.MediaPlayer2.GnomeRadio '
                     '--object-path /org/gnome/Radio --method org.freedesktop.DBus.Properties.Get '
                     'org.gnome.Radio1 State >/dev/null 2>&1 && break; sleep 2; done; '
                     'info=$(gnome-extensions info radiolina@drdaniloromano.github.io); '
                     'printf "%s\\n" "$info"; printf "%s" "$info" | grep -q "State: ACTIVE"; '
                     'gdbus call --session --timeout 5 --dest org.mpris.MediaPlayer2.GnomeRadio '
                     '--object-path /org/gnome/Radio --method org.freedesktop.DBus.Properties.Get '
                     'org.gnome.Radio1 State')
            subprocess.run([sys.executable, str(SCRIPTS / 'guest-console.py'), check,
                            '--timeout', '300'], check=True)
            (VM / 'ready.pid').write_text(str(running()) + '\n')
        print('GNOME 49 and radiolina are ready. Guest password: 246810')
    elif args.action == 'view':
        view()
    elif args.action == 'wake':
        if not running():
            raise RuntimeError('The VM is stopped; use ready to start it.')
        if qmp('query-status')['status'] != 'suspended':
            raise RuntimeError('QEMU does not report a suspended guest; wake request not sent.')
        qmp('system_wakeup')
        print('Wake requested for the disposable guest.')
    elif args.action == 'stop':
        if running():
            qmp('quit')
            for _ in range(50):
                if not running():
                    break
                time.sleep(0.1)
        if running():
            raise RuntimeError('VM has not stopped; inspect its owned QEMU process.')
        try:
            viewer = int((VM / 'viewer.pid').read_text())
            if str(VM / 'spice.sock').encode() in Path(f'/proc/{viewer}/cmdline').read_bytes():
                os.kill(viewer, signal.SIGTERM)
        except (OSError, ValueError):
            pass
        print('VM stopped. Live guest changes are discarded; CPU/RAM released.')
    else:
        pid = running()
        print(json.dumps({'pid': pid, 'qemu': qmp('query-status') if pid else 'stopped'}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
