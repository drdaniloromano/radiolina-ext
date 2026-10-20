# Development

See [contributor guidelines](../AGENTS.md) and [verification commands](TESTING.md).

## Architecture and ownership

```mermaid
flowchart TB
    subgraph shell["GNOME Shell process"]
        ui["Indicator and popup"]
    end
    subgraph backend["Separate GJS playback process"]
        service["Station state, D-Bus API and MPRIS"]
        player["GStreamer playback"]
        store["Validated station storage"]
        service --> player
        service --> store
    end
    ui -->|D-Bus commands| service
    service -->|D-Bus state updates| ui
    media["Media keys and native media card"] <-->|MPRIS| service
    stream["Radio stream"] -->|Audio and track metadata| player
    store --> config["stations.json"]
```

The Shell UI owns widgets, focus, local filtering, and a cached state snapshot.
The separate GJS/GStreamer service owns playback, validation, persistence, source
loading, and metadata. State changes arrive through D-Bus signals rather than
polling. Core logic contains no Shell widgets; no other desktop adapter is shipped.
There is no web runtime, runtime Python/npm dependency, station-directory API,
recording, account system, or podcast subsystem.

| Location | Responsibility |
| --- | --- |
| [extension/](../extension/) | Native popup/indicator, symbolic SVGs, layout CSS, desktop adapter. |
| [src/core/](../src/core/) | URL/config validation, bounded playlist/image parsing, metadata sanitization and deduplication. |
| [src/service/](../src/service/) | GStreamer, async playlists/favicons, atomic storage, D-Bus/MPRIS, process-local resource policy. |
| [radio.xml](../src/service/radio.xml) | App command/state contract; `State` is JSON in a D-Bus string property. |
| [tests/unit/](../tests/unit/) | Critical validation, metadata, parsing, and storage cases. |
| [tests/e2e/](../tests/e2e/) | Production service and actual Shell workflows using local fixtures. |
| [scripts/](../scripts/), [Makefile](../Makefile), [Containerfile](../Containerfile) | Contained builds, tests, packaging, and live-development helpers. |

### Lifecycle and cancellation

`enable()` loads owned styles, creates the indicator, and starts the service.
`disable()` destroys UI/subscriptions, unloads its stylesheet, and requests service
shutdown without blocking Shell. Service teardown handles SIGTERM/SIGINT and loss
of its owning Shell D-Bus connection. Infobox Stop exits the backend; subsequent
Play or station/settings operations start it on demand. An unexpected service
exit preserves the indicator for explicit retry, with stale metadata cleared.
Screen lock follows GNOME's default `user` session mode: stop on lock, idle on unlock.

UI call generations/cancellables prevent stale replies from updating removed UI
or undoing a newer Stop. Service load generations/cancellables prevent a slow
playlist or obsolete source from starting after a switch, edit, Pause, or Stop.
Track every actor, subscription, timeout, request, and process through its owner
and cleanup path. Keep the focused playback input target intact during a pending
command; the command guard suppresses duplicates without interrupting native gestures.

The two-minute service-readiness deadline accommodates cold GStreamer discovery;
child exit fails promptly and Stop/Quit can cancel startup. Stream connection or
rebuffering uses a cancellable 30-second one-shot deadline, not a recurring timer.
The service entry retains its standalone `#!@GJS@ -m` marker and runs with `gjs -m`.

### Desktop integration and identity

Use native Shell fonts, colors, focus, and light/dark styles; CSS controls compact
layout rather than replacing theme colors. The popup is fixed-width, with a
font-relative fixed-height infobox and mutually exclusive lower views. Keep URLs
in the editor, metadata subdued, row actions available to keyboard users, and
internal actions inside the open popup. Update MPRIS silently; legacy notification
fields remain compatible but never trigger song-change banners.

The indicator stays standalone unless an explicitly compatible cooperative group
exists. Never reparent arbitrary app indicators. Theme cleanup removes distinct,
identifiable styles only from this extension's directory, preserving the shared
Shell theme object, other styles, and unidentified registrations. Versioned CSS
and content-addressed UI modules support live updates; native GType identities
include the module URI so cached installations cannot collide.

