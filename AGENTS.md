# Repository Guidelines

## Purpose & First-Release Scope

Build a minimal, lightweight GNOME top-bar radio applet. Avoid web runtimes, polling, unnecessary dependencies, and background work. Measure idle CPU/memory when changing architecture.

First-release features:

- Play/pause through panel controls and keyboard media keys.
- Adding and editing stations from direct stream, M3U, or XSPF URLs.
- A persistent saved-station list and station selection.
- Stream-provided song metadata and optional song-change notifications.

Defer station search. Keep podcasts, accounts, and recording outside the first release until explicitly requested.

## User Experience

Clicking the indicator opens a compact native popup with controls and station management. Show station name, source URL in smaller text, and available song title. Clear stale metadata on stream changes.

Take visual inspiration from Copyous: rounded cards, a clear selected state, and inline actions. Keep editing inside the popup and preserve station identity and playback when renaming.

Notifications default off. Notify on distinct stream-reported track changes; suppress initial, duplicate, and empty metadata.

Keep controls responsive and keyboard-accessible, with clear state, accessible labels, and concise errors.

## Architecture & Portability

Use GJS/GStreamer; separate playback, persistence, validation, and metadata from desktop adapters. Core functionality must not depend on Shell widgets.

`src/core/` holds critical logic; `src/service/` owns playback, D-Bus/MPRIS, and storage; `extension/` owns popup/notifications. `tests/` contains unit/E2E tests. GNOME 49 is the current target; additional desktop adapters are future work.

## Contained Development & Commands

Keep dependencies/artifacts contained; do not install development packages globally. Prefer an isolated GNOME VM for visual/audio checks.

- `make container-build`: build the development image.
- `make container-test`: offline service E2E and critical unit tests.
- `make container-package`: create the extension ZIP in `build/`.
- `make test-shell`: actual popup/lifecycle checks in disposable headless GNOME.
- `make build` / `make test`: use already installed tools without dependency installation.

## Coding Style & Naming Conventions

Use four-space indentation in JavaScript/Python, ES modules, descriptive names, and focused modules. Run `git diff --check`; no formatter/linter is configured.

## Testing Guidelines

Write necessary E2E tests for user workflows and integration. Add unit tests only for critical validation, storage, and state/metadata logic. Use Python unittest for E2E and the GJS critical-test harness. No numerical coverage threshold applies.

Use deterministic local fixtures; public streams must not gate automated tests. Use [Nightride FM](https://nightride.fm/) for manual checks. Verify media keys, accessibility, notifications, and lifecycle on documented GNOME versions.

Cover edit persistence, invalid/duplicate URLs, playlist parsing/bounds, and cancellation of stale source loads. Test same-session updates against already imported UI modules.

## Documentation, Commits & Pull Requests

Keep `README.md`, `CHANGELOG.md`, and plan current with behavior/tooling changes. Use focused imperative commits, e.g. `Add station menu`. PRs describe purpose, verification, limitations, linked issues, and UI screenshots.
