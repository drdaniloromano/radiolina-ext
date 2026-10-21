# Testing

## Commands

Run from the repository root; use existing tools rather than installing host dependencies.

| Command | Purpose |
| --- | --- |
| `make container-build` | Build the Fedora 43 development image; network access required. |
| `make container-test` | Offline packaging E2E, 13 critical unit cases, 19 service E2E cases, and 7 transport/media validation cases. |
| `make container-package` | Write the runtime ZIP under `build/`. |
| `make test` | Run packaging/unit/service/transport-media checks with already installed host tools. |
| `python3 tests/e2e/package.py` | Packaging check alone; Python standard library only. |
| `make test-shell OOM_SCORE_ADJ=500` | Build and run the real popup/lifecycle/OOM workflow in private headless GNOME 49. |
| `GNOME_RADIO_TEST_SCALE=1.5 GNOME_RADIO_TEST_THEME=light make test-shell` | Repeat at 150% monitor scaling with light/dark checks. |
| `git diff --check` | Check patch whitespace. |

Repeat the three `container-*` commands with `CONTAINER_ENGINE=docker` to verify
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

- Container tests use `--network=none`, explicit read-only source mounts, private XDG paths
  and D-Bus, generated local MP3/ICY/image fixtures, and synchronized silent audio.
  Private workspace/credentials/Git are excluded from the build context and mounts;
  only packaging exposes `build/` writable. Public streams never gate automated checks.
- Shell E2E needs an already installed GNOME 49 Shell/rendering backend. Its private
  D-Bus/XDG/settings/display isolate input, install/update/uninstall, typography,
  and lifecycle from the user's desktop. Host service activation stays disabled.
- The evaluator bootstrap exists only on that disposable Shell; it is never
  packaged. Do not enable remote Eval or unsafe mode in the host Shell.
- Headless Shell is process/settings isolation, not a security sandbox or full VM.
  Its wallpaper is disabled and llvmpipe uses two threads to limit test overhead.
- Use a disposable desktop for real audio, physical media keys, lock, and suspend.
  A verified profile is Fedora 43 Live / GNOME 49.1, 2 vCPUs, 2 GiB guest RAM, KVM,
  accelerated virtio graphics, and 1280×720 display. Verify the signed ISO checksum;
  use read-only ZIP media and user-mode networking, disable host sharing/clipboard
  transfer, set a guest-only password for locking, and stop the VM/viewer afterward.

Logs, screenshots, and measurements go to ignored `workspace/`, including
`shell-e2e.log`, `playback-hover-{light,dark}.png`, `large-text-*.png`, and
`shell-oom-recovery.json`. Keep temporary fixtures and VM assets outside Git.

## Automated coverage

| Area | Required coverage |
| --- | --- |
| Package | Source fidelity, MIT/license inclusion, UUID/version/support/clipboard metadata, private/development exclusions; valid/invalid OOM build settings without source-default changes. |
| Critical unit | URL/config validation, 128-character IDs, unknown-field rejection, exact 1 MiB/overflow bounded reads and closure, invalid UTF-8 preservation, canonical private storage and legacy defaults; metadata, playlist and image bounds. No numerical coverage threshold. |
| Service E2E | Real decoding/MPRIS, CRUD/edit persistence, rejected-file preservation/write blocking/compact error state and playback after manual repair, Recent, favicons/cancellation, HTTP failures/deadlines, stale-load cancellation, idle resources, Shell-owner loss, OOM overrides/inheritance/denial/restart. |
| Transport/media E2E | Actual same-response decoding, misleading extensions/headers, HTML/HLS/video rejection before decoder construction, bounded ID3/ICY/gzip playlists, five-hop redirect boundary, credentials/fragments/schemes, trusted local TLS upgrade/downgrade and playlist-entry policy. |
| Shell E2E | Real ZIP install/replacement/uninstall and legacy-ID migration; saved bytes preserved; native pointer/keyboard controls, shared playback hover/focus, row-action exit, search, 30/70 editor, mutually exclusive views, optional Stop, fixed dimensions/aligned spacing, state icons, silent native media card, service crash/recovery. |
| Theme/lifecycle | Native light/dark changes, 100%/150% display scales, Serif 12 with 125% text scaling, cached-module/CSS updates, delayed startup/cancellation/early exit, rapid Stop/restart, disable/enable, foreign indicator/style ownership, unsupported grouping fallback. |

The service tests execute the packaged-compatible standalone GJS entry. The
transport-stall test disables the HTTP source's timeout in a disposable copy to
exercise the app's own fallback, including Pause cancellation. Shell tests use
real virtual pointer/keyboard events; silent output cannot establish audibility
or physical-key routing. Third-party themes and hardware suspend are not implied.

Validation fixtures generate MP3, FLAC, Vorbis/Opus Ogg, WAV, MP3/Opus MP4,
and video locally. TLS tests trust an ephemeral CA only inside a disposable service
copy, with certificate verification enabled. The default image exercises AAC's
missing-codec error, not positive AAC decoding; that requires a suitable installed
decoder and real AAC fixture. Native parser security is not established by these cases.

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

## Manual acceptance

Run on each advertised GNOME version in a disposable desktop:

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
   history/order, optional favicon fetch/cache/disable, and default-hidden Stop.
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
