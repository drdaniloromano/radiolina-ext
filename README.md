# radiolina

Lightweight internet radio for **GNOME Shell**, controlled entirely from the top bar.
A compact native popup keeps playback and saved stations close at hand.

**Release status:** **0.4.0**, finalized locally; public distribution is pending.
Supports **GNOME Shell 49 and 50**.
See the [changelog](CHANGELOG.md) for completed changes.
Publication awaits a [patched runtime baseline and remaining verification](docs/SECURITY.md#release-priorities).

## Features

- Play/pause from the indicator, station/track information, or media keys.
- Saved stations from direct HTTP(S) streams, M3U, and XSPF playlists.
- Bounded URL, redirect, and audio-format validation before decoding.
- Inline station editing, local filtering, and configurable Recent entries.
- Stream-provided artist/title metadata and GNOME's native media card, without
  song-change notification banners.
- Native light/dark styling, static playback-state icons, and optional Stop.
- Separate playback service; Stop releases it and Quit removes the indicator.

## Requirements

- **Desktop runtime:** GNOME Shell 49 or 50, GJS/GI with GLib/Gio/GLibUnix, libsoup 3,
  GStreamer with base/good plugins and the decoders your streams need, and desktop audio.
- **Container packaging:** Make and a local Podman or Docker installation.

The ZIP contains extension code, not runtime libraries. Installing a package built
in a container still requires those libraries on the desktop host. See the
[dependency and codec details](docs/DEVELOPMENT.md#dependencies-and-codecs).

## Installation

From a checkout, build the development package and install it:

```sh
make container-build
make container-package
gnome-extensions install --force build/radiolina@drdaniloromano.github.io.zip
```

Podman is the default. For Docker, add `CONTAINER_ENGINE=docker` to both Make
commands. See [contained development](docs/DEVELOPMENT.md#contained-builds-and-configuration).

For a first installation, log out and back in, then enable it:

```sh
gnome-extensions enable radiolina@drdaniloromano.github.io
```

See the [user guide](docs/USER_GUIDE.md#same-session-installation-and-updates)
for installation without logging out, updates, and migration from the development ID.

## Basic usage

1. Click the radio icon, then **+** to save a station name and stream/playlist URL.
2. Click Play or the station/track area to toggle playback. Media keys work while
   the playback service is running.
3. Expand **Stations** to browse; type or press **Ctrl+F** to filter saved stations.
   Hover or focus a row for Play, Edit, and Remove.
4. Open Settings to change the Recent count or show Stop.

Pause retains the playback pipeline. Optional **Stop** exits the service while
leaving the indicator available; **Quit** disables the extension. Screen lock
stops playback; unlocking restores an idle indicator until you press Play.

## Help and contributions

- [User guide and troubleshooting](docs/USER_GUIDE.md)
- [Architecture, development, and build configuration](docs/DEVELOPMENT.md)
- [Testing and manual acceptance](docs/TESTING.md)
- [Dependency security checks and release review](docs/SECURITY.md)
- [Contributor guidelines](AGENTS.md)
- [Report a problem or suggest a change](https://github.com/drdaniloromano/radiolina-ext/issues)

Maintained by [Danilo Romano](https://github.com/drdaniloromano).
Use the [bug-report form](.github/ISSUE_TEMPLATE/bug_report.yml) for versions,
reproduction steps, and expected/actual behavior. Screenshots and logs are optional;
remove private stream URLs, credentials, and tokens before posting.
The source repository is [radiolina-ext](https://github.com/drdaniloromano/radiolina-ext).

## License

Original code, bundled icons, documentation, and tooling use the [MIT License](LICENSE).
See the [provenance review](docs/PROVENANCE.md) for attribution findings and limits.
This independent project is not endorsed by the GNOME Foundation.
