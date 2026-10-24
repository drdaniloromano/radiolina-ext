#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

# This script is exclusively for the disposable Fedora live guest.
if [[ $(id -un) != liveuser ]] || ! grep -qw rd.live.image /proc/cmdline; then
    echo 'Refusing to configure anything except the Fedora liveuser guest.' >&2
    exit 1
fi
gnome-shell --version | grep -Eq 'GNOME Shell 49\.'
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
payload=$(cd -- "$(dirname -- "$0")" && pwd)
uuid=radiolina@drdaniloromano.github.io
if ! rpm -q gjs gstreamer1-plugins-base gstreamer1-plugins-good libsoup3 >/dev/null; then
    sudo dnf -y --setopt=install_weak_deps=False install gjs gstreamer1-plugins-base gstreamer1-plugins-good libsoup3
fi
gnome-extensions install --force "$payload/$uuid.zip"
mkdir -p "$HOME/.config/gnome-radio"
if [[ ! -e "$HOME/.config/gnome-radio/stations.json" ]]; then
    umask 077
    cat > "$HOME/.config/gnome-radio/stations.json" <<'JSON'
{"version":1,"stations":[{"id":"nightride_test","name":"Nightride FM","url":"https://stream.nightride.fm/nightride.mp3"}],"selected":"nightride_test","notifications":false,"recent":[],"recentLimit":3,"fetchFavicons":false,"playButtonOnLeft":false,"groupWithAppIndicators":false}
JSON
fi
# Live media normally disables locking; restore normal installed-desktop behavior.
# This password exists only in this disposable guest, never on the host.
printf '%s\n' 'liveuser:246810' | sudo chpasswd
gsettings set org.gnome.desktop.lockdown disable-lock-screen false
gsettings set org.gnome.desktop.screensaver lock-enabled true
gsettings set org.gnome.shell welcome-dialog-last-shown-version '49.0'
touch "$HOME/.config/gnome-initial-setup-done"
echo RADIOLINA_GUEST_CONFIGURED
sudo systemd-run --quiet --unit=radiolina-start-desktop --on-active=3s /usr/bin/systemctl start gdm
