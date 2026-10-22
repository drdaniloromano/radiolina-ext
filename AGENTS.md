# Repository Guidelines

## Purpose & First-Release Scope

Build radiolina, a minimal, lightweight GNOME top-bar radio applet. Avoid web runtimes, polling, unnecessary dependencies, and background work. Measure idle CPU/memory when changing architecture.

First-release features:

- Play/pause, resource-releasing Stop, and Quit through panel controls; play/pause
  through keyboard media keys while the service runs.
- Adding and editing stations from direct stream, M3U, or XSPF URLs.
- Persistent saved stations, local filtering, selection, and configurable Recent entries.
- Stream-provided title/artist metadata and silent native MPRIS media integration.

Defer online station discovery. Keep podcasts, accounts, and recording outside the first release until explicitly requested.

## User Experience

Clicking the indicator opens a compact native popup with fixed-width controls and station management. Show the station name in bold and available artist/title together in smaller, subdued text. Keep URLs in the editor; clear stale metadata on stream changes.

Follow native GNOME popup and indicator conventions, with a clear selected state and inline actions. Keep editing inside the popup and preserve station identity and playback when renaming.

Update GNOME's native media card silently; do not create song-change popup notifications. Legacy notification fields remain for storage/API compatibility.

Keep the indicator standalone unless an explicitly supported cooperative grouping host exists. Never reparent arbitrary third-party indicators. Follow system theme styles and use static playback-state icons.

Keep controls responsive and keyboard-accessible, with clear state, accessible labels, and concise errors.
Do not fetch station favicons. Legacy saved flags remain accepted but inactive.

## Architecture & Portability

Use GJS/GStreamer; separate playback, persistence, validation, and metadata from desktop adapters. Core functionality must not depend on Shell widgets.

Keep source admission policy in `src/core/validation/`. Enforce URL/redirect rules
on actual requests and inspect a bounded byte prefix before selecting an explicit
audio pipeline. Preserve the same response through playback; do not restore URI
reopening, unrestricted decoder autoselection, or streaming-thread JS callbacks.
Keep configuration schema/defaults in the same validation layer. Bound file reads
before parsing, reject unknown fields, and preserve invalid files for repair;
never silently reset or truncate saved stations.
Do not expose transport URLs in MPRIS or final redirect URLs in app state.
Only code-authored, bounded `UserError` messages may cross error boundaries;
never embed input, URLs or native diagnostics in them. Preserve full saved URLs
for station editing and explicit Copy, and document same-user privacy limits.

Respect GNOME's default `user` session lifecycle: screen lock stops playback;
unlock restores the idle indicator without automatic playback. Keep lock-screen
operation disabled.

`src/core/` holds critical logic; `src/service/` owns playback, D-Bus/MPRIS, and storage; `extension/` owns the panel/popup and desktop integration. `tests/` contains unit/E2E tests. GNOME 49 and 50 are current targets; additional desktop adapters are future work.

See [architecture and build configuration](docs/DEVELOPMENT.md) for lasting design
decisions and [testing](docs/TESTING.md) for coverage and isolation requirements.

## Contained Development & Commands

Keep dependencies/artifacts contained; do not install development packages globally.
Use versioned Shell containers for automated UI/lifecycle checks. Use an isolated
full desktop for physical audio/media-key, lock, and suspend acceptance.

- `make container-build`: build the development image.
- `make container-refresh`: pull/rebuild without cache and upgrade image packages
  before release/security verification; keep host packages unchanged.
- `make container-test`: offline service E2E and critical unit tests.
- `make container-resources`: opt-in ten-minute Linux resource probe with local
  fixtures and no forced garbage collection; keep it outside the normal suite.
- `make container-package`: create the extension ZIP in `build/`.
- `make security-check` / `make container-security-check`: opt-in dependency
  advisory queries with temporary caches. Follow [security review](docs/SECURITY.md);
  incomplete data must not pass and exit zero alone never approves a release.
  For each finding, follow [advisory triage](docs/SECURITY.md#repeatable-advisory-triage):
  verify primary notices and actual reachability, retain raw reports and dated
  per-advisory Markdown reports in ignored `workspace/` using the documented
  sortable UTC filenames, and leave uncertain findings open. Reassess
  after source/environment changes; never silently update packages or suppress CVEs.
- Add `CONTAINER_ENGINE=docker` to container commands to select Docker instead of
  the default Podman. Keep private files out of build contexts and runtime mounts;
  preserve the invoking user's ownership of generated files.
- `make test-shell`: actual popup/lifecycle checks in disposable headless GNOME.
- `make container-shell-build` / `make container-shell-test`: build and test a
  private headless Shell images; the default `SHELL_VERSIONS="49 50"` tests both
  supported targets. Set one version for focused development checks.
  Version lists run sequentially, with private buses/settings and bounded resources.
  Never mount host desktop/system buses, home, display/audio sockets or workspace.
  Evidence goes to a fresh ignored `build/shell-tests/` directory. Additional
  profiles do not establish compatibility until the declared-version suite passes.
- `make build` / `make test`: use already installed tools without dependency installation.
- `make ci-start`, `make ci-image` / `make ci-test CI_PROFILE=49` (then `50`, `aac`),
  `make ci-package`, `make ci-evidence`: local Actions orchestration; see
  [CI maintenance and artifacts](docs/DEVELOPMENT.md#github-actions-test-and-build).
  Keep cache refresh distinct from security approval, verify artifact/source/runtime
  identity, and upload only staged allowlisted evidence. Genuine Docker and remote
  runs require observed verification; Podman wrappers do not establish Docker support.

The dedicated release workflow builds a fresh installer from the exact version
tag after its main push CI succeeds; never promote PR artifacts. Use reviewed
main tooling, inspect tagged source without running its tooling, and keep
source/tag/version/payload/checksum checks. Produce deterministic assets for
retries and separate read-only building from write-capable attachment. Preserve
identical existing assets and reject conflicts without overwriting. Standalone
tags must not create releases. See
[release attachments](docs/DEVELOPMENT.md#automated-release-attachments).

## Coding Style & Naming Conventions

Use four-space indentation in JavaScript/Python, ES modules, descriptive names, and focused modules. Run `git diff --check`; no formatter/linter is configured.

## Testing Guidelines

Write necessary E2E tests for user workflows and integration. Add unit tests only for critical validation, storage, and state/metadata logic. Use Python unittest for E2E and the GJS critical-test harness. No numerical coverage threshold applies.

Use deterministic local fixtures; public streams must not gate automated tests. Use [Nightride FM](https://nightride.fm/) for manual checks. Verify media keys, accessibility, notifications, and lifecycle on documented GNOME versions.

Cover edit persistence, invalid/duplicate URLs, playlist parsing/bounds, and cancellation of stale source loads. Test same-session updates against already imported UI modules.

## Documentation, Commits & Pull Requests

Keep the [README](README.md), [user guide](docs/USER_GUIDE.md),
[development guide](docs/DEVELOPMENT.md), [testing guide](docs/TESTING.md), and
[changelog](CHANGELOG.md) current with behavior/tooling changes. Use focused
imperative commits, e.g. `Add station menu`. PRs describe purpose, verification,
limitations, linked issues, and UI screenshots.

Every finalized release must have a matching Git tag `v{release}`, for example
`v0.1.0`, pointing to its reviewed release commit. Create the tag when finalizing
the release; an Unreleased entry or planned version alone does not create a release.
