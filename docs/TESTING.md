# Testing

## Commands

Run from the repository root; use existing tools rather than installing host dependencies.
The default is offline service E2E plus real headless GNOME Shell containers for
each supported Shell version. Full desktop VMs are optional, not a routine release
prerequisite. Fedora supplies the current test images; it is not an extension
runtime requirement or evidence of compatibility with every distribution.

| Command | Purpose |
| --- | --- |
| `make container-build` | Build the Fedora 43 development image; network access required. |
| `make container-refresh` | Pull/rebuild without cache and refresh packages inside the image before security/release checks. |
| `make container-test` | Offline packaging/security-tool/launcher/CI-boundary E2E, 13 critical unit cases, 19 service E2E cases, and 10 transport/media/privacy cases (positive AAC skips without codecs). |
| `make container-shell-build SHELL_VERSIONS=49` | Build the version-specific headless Shell image, with dependencies contained. |
| `make container-shell-test SHELL_VERSIONS=49` | Run the actual popup/lifecycle/OOM suite in the offline Shell container. |
| `make container-shell-build` / `make container-shell-test` | Build/test both supported profiles (49/Fedora 43 and 50/Fedora 44) sequentially. |
| `make container-shell-test SHELL_SCALE=1.5 SHELL_THEME=light` | Repeat both Shell profiles at 150% scale with light/dark checks. |
| `make container-test IMAGE=localhost/radiolina-shell-test:50` | Run the offline core/service suite against GNOME 50's GJS/native libraries. |
| `make container-aac-build` / `make container-aac-test` | Build a separate codec image from the existing GNOME 50 profile; require real ADTS AAC and AAC-in-M4A playback/control tests. |
| `make container-resources` | Opt-in ten-minute Linux resource E2E in the offline image; local fixtures, private D-Bus/XDG, silent audio, no forced GC. |
| `make test-resources` | The same probe using already installed host tools and isolated state. |
| `make container-package` | Write the runtime ZIP under `build/`. |
| `make container-check-package PACKAGE_ZIP=build/radiolina@drdaniloromano.github.io.zip` | Analyze an already-built ZIP with pinned Shexli. Initial tool-image build needs network; analysis is offline and limited to the package. |
| `make ci-start`, then `ci-image`/`ci-test CI_PROFILE=49`, `50`, `aac`, then `ci-package`/`ci-evidence` | Run the local equivalent of Actions, gate the installation ZIP on current successful tests, and stage allowlisted evidence. See [CI commands and artifacts](DEVELOPMENT.md#github-actions-test-and-build). |
| `make test` | Run packaging/unit/service/transport-media checks with already installed host tools. |
| `python3 tests/e2e/package.py` | Packaging check alone; Python standard library only. |
| `python3 tests/e2e/release.py` | Offline release builds/uploads with real temporary Git repositories/ZIPs and a fixture GitHub API; existing Git and Python only. Runs once on the Actions runner, outside the GNOME dependency images. |
| `python3 tests/e2e/package_check.py` | Offline analyzer-gate cases: zero-exit findings, crash/malformed report rejection, ZIP-only container mount and unrelated-file preservation. |
| `make test-shell OOM_SCORE_ADJ=500` | Build and run the real popup/lifecycle/OOM workflow using an already installed GNOME 49/50. |
| `GNOME_RADIO_TEST_SCALE=1.5 GNOME_RADIO_TEST_THEME=light make test-shell` | Repeat at 150% monitor scaling with light/dark checks. |
| `git diff --check` | Check patch whitespace. |
| `make security-check` / `make container-security-check` | Opt-in networked dependency/advisory reports; follow [security procedure](SECURITY.md). |

Repeat relevant container commands with `CONTAINER_ENGINE=docker` to verify
Docker independently. A Docker CLI backed by Podman is not an independent Docker
result. Report engine versions and unavailable/untested engines. Check that files
under `build/` belong to the invoking host UID/GID after packaging.

See [build configuration](DEVELOPMENT.md#contained-builds-and-configuration) and
[user installation/update procedures](USER_GUIDE.md#same-session-installation-and-updates).
The [dependency table and codec requirements](DEVELOPMENT.md#dependencies-and-codecs)
distinguish host runtime, packaging, and testing tools. OpenSSL is required for
local TLS fixtures in the full suite; it is included in Dockerfile and is not an
extension runtime dependency. Container packaging supplies no host runtime libraries.

## Isolation requirements

- Service container tests use `--network=none`, explicit read-only source mounts, private XDG paths
  and D-Bus, generated local MP3/ICY fixtures, and synchronized silent audio.
  Private workspace/credentials/Git are excluded from the build context and mounts;
  packaging exposes `build/` writable, while Shell evidence is limited as below.
  Public streams never gate automated checks.
- Host Shell E2E needs an already installed GNOME 49/50 Shell/rendering backend. Its private
  D-Bus/XDG/settings/display isolate input, install/update/uninstall, typography,
  and lifecycle from the user's desktop. Host service activation stays disabled.
- Versioned Shell containers provide that backend without host dependency installs.
  They use private HOME/XDG and an activation-free bus for session/system connections,
  offline software rendering/silent audio, read-only inputs/root and a fresh output
  directory under ignored `build/shell-tests/`. No host home, workspace, sockets,
  physical devices or system bus is mounted. A lock enforces sequential runs; limits are
  1 GiB memory, two CPUs, 256 processes and ten minutes per run. See
  [container setup](DEVELOPMENT.md#versioned-shell-test-containers).
- The evaluator bootstrap exists only on that disposable Shell; it is never
  packaged. Do not enable remote Eval or unsafe mode in the host Shell.
- Headless Shell is process/settings isolation, not a security sandbox or full VM.
  Its wallpaper is disabled and llvmpipe uses two threads to limit test overhead.
- If full-desktop checks are useful, use an available isolated desktop. Do not
  download an OS image or provision a VM as an automatic next step. If a VM is
  deliberately used, verify its signed image, disable host sharing/clipboard
  transfer, use a guest-only account and stop it afterward. Keep unavailable
  physical checks explicitly untested; do not simulate them by exposing host
  audio/display/system-bus sockets to the automated containers.
  Prefer a minimal guest with selected GNOME/login/audio packages and disposable
  disk overlays. Verify its Shell major and measure setup/download/disk/RAM costs;
  a tiny base image does not establish a lightweight installed desktop. Record
  differences such as OpenRC/elogind versus systemd/logind in the coverage scope.

Logs, screenshots, and measurements go to ignored `workspace/`, including
`shell-e2e.log`, `playback-hover-{light,dark}.png`, `large-text-*.png`, and
`shell-oom-recovery.json`. Keep temporary fixtures and VM assets outside Git.

## Automated coverage

Three offline security-tool E2E cases exercise command boundaries, recursive
inventory, private reports, findings, partial repository failures and missing or
malformed data. Fake tools never contact vendor services; live queries are
separate checks whose findings/limitations must be reported.
Six launcher E2E cases use fake engines to cover private mount/resource boundaries,
sequential versions, per-checkout locking, failure/interruption cleanup/status retention, rejected
profiles/engines, and Podman/Docker refresh/identity contracts. They do not substitute
for genuine Docker execution or actual per-version Shell tests.

Five CI boundary E2E cases cover cache hit/refresh/corruption, failed-service owned
cleanup, failed/stale/missing test gates, real ZIP source/exclusion checks, and
allowlisted/redacted output. They also verify that restore-only cold builds retain
runtime evidence without exporting unused image archives, and reject invalid cache
policy before image preparation. Their fake engines do not establish Docker support.
Run them alone with `python3 tests/e2e/ci.py`; they also run in the contained suite.
A container-identity regression checks unknown numeric UID/GID provisioning,
idempotence, existing-account preservation and invalid-ID rejection. Reproduce
D-Bus identity failures with automatic engine account injection disabled; keep
EXTERNAL authentication and host account isolation intact.
The Actions workflow runs both supported profiles sequentially and the
positive AAC profile. The first genuine Docker run failed private D-Bus
authentication before service cases; after numeric-account provisioning,
[run 39822728172](https://github.com/drdaniloromano/radiolina-ext/actions/runs/39822728172)
passed all three profiles (56 passes and one expected codec skip each), four
Shell runs and package/artifact verification on Docker 28.0.4. All four popup
screenshots were reviewed. Each new PR revision still requires its own green
checks; physical acceptance stays separate.

Release-workflow E2E cases cover fresh tagged-source builds, successful main-only
CI selection, deterministic rebuilds, source/version/package checks, rejection of
tagged tooling and symlinks, cross-host credential stripping, API response bounds,
changed tags/staging, asset conflicts, immutability, dry runs and idempotent retries.
They perform no network requests or release writes. Actual GitHub build preparation
and attachment dry-run are separate read-only checks; they do not verify the
write-capable job or published assets. The release ZIP is rebuilt from tested
source and checked file by file; this workflow does not execute it inside GNOME.

The contained Shexli check runs after ZIP creation and before either upload path.
Local Podman tests verify real warning/manual-review output and rejection of a
malformed-metadata ZIP with two errors, despite the analyzer's zero exit code.
Five fixture cases cover the gate's isolation and failure handling. Genuine Docker
for this new step remains untested locally (`docker` is a Podman wrapper).
See [static-review policy and coverage limits](DEVELOPMENT.md#post-build-static-review).

Local adapter verification on **2026-10-22**, Podman 5.8.4: all three offline
profiles pass 55 cases with one expected codec-related skip each. Actual Shell
49.10/50.6 pass both scale/theme runs; service score stays 500 through SIGKILL/
Play recovery while Shell stays 200. The verified installation payload matches
all four Shell runs. A dependency-image cache round-trip retains its image ID
(479 MiB compressed). These results do not establish remote Actions or Docker.

The versioned Podman profiles passed all 51 offline cases each, plus actual Shell
workflows on **49.10/Fedora 43** and **50.6/Fedora 44** at 100% and 150% monitor
scale. Light/dark, Serif 12 at 125% text scale, popup controls, same-session updates,
repeated lifecycle and OOM/crash recovery passed. Final matrix source fingerprints
and package-content checksums match; ZIP checksums also record each archive's
timestamp-dependent bytes. Screenshots were visually reviewed. This establishes
the documented automated scope, not native patch status, real audio/physical keys,
full lock/suspend integration or genuine Docker behavior.

| Area | Required coverage |
| --- | --- |
| Package | Source fidelity, MIT/license inclusion, UUID/version/support/clipboard metadata, private/development exclusions; valid/invalid OOM build settings without source-default changes. |
| Critical unit | URL/config validation, 128-character IDs, unknown-field rejection, exact 1 MiB/overflow bounded reads and closure, invalid UTF-8 preservation, canonical private storage and legacy defaults; metadata/playlist bounds and safe diagnostics. No numerical coverage threshold. |
| Service E2E | Real decoding/MPRIS, CRUD/edit persistence, rejected-file preservation/write blocking/compact error state and playback after manual repair, Recent, inactive legacy favicon flag/setter without requests or cache changes, HTTP failures/deadlines, stale-load cancellation, idle resources, Shell-owner loss, OOM overrides/inheritance/denial/restart. |
| Transport/media E2E | Actual same-response decoding, misleading extensions/headers, HTML/HLS/video rejection before decoder construction, bounded ID3/ICY/gzip playlists, five-hop redirect boundary, credentials/fragments/schemes, trusted local TLS upgrade/downgrade and playlist-entry policy. |
| Privacy | Token-bearing path/query URLs reach actual playback unchanged; MPRIS properties/signals omit URLs and State omits final redirects. Full saved/editor URLs and private mode persist. Disposable native/JS error traps cover HTTP, player bus, startup and saves without exposing injected secrets in application errors/logs; public-message unit bounds remain enforced. |
| Shell E2E | Real ZIP install/replacement/uninstall and legacy-ID migration; saved bytes preserved; native pointer/keyboard controls, shared playback hover/focus, row-action exit, search, 30/70 editor, mutually exclusive views, optional Stop, fixed dimensions/aligned spacing, state icons, silent native media card, service crash/recovery. |
| Theme/lifecycle | Native light/dark changes, 100%/150% display scales, Serif 12 with 125% text scaling, cached-module/CSS updates, asynchronous interface loading (responsive popup, late result after disable, replacement readiness, cancelled native read, missing/malformed XML recovery), retained buttons cannot call destroyed row/indicator owners, retired signal trackers removed, delayed startup/cancellation/early exit, rapid Stop/restart, disable/enable, foreign indicator/style ownership, unsupported grouping fallback. |

The service tests execute the packaged-compatible standalone GJS entry. The
transport-stall test disables the HTTP source's timeout in a disposable copy to
exercise the app's own fallback, including Pause cancellation. Shell tests use
real virtual pointer/keyboard events; silent output cannot establish audibility
or physical-key routing. Third-party themes and hardware suspend are not implied.

Validation fixtures generate MP3, FLAC, Vorbis/Opus Ogg, WAV, MP3/Opus MP4,
and video locally. TLS tests trust an ephemeral CA only inside a disposable service
copy, with certificate verification enabled. Both tested GNOME 49/Fedora 43 and
GNOME 50/Fedora 44 images lack AAC decoders and exercise the missing-codec error,
not successful AAC decoding. The separate Fedora 44 AAC profile adds the vendor
libav plugin and passes locally encoded ADTS AAC and AAC-in-M4A playback,
pause/resume, Stop and one-GET checks. Its full suite runs 52 cases: 51 pass and the
missing-codec case skips; the original profile separately passes that case and
skips positive AAC. `REQUIRE_AAC=1` fails if positive-test prerequisites are absent.
No real device output, ADIF, other AAC decoders or every channel/profile combination
is implied. See the [optional profile](DEVELOPMENT.md#optional-aac-test-profile).
Native parser security is not established by these functional cases.

## Resource cleanup

The separate ten-minute resource probe samples RSS/PSS, CPU, descriptors/sockets,
threads and active fixture connections. It warms up for 30 seconds, cycles until
510 seconds, then observes 90 seconds idle. No GC hook or production timer is
added. Early safety ceilings are 256 MiB RSS, 256 descriptors and 64 threads;
final idle allowances are warm-up +24 descriptors, +4 threads, +32 MiB PSS and
under 0.5 CPU seconds in the last 30 seconds. These are regression tolerances,
not universal budgets or proof of leak freedom. Output is JSON-prefixed stdout;
redirect it to ignored `workspace/`. Shell checks additionally repeat ten
disable/enable cycles and five pending-backend-start cancellations.

Completed probe: 101 cycles in 600.482 s, peak sampled RSS 49.1 MiB/16 descriptors;
final idle 12 descriptors/12 threads, no fixture connections and 0.000 CPU seconds
over the last 30 seconds. The full GNOME 49.8 workflow passed in 85.699 s with
all lifecycle repetitions and OOM recovery; no runtime GC timer was needed.

## OOM isolation and crash recovery

The default-build Shell test records Shell's inherited score before any backend
starts, resolves the child PID against its private D-Bus owner, and verifies only
the playback service receives `oom_score_adj=500`. It SIGKILLs that verified child
without allocating memory. The same Shell PID and indicator must survive with
cleared metadata, retry feedback, unchanged selection/config bytes, and working
panel close/reopen clicks. No automatic restart is allowed.

One real Play click must create a new PID/bus owner, restore fixture playback and
metadata, reapply score 500, and clear the error. Shell and test-runner scores must
remain unchanged. Assertions and measured PIDs/scores are recorded in
`workspace/shell-oom-recovery.json` after success.

Completed verification on GNOME 49.7: Shell **200 → 200**, playback service
**500 → 500** across SIGKILL/recovery; the full Shell workflow passed in 112.738 s.
The offline suite passed all 9 critical cases and 18 service cases (150.916 s).
This tests abrupt service death and recovery, not kernel victim selection,
actual low-memory survival, hardware behavior, or systemd-oomd policy.

The subsequent privacy-hardening workflow also passed on isolated GNOME 49.8
(84.525 s): native media card/editor Copy, Stop exit, unchanged Shell score 200,
service score 500 before/after SIGKILL, and one-click playback/metadata recovery.
The same OOM verification limitations apply.

## Manual acceptance

Use this checklist for targeted checks when an isolated desktop is available.
Reuse prior confirmations and repeat checks affected by changes or reported bugs;
do not require a full VM matrix for every release. Record the exact build and
environment. Unavailable audio/hardware/suspend checks remain documented coverage
limits, not automatic release blockers or implied passes. Confirmed defects still
need assessment under the [release priorities](SECURITY.md#release-priorities).

1. Install the actual ZIP, enable it, and add a direct stream from
   [Nightride FM](https://nightride.fm/). Confirm audible playback, pause/resume,
   station switching, and saved data after restart. Check real M3U/XSPF streams
   and codec availability; playlist parsing alone does not establish endpoint availability.
2. Check native light/dark/high contrast, long labels, keyboard focus/navigation,
   larger fonts/scales, fixed popup width, aligned controls/separators, and fields
   contained within the popup. Shared playback hover must clear after input ends.
3. Press physical Play/Pause keys, including with another MPRIS player running.
   Check static active/inactive icons and the native media card. With Do Not Disturb
   on/off, song changes must remain silent without popup banners or duplicate cards.
4. Test Stations expansion/type-to-search/Ctrl+F/clear, editing without triggering
   search, hover/focus Play/Edit/Remove, editor Copy, validation, and rename/source
   changes during playback. Actions keep the popup open; normal dismissal still works.
5. Play four stations; verify default three-entry Recent, 1–10 settings, retained
   history/order, absent favicon controls, and default-hidden Stop.
   Stations, Add/Edit, and Settings must replace one another.
6. Disconnect/reconnect networking. Expect a useful persistent error, cleared
   metadata, responsive controls, and successful explicit Play retry.
7. Enable Stop: verify backend exit with indicator retained, Play recovery,
   editing after Stop, and rapid Stop/Play. Quit/disable must remove UI and service
   while preserving data; re-enable must restore stations, not autoplay.
8. Verify grouping defaults off with its warning. Without a supported host it
   stays standalone; other indicators' placement, menus, styles, and lifecycle
   remain unchanged through updates, disable, and recovery.
9. Lock during playback: audio stops; unlock restores an idle indicator until Play.
   Test suspend/resume only after the environment can complete a baseline sleep/wake
   cycle. A hung VM does not establish an applet cause or hardware compatibility.

Maintainer-confirmed GNOME 49.1 VM results cover audible Nightride playback, basic
physical Play/Pause, lock/unlock without autoplay, and native light/dark/high-contrast
readability/focus. Those confirmations do not cover every player, stream, theme,
codec, or suspend environment; retain those boundaries when reporting compatibility.
