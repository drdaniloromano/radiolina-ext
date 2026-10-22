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
        source["Validated HTTP response and bounded media identification"]
        store["Validated station storage"]
        service --> source --> player
        service --> store
    end
    ui -->|D-Bus commands| service
    service -->|D-Bus state updates| ui
    media["Media keys and native media card"] <-->|MPRIS| service
    stream["Radio stream"] -->|Audio and track metadata| source
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
| [src/core/](../src/core/) | URL/config validation, bounded playlist parsing, metadata sanitization and deduplication. |
| [src/core/validation/](../src/core/validation/) | Shared URL/redirect, configuration schema/text, and bounded byte-level audio/container admission policy. |
| [src/service/](../src/service/) | GStreamer, async playlists, atomic storage, D-Bus/MPRIS, process-local resource policy. |
| [radio.xml](../src/service/radio.xml) | App command/state contract; `State` is JSON in a D-Bus string property. |
| [tests/unit/](../tests/unit/) | Critical validation, metadata, parsing, and storage cases. |
| [tests/e2e/](../tests/e2e/) | Production service and actual Shell workflows using local fixtures. |
| [scripts/](../scripts/), [Makefile](../Makefile), [Dockerfile](../Dockerfile) | Contained builds, tests, packaging, and live-development helpers. |

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

### Stream validation and decoder boundary

Validation acts on URLs, redirect destinations, and initial response bytes. The
pure policies live in `src/core/validation/`; they have no Shell or GStreamer
dependency. `http.js` enforces redirect policy on actual libsoup requests;
`source.js` resolves bounded playlists and inspects up to 64 KiB through a native
`Gio.BufferedInputStream`. No extension-based playback shortcut or second GET
is used. HTTPS sources cannot fall back to HTTP, including through playlist entries.

`decoder.js` builds explicit pipelines from fixed, owned element names after
admission. Native `giostreamsrc` consumes the same inspected buffer/response;
ICY/ID3 handling and supported container parsers precede an allowed audio decoder.
There is no `playbin`/`decodebin`, decoder autoselection, media URI reopening,
video output, or JavaScript callback from a streaming thread. Codec alternatives
are explicitly enumerated; missing native components fail with a codec error.
MP4 headers are inspected for audio tracks and supported sample descriptions;
WAV is limited to PCM/float and Ogg to the allowed audio codecs.

Stop first aborts HTTP I/O, then stops the native pipeline and closes the stream.
Failed/stale loads close their response; generation guards and one-shot deadlines
remain in effect. This is bounded admission plus native format parsing, not a
proof that a malformed allowed format cannot exploit a native library bug.

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

Packaged metadata uses `radio-stylesheet` to select the owned layout stylesheet
and `radio-runtime` to identify the module for the same-session developer updater.
Both name local content-hashed files. The updater itself is not included in the ZIP.

Keep UUID `radiolina@drdaniloromano.github.io` stable. Service identifiers
`org.mpris.MediaPlayer2.GnomeRadio` / `org.gnome.Radio1` and the `gnome-radio`
config/cache names deliberately retain compatibility. Stable station IDs preserve
selection/history through edits. Storage validates before private atomic replacement;
unreadable existing configuration blocks mutations rather than destroying data.
Clipboard access writes only the editor URL; it does not read clipboard contents.

## Dependencies and codecs

Container development keeps tools contained; it does not make the extension ZIP
self-sufficient. The installed Shell UI and GJS service load the desktop host's
libraries and GStreamer plugins. None of those native libraries are bundled in
the ZIP or installed onto the host by the build scripts.