Keep UUID `radiolina@drdaniloromano.github.io` stable. Service identifiers
`org.mpris.MediaPlayer2.GnomeRadio` / `org.gnome.Radio1` and the `gnome-radio`
config/cache names deliberately retain compatibility. Stable station IDs preserve
selection/history through edits. Storage validates before private atomic replacement;
unreadable existing configuration blocks mutations rather than destroying data.
Clipboard access writes only the editor URL; it does not read clipboard contents.

## Contained builds and configuration

With Podman and Make already installed:

```sh
make container-build
make container-test
make container-package
```

Development packages stay in the Fedora 43 image. Building the image needs network
access; the test container runs offline with a read-only source mount. Packaging
writes `build/radiolina@drdaniloromano.github.io.zip`; build/test commands do not
install the extension on your desktop. The ZIP contains runtime source, interfaces,
icons, metadata, CSS, and LICENSE, excluding repository docs and development/private files.

`make build` and `make test` use already installed host tools without installing
anything. The verified stack includes GJS 1.86, GLib/Gio/GLibUnix, GStreamer 1.26
with base/good plugins, libsoup 3, and desktop audio. Tests additionally use Python 3,
PyGObject, `dbus-run-session`, and `gst-launch-1.0`; Shell E2E needs native GNOME 49.

| Make variable | Default | Meaning |
| --- | --- | --- |
| `CONTAINER_ENGINE` | `podman` | Container command; supplied flags follow Podman. |
| `IMAGE` | `localhost/gnome-radio-dev:43` | Development image tag. |
| `OOM_SCORE_ADJ` | `500` | Playback-service kernel adjustment: integer 0–1000, or `inherit`. |

```sh
make build OOM_SCORE_ADJ=750
make container-package OOM_SCORE_ADJ=inherit
python3 scripts/build.py --oom-score-adj 750
```

The builder generates the packaged [build-config.js](../src/service/build-config.js)
without changing the source default; invalid values fail before replacing artifacts.
Only [resource-policy.js](../src/service/resource-policy.js), imported by the
service entry, writes `/proc/self/oom_score_adj` once. Shell's score is unchanged.
Missing/denied controls log a warning and leave playback operational. `inherit`
leaves the inherited adjustment intact. This sets a kernel preference, not a
universal kill order: other managers such as [systemd-oomd](https://www.freedesktop.org/software/systemd/man/latest/systemd-oomd.service.html)
use their own policies. There is no system-wide OOM setting or daemon dependency.
See [OOM verification and limitations](TESTING.md#oom-isolation-and-crash-recovery).

## Input and resource bounds

| Input | Bounds and behavior |
| --- | --- |
| Stations | Up to 200; names up to 80 characters; unique IDs and HTTP(S) URLs up to 2,048 characters without credentials/fragments. |
| Playlists | 256 KiB, three documents, five redirects, 15-second resolution deadline; first usable HTTP(S) entry. Reject circular sources, HLS, and XML declarations/DTDs. |
| Favicons | Origin `/favicon.ico`, sequential host-deduplicated requests, PNG/ICO only, 256 KiB and bounded dimensions, three redirects, five seconds; cached, cancellable, no refresh polling. |
| Recent | Ten retained unique played stations; 1–10 shown, default three. Lowering the display limit preserves history. |

Resource samples are service-only, not the incremental memory used inside Shell.
An offline-container idle sample measured 36.9 MiB RSS and 0.000 CPU seconds over
one second. A paused local-fixture sample measured 46.9 MiB RSS / 41.4 MiB PSS and
0.000 CPU seconds over 10.002 seconds; MPRIS Stop retained about 47.0 MiB RSS.
Infobox Stop instead exits that process. Shared libraries, allocator behavior,
streams, codecs, and audio sinks affect results; these are observations, not budgets.

## Release policy

The current local release is **0.2.0**; public distribution is pending.
Use `MAJOR.MINOR.PATCH`:
patches for fixes, minor increments for features/compatibility breaks during `0.x`,
and major increments for compatibility breaks after `1.0`. Set `version-name` in
[metadata.json](../extension/metadata.json); leave numeric submission versions to
[extensions.gnome.org](https://gjs.guide/extensions/overview/anatomy.html#version-name).

For a finalized release, date the changelog entry, tag the reviewed commit
`v{release}` (for example `v0.2.0`), build its ZIP, and record the checksum. A planned
version or Unreleased entry creates neither a tag nor a public release. Keep original
MIT notices in the package; platform dependencies retain their own licenses.
Retain the [provenance findings and review limits](PROVENANCE.md).