| Use | Required components | Where they must exist |
| --- | --- | --- |
| Installed extension | GNOME Shell 49/50; GJS and GI bindings for GLib/Gio/GLibUnix, GStreamer 1.x, and libsoup 3; session D-Bus and desktop audio. Shell supplies St/Clutter/Pango. | Desktop host. |
| Playback | Native GIO source, audio conversion/resampling/volume, buffering, and an available audio sink; parser/decoder for the chosen format. Base/Good plugins cover the verified common set, with AAC exceptions below. | Desktop host; a silent sink replaces desktop audio in tests. |
| Container packaging | Make, POSIX shell/basic user-ID tools, local Podman or Docker; network access for image creation. Python and development packages come from [Dockerfile](../Dockerfile). | Host needs the engine/Make, not the image's GJS/Python libraries. |
| CI adapter (`make ci-*`) | Existing Python 3.11+ standard library, Make and the local engine; no third-party host modules. | GitHub runner VM or already-equipped developer host; these targets install no host dependencies. |
| Direct packaging (`make build`) | Python 3 standard library; Make for the convenience target. No GJS/media stack is needed just to create the ZIP. | Existing host tools; no dependency installation. |
| Service/media tests (`make test`) | Runtime GJS/GI/GStreamer/libsoup plus Python 3, PyGObject, `dbus-run-session`, GStreamer command-line tools/fixture encoders, and OpenSSL. | Development image for `make container-test`; existing host tools for direct testing. |
| Shell tests | GNOME Shell 49/50 with headless rendering, Python/GI, service-test tools, and extension-management tools. | Versioned Shell container or disposable desktop; the smaller service image does not provide Shell. |

Python, Make, container engines, fixture encoders, and the OpenSSL command are
development tools, not installed-extension runtime dependencies. OpenSSL generates
temporary TLS-test certificates; tests trust their private CA only in a disposable
service copy and leave system trust unchanged. Additional codecs are needed only
for the formats you play. Packaging does not verify a destination PC's runtime.

### Per-format native elements

These are the explicit choices in [decoder.js](../src/service/decoder.js), not all
formats GStreamer might otherwise support. Package/plugin availability varies by
distribution; a missing decoder produces an error rather than an automatic install.

| Audio format/container | Required parser/decoder elements |
| --- | --- |
| MP3 | `mpegaudioparse` plus `mpg123audiodec`, `avdec_mp3`, or `mad`; preferred parser/decoder are in Good plugins. |
| AAC (ADTS/ADIF or admitted MP4 audio) | `aacparse` **and** one of `avdec_aac`, `fdkaacdec`, or `faad`. The parser alone cannot decode audio. |
| Ogg Vorbis | `oggdemux` plus `vorbisdec` or `avdec_vorbis`; the preferred pair is in Base plugins. |
| Ogg Opus | `oggdemux` plus `opusdec` or `avdec_opus`; the preferred pair is in Base plugins. |
| FLAC | `flacparse` plus `flacdec` or `avdec_flac`; add `oggdemux` for Ogg FLAC. Preferred native elements are in Good plugins. |
| PCM/float WAV | `wavparse` (Good), followed by raw-audio conversion; no compressed-audio decoder. |
| Audio-only MP4/M4A | `qtdemux` (Good), plus the parser/decoder of its admitted embedded codec; the `.m4a` extension alone does not establish AAC or decoder availability. |

All pipelines also use `giostreamsrc`, `queue2`, `audioconvert`, `audioresample`,
`volume`, and `autoaudiosink` with a working output backend. ICY and ID3 streams
add `icydemux` and `id3demux`. Tests use `fakesink`; silent decoding does not verify
the host's actual output device.

AAC is an important distinction: [aacparse](https://gstreamer.freedesktop.org/documentation/audioparsers/aacparse.html)
is in Good, whereas [avdec_aac](https://gstreamer.freedesktop.org/documentation/libav/avdec_aac.html)
comes from libav, and [fdkaacdec](https://gstreamer.freedesktop.org/documentation/fdkaac/index.html)
or [faad](https://gstreamer.freedesktop.org/documentation/faad/index.html) come from
Bad plugins. Both tested Fedora 43/GNOME 49 and Fedora 44/GNOME 50 images provide
the parser but none of these AAC decoders: their tests establish missing-codec
handling, not successful AAC playback. Neither original image has the libav plugin
or its permitted fallback decoders. The separate [AAC test profile](#optional-aac-test-profile)
adds Fedora's libav package and verifies real ADTS AAC and AAC-in-M4A playback.
Its wrapper uses the source build recorded in the
[security review](SECURITY.md#native-decoder-release-blockers).
An eligible decoder on the desktop host is required even when container packaging succeeds.

Inspect actual availability with already installed tools, for example
`gst-inspect-1.0 mpg123audiodec` or `gst-inspect-1.0 avdec_aac`; a missing factory
means that decoder is unavailable. See [format restrictions](USER_GUIDE.md#stream-formats-and-saved-data)
and [test coverage](TESTING.md#automated-coverage).

### Verified versions, not minimum-version claims

The Fedora 43 image was verified with GJS **1.86.0**, GLib **2.86.5**,
GStreamer/Base/Good **1.26.11**, and libsoup **3.6.6**. Development tools included
Python **3.14.8**, Make **4.4.1**, OpenSSL **3.5.9**, D-Bus **1.16.2**, and Podman
**5.8.4**. Headless Shell workflows have passed on GNOME **49.7** and **49.8**;
earlier GNOME **49.1** VM workflows have maintainer confirmation. Genuine Docker runtime remains untested here;
the available `docker` command delegates to Podman.

The versioned containers also verify Shell **49.10** / Mutter **49.8** on Fedora 43
and Shell/Mutter **50.6** on Fedora 44. The latter provides GJS **1.88.1**,
GStreamer/Base/Good **1.28.8**, and libsoup **3.6.6-10.fc44**. These functional
results do not close the native dependency findings or verify other vendor builds.

GNOME Shell **49 and 50** are declared by release 0.4.0; the 0.3.0 tag
declares 49. Lower GJS/GLib/GStreamer package
minimums have not been established by a compatibility matrix; the verified
versions above are examples, not proven minimums. GI namespace versions such as
`Gst-1.0` and `Soup-3.0` identify APIs rather than the exact installed package release.
These historical functional results do not approve those builds for publication:
the [native security review](SECURITY.md#native-decoder-release-blockers) found
missing GStreamer fixes in the reviewed 1.26.11 source packages. A fixed runtime
or verified backports and renewed compatibility checks are public distribution prerequisites.

For release verification, use supported distribution packages with the relevant
security fixes/backports. The Fedora 44 profile is the current reference for the
reviewed native fixes; GNOME 49/50 API compatibility is assessed separately.
This is not a universal minimum-version claim or a runtime version check.

## Contained builds and configuration

With Podman or Docker, and Make already installed (Linux, local engine):

```sh
make container-build
make container-test
make container-package
```

Podman is the default; select Docker explicitly for each command:

```sh
make container-build CONTAINER_ENGINE=docker
make container-test CONTAINER_ENGINE=docker
make container-package CONTAINER_ENGINE=docker
```

Development packages stay in the Fedora 43 image defined by [Dockerfile](../Dockerfile).
The image upgrades its base packages before installing development tools. Ordinary
builds may reuse cached layers. Before security/release verification, use
`make container-refresh` to pull the base and rebuild without cache, followed by
`make container-test` and `make container-security-check`. Add
`CONTAINER_ENGINE=docker` for Docker, or `IMAGE=localhost/radiolina-review:43` to
keep a separate review image. Podman uses `--pull=always`; Docker uses `--pull`.
This updates only the selected container image, never the host's packages.
Building the image needs network access. [.dockerignore](../.dockerignore), supported
by both engines, excludes everything except the recipes and ignore file from the
build context; the image contains dependencies rather than a copy of the checkout.
Tests and packaging run offline with only `extension/`, `src/`, `scripts/`, `tests/`,
and `LICENSE` mounted read-only. Private `workspace/`, Git metadata, credentials,
and the rest of the checkout are not mounted. Packaging mounts host-created
`build/` writable and writes `build/radiolina@drdaniloromano.github.io.zip`.
Shell checks mount only a newly created evidence subdirectory writable, as below.

[Identity selection](../scripts/container-user-flags.sh) detects the actual CLI,
including Docker commands backed by Podman. Podman uses `--userns=keep-id`.
Rootful Docker uses the caller's numeric UID/GID with `--userns=host` to avoid
daemon remapping; rootless Docker uses container UID/GID 0, mapped to its host
user. Run rootless Docker as the same user who owns the checkout. See Docker's
[UID/GID mapping](https://docs.docker.com/engine/security/rootless/uid-gid-mapping/).
No `sudo`, host `chown`, or checkout relabeling is needed; the containers use
`--security-opt label=disable` for SELinux bind-mount access. Remote daemons and
Docker Desktop are outside this local-Linux workflow's verification scope.

Build/test commands do not install the extension on your desktop. The ZIP contains
runtime source, interfaces, icons, metadata, CSS, and LICENSE, excluding repository
docs and development/private files. Rebuild the image after changing Dockerfile;
ordinary source edits are visible through the explicit read-only mounts.

`make build` and `make test` use already installed host tools without installing
anything; their different requirements are listed in the [dependency table](#dependencies-and-codecs).

### Optional AAC test profile

[Dockerfile.aac](../Dockerfile.aac) derives a separate Fedora 44 codec-test image
from the existing GNOME 50 profile. It installs the vendor libav package inside
that image; normal images, packaging dependencies and host libraries are unchanged.

```sh
make container-shell-build SHELL_VERSIONS=50 # Only if the base image is missing.
make container-aac-build
make container-aac-test
```

Use `CONTAINER_ENGINE=docker` consistently for Docker. Override `AAC_BASE_IMAGE`
with an inspected immutable image ID for repeatable review, and `AAC_IMAGE` for a
separate tag. Builds query vendor repositories; tests are offline, mount only
allowlisted sources and use the normal invoking-user identity rules.
`container-aac-test` sets `REQUIRE_AAC=1`: absent fixture encoders or decoders fail
the positive test. Ordinary tests skip that case when unavailable and retain the
separate missing-codec test. Neither test downloads codecs or public streams.

The verified profile uses GStreamer/libav **1.28.8-1.fc44** and actual loaded
`libavcodec-free` **8.1.3-1.fc44**. Local generated ADTS AAC and AAC-in-M4A streams
pass playback, pause/resume and same-response checks with silent output.
This adds codec/service coverage, not another full Shell matrix or physical audio
acceptance. Genuine Docker remains untested. See [testing](TESTING.md) and
[security scope](SECURITY.md#release-priorities).

### Versioned Shell test containers

[Dockerfile.shell](../Dockerfile.shell) supplies an actual headless GNOME Shell,
Mutter, GJS, fonts, software renderer and playback libraries. The service image
remains smaller and separate. Build/run GNOME 49 with:

```sh
make container-shell-build SHELL_VERSIONS=49
make container-shell-test SHELL_VERSIONS=49
make container-test IMAGE=localhost/radiolina-shell-test:49
make container-shell-test SHELL_VERSIONS=49 SHELL_SCALE=1.5 SHELL_THEME=light
```

Use `CONTAINER_ENGINE=docker` for the local Docker engine. Use
`container-shell-refresh` instead of `container-shell-build` to pull/rebuild without
cache. Profiles map GNOME 49 to Fedora 43 and GNOME 50 to Fedora 44;
the image build rejects an unexpected Shell major. A profile's existence does not
declare support: the runner also checks the package's `shell-version` metadata.
The default `SHELL_VERSIONS="49 50"` runs both profiles sequentially; a per-checkout
lock rejects concurrent Shell builds/tests. To test the same core/service suite
against the newer libraries, run `make container-test IMAGE=localhost/radiolina-shell-test:50`.

These images are test fixtures, not a Fedora dependency of the extension. Other
distributions can supply the required GNOME/GJS/native stack; report the versions
actually tested without turning image choices into distribution restrictions.
Keep the current contained profiles as the default; do not build a full guest OS
just to repeat their UI tests.

The runner uses the inspected image ID, read-only root/source mounts, no network,
no extra capabilities, and no host bus, display, GPU or audio sockets. Private
temporary storage holds a copied checkout, generated packages, HOME/XDG state, settings and the
activation-free test bus, also used for system-bus connections. Fractional runs
enable `scale-monitor-framebuffer` only in private settings where Mutter exposes
that experimental feature, then verify the actual monitor scale. Only a new mode-700
directory under `build/shell-tests/{major}/` is writable on the host; logs,
screenshots, runtime package inventory, ZIP/payload checksums, source fingerprint, image identity and
exit status stay there. Files retain the caller's ownership. Each run is limited
to 1 GiB memory, two CPUs, 256 processes, and ten minutes; llvmpipe uses two threads.
Containers are removed on completion/failure/interruption, while evidence remains.

This tests a selected distribution/runtime on the host kernel, not every distro
or native security patch status. No real system services are supplied by the test
bus; silent audio, headless rendering and virtual input do not establish physical
media keys, real audibility, lock/suspend integration or hardware compatibility.
Use [targeted manual checks](TESTING.md#manual-acceptance) when an isolated desktop
is available, and retain untested physical scope explicitly. Full desktop VMs are
optional. The [dependency review](SECURITY.md) remains separate.

| Make variable | Default | Meaning |
| --- | --- | --- |
| `CONTAINER_ENGINE` | `podman` | `podman` or `docker`; runtime identity flags adapt to the actual engine. |
| `IMAGE` | `localhost/gnome-radio-dev:43` | Development image tag. |
| `OOM_SCORE_ADJ` | `500` | Playback-service kernel adjustment: integer 0–1000, or `inherit`. |
| `SHELL_VERSIONS` | `49 50` | Space-separated versioned Shell profiles to build/test sequentially. |
| `SHELL_IMAGE_PREFIX` | `localhost/radiolina-shell-test` | Shell test image prefix; the major is its tag. |
| `SHELL_SCALE` / `SHELL_THEME` | `1` / `dark` | Shell test monitor scale (`1`/`1.5`) and initial theme (`light`/`dark`). |

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

## GitHub Actions test and build

The [workflow](../.github/workflows/ci.yml) prepares **development artifacts**;
it has no release, registry, or GNOME submission job. It uses a standard
`ubuntu-24.04` VM and genuine Docker. GNOME dependencies stay in the Fedora
containers, with Podman still supported for local development. Local validation
does not establish a successful Actions run or genuine Docker compatibility;
both remain unverified until observed on that backend.

### Triggers, tests and image maintenance

Pushes to `main`, pull requests and manual dispatch run one sequential job.
Feature-branch pushes do not duplicate PR runs; obsolete runs on the same PR/ref
are cancelled. No tag trigger, write token, publication secret or
`pull_request_target` is used. Official actions are pinned to reviewed commits
(checkout 6.1.0, cache 5.1.0, upload-artifact 7.0.2; Node 24). The workflow validator
also uses an immutable container digest; update pins deliberately and revalidate.

The adapter reuses Make: profile 49/Fedora 43 and profile 50/Fedora 44 each run
the full offline suite plus actual headless Shell at dark/100% and light/150%.
The existing assertions exercise both themes, large text, lifecycle and OOM
recovery; screenshots still need human review. A separate 50-based AAC profile
requires actual ADTS/M4A decoding. Packaging follows all required successful
tests and verifies the final payload against both Shell-tested packages.
Tests retain private buses/settings, silent audio, no network or host desktop
sockets, and owned cleanup. CI service runs also have 1 GiB/two CPU/256 PID caps;
Shell runs retain their ten-minute cap. The overall job is capped at 60 minutes,
which is a ceiling, not an observed typical duration.

Dependency-only images are gzip archives in `build/ci-cache/`, separate from
test artifacts. Exact cache keys include profile, runner OS/architecture,
Dockerfile/build inputs and [.github/ci-image-generation](../.github/ci-image-generation).
Ordinary application-source edits reuse images. Restores verify archive SHA-256,
inputs and loaded image ID; test evidence records actual IDs and RPM versions.
Only trusted main runs save shared caches; PRs may restore but do not save them.
An absent/evicted cache rebuilds the image. Manual **refresh_images** bypasses
cache and rebuilds with refreshed container packages; this does not approve them.
To adopt a reviewed baseline for normal runs, increment the tracked generation
in a focused change after the [security review](SECURITY.md). Cached functional
tests never replace advisory checks or update users' desktop libraries.

Run the same orchestration locally (it resets only `build/ci/`):

```sh
make ci-start
make ci-image CI_PROFILE=49
make ci-test CI_PROFILE=49
make ci-image CI_PROFILE=50
make ci-test CI_PROFILE=50
make ci-image CI_PROFILE=aac
make ci-test CI_PROFILE=aac
make ci-package
make ci-evidence
```

Add `CONTAINER_ENGINE=docker` consistently for genuine Docker. Existing local
images can be inspected/tested with `CI_IMAGE_FLAGS=--reuse-local` and
`CI_IMAGE_PREFIX`/`CI_AAC_IMAGE` environment overrides; this mode never seeds a
shared cache and is rejected in Actions. `CI_IMAGE_FLAGS=--refresh` requests an
uncached rebuild. Do not invoke `ci-start` during an active run.

### Downloading and installing the artifact

Open **Actions → Test and build → successful run → Artifacts**, then download
`radiolina-install-<commit>`. GitHub may require sign-in. Extract the outer
artifact archive; install the inner **radiolina@drdaniloromano.github.io.zip**,
not the outer archive or GitHub's source-code ZIP. `SHA256SUMS` and
`verification.json` identify its checksum, source and tested runtimes:

```sh
sha256sum -c SHA256SUMS
gnome-extensions install --force radiolina@drdaniloromano.github.io.zip
```

Installation needs the [desktop runtime](#dependencies-and-codecs), but no
checkout, Make or container tools. Follow the [installation guide](USER_GUIDE.md#same-session-installation-and-updates)
to enable/reload the extension. CI outputs expire after **7 days**; selected
test logs/measurements/screenshots, including failures, expire after **3 days**.
Logs have URL redaction and a 1 MiB tail limit; the selected evidence budget is
25 MiB/run with 5 MiB/file limits. Full raw local logs remain under `build/ci/`.
Only staged allowlisted outputs are uploaded, never private workspace, saved
stations, credentials, account inventory or the entire build tree.

### GitHub settings and cost limits

Before separately authorizing a push/run, verify repository visibility and
**Settings → Actions → General**: permit the pinned official actions, keep the
default workflow token read-only, and retain approval requirements for untrusted
fork workflows. Allow the configured cache/artifact retention within account
policy. No PAT, deployment environment, registry login or paid runner is needed.
Do not change settings or grant publication access just to prepare this workflow.

As checked on **2026-10-22**, [standard runner compute](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
is free for public repositories; private GitHub Free includes 2,000 minutes/month.
The VM has 14 GB SSD and either 4 CPUs/16 GB RAM (public) or 2 CPUs/8 GB (private).
Visibility is currently unverified; no public-repository billing assumption is made.
[GitHub Free storage](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
includes 500 MB artifacts shared with Packages and a separate 10 GB cache allowance.
[Cache eviction](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
can occur after seven days without access or at capacity; leave paid expansion
disabled. Each compressed profile is capped at 3 GiB. The workflow removes owned
archives/images between profiles to limit ephemeral disk usage; multiple cache
generations can still cause eviction. There are two uploaded artifacts per run,
well below the action's [500-per-job limit](https://github.com/actions/upload-artifact#number-of-artifacts).
Configured retention cannot exceed repository policy. The hosted job maximum is
[six hours](https://docs.github.com/en/actions/reference/limits); our cap is lower.

Actual remote cold/warm durations, peak disk and storage are **unmeasured**. Record
them on the first authorized run, compare monthly runs × observed runner-minutes
with private allowances, and shorten retention if needed. Neither green CI nor
an empty vendor advisory result clears [open findings](SECURITY.md#release-priorities).
Hardware audio/keys, real lock/suspend and destination desktops are outside this CI.

## Input and resource bounds

| Input | Bounds and behavior |
| --- | --- |
| Configuration | 1 MiB UTF-8 JSON; bounded reads stop after one overflow byte before parsing, without relying on a size check. Reject unknown top-level/station fields; publish only explicit schema fields. Private atomic writes use the same validation/byte limit. Invalid files remain untouched and service mutations stay blocked until repair/restart. |
| Stations | Up to 200; names up to 80 characters; unique ASCII IDs up to 128 characters and HTTP(S) URLs up to 2,048 characters without credentials/fragments. |
| Playlists | 256 KiB, three documents, five redirects, 15-second resolution deadline; first usable HTTP(S) entry. Reject circular sources, HLS, and XML declarations/DTDs. |
| Audio identification | 64 KiB prefix, within the 15-second source-loading deadline; explicit audio container/codec policy, with no second audio GET. ID3/MP4 headers must fit; MP4 must be streamable. |
| Legacy favicons | Fetching and image loading are removed. Accept the old boolean field and D-Bus setter as inactive compatibility inputs; never read/write the old cache. |
| Recent | Ten retained unique played stations; 1–10 shown, default three. Lowering the display limit preserves history. |

Configuration schema/defaults live in
[validation/config.js](../src/core/validation/config.js); Store owns bounded I/O.
The existing `stations.js` exports remain compatible. Version-1 files can omit
newer optional settings; accepted configs are copied into known-field objects.
These limits constrain local configuration allocation and IPC, not
remote media attacks or malicious same-user processes. Oversized State propagation
was reproduced before the fix; no memory-exhaustion or Shell crash was attempted.

Resource samples are service-only, not the incremental memory used inside Shell.
Before validation hardening, an offline-container idle sample measured 36.9 MiB RSS and 0.000 CPU seconds over
one second. A paused local-fixture sample measured 46.9 MiB RSS / 41.4 MiB PSS and
0.000 CPU seconds over 10.002 seconds; MPRIS Stop retained about 47.0 MiB RSS.
Infobox Stop instead exits that process. Shared libraries, allocator behavior,
streams, codecs, and audio sinks affect results; these are observations, not budgets.

The validation branch's offline suite also measured idle RSS 36.9 MiB with 0.000
CPU seconds over one second. A separate paused ICY fixture measured 49.0 MiB RSS /
43.4 MiB PSS with 0.000 CPU seconds over five seconds. Finite playback-cycle probes
showed native descriptors being reclaimed after idle/diagnostic GC in a disposable
copy; no production GC timer was added and long-duration leak freedom is not established.

After favicon retirement, an opt-in ten-minute probe completed 101 playback,
pause, switch, failure and cancellation cycles without forced GC. Sampled RSS
was 47.4 MiB after warm-up, peaked at 49.1 MiB and ended at 48.9 MiB; descriptors
ranged from 10 to 16, ending at 12, with 12 threads and no fixture connections.
The last 30 seconds consumed 0.000 service CPU seconds; Quit reaped the process.
PSS changed with concurrent shared mappings, so these are bounded observations,
not proof of leak freedom or incremental Shell-memory budgets.

## URL privacy and diagnostics

MPRIS omits `xesam:url` entirely, including for public streams: secrets can occur
in paths as well as query strings. Keep track IDs, station/title/artist and media
controls; the [MPRIS metadata contract](https://specifications.freedesktop.org/mpris/latest/Player_Interface.html#Property:Metadata)
requires a track ID, not a URL. The playback response owns its final URL internally;
the application `State` no longer exports `resolvedUrl`.

[UserError/publicErrorMessage](../src/core/errors.js) marks code-authored public
messages and sanitizes/bounds them to 384 characters. Never put URLs, server text,
user input or a native error's message into `UserError`. Boundary handlers replace
unexpected/native errors with fixed fallbacks. Playback warnings also use fixed
messages; codec/HTTP-status/validation guidance remains specific.
No raw-error opt-in logger or polling is introduced. External native debugging is
outside this policy and its output must be reviewed before sharing.

Full saved URLs remain necessary for station editing/Copy and are exposed in
station-management state and private plaintext storage. This reduces unnecessary
metadata/diagnostic disclosure; it is not a boundary against same-user processes.
See [user-facing privacy limits](USER_GUIDE.md#url-privacy).

## Release policy

Use the opt-in [dependency advisory procedure](SECURITY.md) before finalizing a
release. Machine-readable reports can feed future preflight automation; vendor
query success alone does not satisfy the upstream/applicability review.

The current local release is **0.4.0**; public distribution is pending the final
[security priorities](SECURITY.md#release-priorities) and package review. Missing
full-VM/hardware coverage alone does not block release; document its limitations.
Use `MAJOR.MINOR.PATCH`:
patches for fixes, minor increments for features/compatibility breaks during `0.x`,
and major increments for compatibility breaks after `1.0`. Set `version-name` in
[metadata.json](../extension/metadata.json); leave numeric submission versions to
[extensions.gnome.org](https://gjs.guide/extensions/overview/anatomy.html#version-name).

For a finalized release, date the changelog entry, tag the reviewed commit
`v{release}` (for example `v0.3.0`), build its ZIP, and record the checksum. A planned
version or Unreleased entry creates neither a tag nor a public release. Keep original
MIT notices in the package; platform dependencies retain their own licenses.
Retain the [provenance findings and review limits](PROVENANCE.md).
