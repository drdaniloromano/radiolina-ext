# Changelog

## Unreleased

### Changed

- Bound saved configuration reads to 1 MiB before JSON parsing, limit station IDs
  to 128 characters, and reject unknown configuration/station fields in the shared
  validation layer. Preserve rejected files and require repair/restart before writes;
  retain version-1 defaults and private atomic saves.
- Centralize URL/redirect and bounded media-admission policy in
  `src/core/validation/`; inspect the actual response rather than trusting a
  filename or MIME header, and pass that same buffered response into playback.
- Replace unrestricted playback autoselection with explicit supported audio
  pipelines, preserving ICY/ID3 metadata and M3U/XSPF handling. Reject unsupported
  formats, HTML, video, HLS, oversized audio headers, and non-streamable MP4;
  report missing codecs separately without downloading dependencies.
- Enforce five redirects, credential/fragment restrictions, and HTTPS-to-HTTP
  rejection across playback and playlist sources; retain explicitly entered
  HTTP and local/LAN stations. Abort source I/O before pipeline teardown.
- Clarify desktop runtime versus container/tool dependencies, per-format decoder
  requirements (including AAC), and verified versions versus unestablished minimums.

### Verification

- Cover exact byte/ID limits, overflow read termination/closure, invalid UTF-8,
  unknown fields, unchanged rejected files, blocked mutations, and successful
  playback after manual configuration repair. No memory exhaustion is simulated.
- Add critical validation cases and real-response E2E checks for supported audio,
  deceptive content, single-request handoff, redirect boundaries, and trusted
  local TLS without changing host trust stores. OpenSSL stays in the development
  image; positive AAC decoding remains outside default-image coverage.

## 0.3.0 — 2026-10-20

Finalized locally; GitHub and extensions.gnome.org publication is pending.

### Changed

- Rename the development recipe/ignore file to `Dockerfile` and `.dockerignore`;
  support Podman and Docker with engine-specific user mapping and host-owned
  packages. Restrict build contexts and runtime mounts to exclude private files.

### Verification and limitations

- Podman 5.8.4: image build, packaging E2E, 9 critical cases, and 18 service cases
  passed. Verified restricted build context, read-only source mounts, private-file
  exclusion, package source fidelity, and host UID/GID ownership of generated files.
- Docker CLI selection was checked through this host's Podman compatibility wrapper.
  Rootful/rootless Docker identity branches passed CLI probes; genuine Docker
  runtime build/test/package verification remains untested because it is unavailable.
- Application behavior and the completed GNOME/OOM verification are unchanged;
  the Shell workflow was not rerun for these container-tooling changes.

## 0.2.0 — 2026-10-20

Finalized locally; GitHub and extensions.gnome.org publication is pending.

### Added

- Optional persisted **Show Stop button** setting, off by default, and one native
  Play/Pause button combining the playback circle and station/track information.
- Configurable playback-service OOM preference: default 500, build-time values
  0–1000 or `inherit`, with nonfatal handling of missing/denied kernel controls.
- Isolated GNOME SIGKILL/recovery verification: service score 500 before/after,
  Shell's inherited score unchanged, same indicator and saved data preserved,
  and one Play click restoring playback/metadata without memory exhaustion.
- Larger-font and native light/dark/150% layout checks; actual ZIP installation,
  update, migration, uninstall, process cleanup, and silent media-card coverage.

### Changed

- Follow GNOME's default user-session lifecycle: lock stops playback, unlock
  restores an idle indicator, and Play reconnects without automatic playback.
- Consolidate documentation into a concise README, user/development guides,
  testing instructions, and retained provenance findings.
- Bound private Shell-test rendering to two software threads without wallpaper
  decoding, and require a matching version tag for finalized releases.

### Fixed

- Allow cancellable cold service initialization for up to 120 seconds; report
  early process exit promptly. Bound connection/rebuffering stalls to 30 seconds
  with cleared metadata, readable persistent errors, and explicit retry.
- Preserve native hover/focus through playback commands; hide stale station-row
  actions on pointer exit and keep keyboard navigation available.
- Align compact playback/section/row spacing, preserve fixed popup geometry, and
  keep search/editor fields contained across native fonts and text scales.
- Complete the former development identity's shutdown before live activation,
  preserving station data and handling service-object disappearance during teardown.

### Verification and limitations

- Packaging, 9 critical unit cases, 18 service E2E cases, and the GNOME 49 Shell
  workflow pass. The OOM/crash check passed on GNOME 49.7; see [testing](docs/TESTING.md).
- Maintainer-confirmed GNOME 49.1 VM checks cover audible Nightride playback,
  basic physical Play/Pause, lock/unlock, and native light/dark/high contrast.
- Suspend/resume remains unverified after the test VM failed to wake; no applet
  cause is established. Multiple-player media-key routing, other codecs, and
  third-party themes require their own checks. OOM tests simulate process death,
  not actual memory pressure, kernel victim selection, or systemd-oomd behavior.
- Song information depends on stream metadata; Pause can lag the live edge.
  No online station discovery, podcasts, accounts, or recording are provided.

## 0.1.0 baseline — 2026-10-20

Earlier local development tag; no public release was recorded.

### Added

- MIT license for original project files, source/artwork/tooling identifiers, and
  the full license/copyright notice in the extension ZIP.
- E2E packaging check for license inclusion, source fidelity, and exclusion of
  machine-local and development files; included in `make test` / `make container-test`.
- Fixed infobox order **Play/Pause | Stop | station/track info | Quit** using native
  symbolic icon buttons; removed the bottom textual Quit action and placement switch.
- Infobox Stop exits the playback service and clears track metadata while retaining
  the indicator and saved state. Play and station/settings actions restart it on
  demand; pending restarts are cancellable. Quit disables radiolina and stops its service.
- Persisted **Group with other app indicators** preference, off by default, with
  the compatibility warning beside it. No cooperative host is currently supported;
  enabling it explicitly reports the standalone fallback and never moves other apps.
- Persistent Recent section with a configurable **1–10** visible entries (default **3**),
  newest first. Ten unique successfully played stations are retained; reducing the
  visible count preserves history. Deleted stations are removed from history.
- Remove actions in saved/Recent rows, shown on hover or keyboard focus.
- Copy URL icon inside the editor, beside the URL field, without saving or changing playback.
- Legacy playback-position preferences remain readable for configuration compatibility;
  the UI now always uses the fixed transport order.
- Collapsed-by-default saved list with an expand button; Search expands it, and
  closing the popup collapses it again.
- Settings gear with opt-in station favicons, asynchronous bounded PNG/ICO loading,
  host deduplication, private disk cache, and cancellation when disabled.
- Artist metadata in the infobox and MPRIS, from explicit artist tags or combined
  `Artist - Title` stream fields. Missing/stale artists are hidden and cleared.
- Distinct panel symbols for active playback (radio with signal marks) and
  paused/inactive playback (plain radio). Both symbols are static; connecting or
  failed playback never shows the playing symbol.
- Bundled theme-colored symbolic radio icons for the panel.
- Station editing with prefilled name/source fields, Save/Cancel/Delete, atomic
  persistence, uninterrupted renaming, and source reconnection while playing.
- Ordinary M3U/M3U8 and XSPF sources with bounded asynchronous resolution, relative
  links, redirects, content-type detection, and cancellation of stale loads.
- Per-station pencil actions, an inline editor, and a scrollable station list.
- A Search button revealing a local saved-station filter, with an adjacent **+**
  button for adding streams. Filtering matches station names and source URLs.
- No-logout updates using content-addressed UI modules and unique GObject type
  names, preserving stations while replacing previously cached UI code.

- GNOME 49 native indicator popup with saved custom streams, playback controls,
  station details, song metadata, and a station add/remove workflow.
- Separate lightweight GJS/GStreamer service with private atomic configuration,
  URL validation, stream error handling, and clean shutdown on disable or Shell loss.
- MPRIS play/pause/stop controls and metadata for desktop media integration.
- Container build/package/test commands, deterministic service E2E tests, critical
  unit tests, and disposable headless Shell E2E tooling.
- Contributor guide and implementation plan.
- Documented and tested GNOME 49 first-install loading through Looking Glass
  without logging out or restarting the current Shell session.

### Current limitations

- GNOME 49 is the initial supported target; no other desktop adapter is shipped.
- Song information depends on stream metadata; pause can lag the live edge.
- Full physical media-key routing and audible playback need desktop/VM checks.
- No online station discovery, podcasts, accounts, or recording.

### Changed

- Set the permanent extension ID to `radiolina@drdaniloromano.github.io`, link the
  source/support repository, and disclose the editor's clipboard write in metadata.
  Package names follow the metadata ID; installation/update helpers and docs use it.
  Remove the manually assigned submission counter, which extensions.gnome.org manages.
- Preserve station storage and service identifiers across the ID transition.
  Scope indicator GType names to the full module URI, allowing the old and new
  installation paths to load sequentially in one Shell session. Cover the transition,
  saved selection/history/preferences, and old-backend shutdown in the Shell E2E test.
- Name the app **radiolina** in Extensions, panel accessibility labels, MPRIS,
  network user-agent strings, update helpers, and documentation. Retain existing
  service identifiers and storage paths for compatibility.
- Remove the GNOME prefix from the app name; propose `radiolina-ext` for the
  repository. Record the existing broadcaster's use of radiolina for naming review.
- Describe popup, inline actions, and panel spacing through native GNOME behavior;
  remove incidental references to an example extension from docs and test comments.
- Record the source/artwork provenance review and its limits; original project
  files use MIT without changing external components' licensing.
- Keep radiolina's panel button independent; grouping requires an explicitly supported
  cooperative host. Add regression checks preserving other indicators' ownership
  and independent input handling through visibility changes and extension reloads.
- Use compact icon-only indicator spacing: clear icon padding and margins,
  retaining native button padding, icon size, height, and theme interaction states.
- Bold the infobox station name and show track information in smaller, subdued
  text that follows the active theme in light and dark mode.
- Split Add/Edit input width 30% for the station name and 70% for its URL,
  reserving spacing and the editor's Copy button inside the fixed popup.
- Show only one Stations-area view at a time: saved list/search, Add/Edit, or Settings.
- Size the fixed infobox from the native font and let its text column shrink to the
  available width, keeping track text above the separator and playback inside the popup.
  Widgets retain native light/dark colors, borders, and focus states.
- Fixed popup width across every view, with a narrower station-name input and
  compact Name/URL and Save/Cancel/Delete rows. Copy URL moved from lists into the editor.
- Fixed infobox height, centering the station name alone and lifting it when track
  information appears. Errors remain readable in a separate row below the infobox.
- Remove the source URL from the main infobox; it shows station name and available
  artist/title. URLs remain available through Copy, editing, and filtering.
- Show station Play/Edit/Remove actions on hover or keyboard focus, without shifting names.
  Play starts/resumes a station without pausing one already playing.
- Move the expand arrow directly beside Stations. Typing in the popup or Ctrl+F
  opens the saved-station filter with native search/clear icons.
  Station-editor text input remains independent.
- Balance the Stations separator against the action icons on either side, restoring
  clearance above the toolbar. Search keeps the same toolbar height/padding and matches
  the action-button height, and shares the compact native styling of Name/URL inputs.
  Showing it adds no margin and keeps it vertically centered with the icons.
- Balanced text spacing around the infobox separator, including when song
  metadata is absent.
- Bold section headings and a separator above Stations. Selected station names use
  regular weight with a small status icon and a **(playing)** suffix during playback.
- Reduced the infobox's bottom padding further.
- Reduced edit/search/add button padding, station-row height, and infobox padding.
  Native theme colors, shapes, and interaction states remain in use.
- Combined artist and song title into a single ellipsized infobox row. Saved-station
  rows show names only; source URLs remain available through Copy, editing, and search.
- Retained GNOME's persistent native MPRIS media card in the notification center;
  track changes update it in place without popup banners or duplicate notifications.
- Restored native station menu rows, removing filled station
  buttons. Indicator and popup controls use standard Shell styles; colors, borders,
  icon sizes, and states come from the theme, with compact layout padding.
- Removed Foliate-inspired flat button styles, restoring
  default native icon controls while retaining the radio glyph.
- Removed playback icon animation; status is conveyed solely by static symbols.
- Hide the song line when metadata is unavailable, without placeholder text.
- Placed the revealed search field inline with the Stations heading and Search/**+**
  controls. Reduced the playback
  information box's vertical padding and text spacing.
- Restored default GNOME typography, colors, and button states for readable text.
  Kept the station-name/source/song information box with play/pause above
  the divider and station controls below it.
- Removed song-change desktop notifications entirely, including for existing enabled
  preferences. The legacy service API/configuration remains compatible.

### Fixed

- Remove stale applet styles during same-session updates and load versioned CSS.
  Isolated checks reproduce the old oversized Name field, verify URL containment
  and track/divider clearance, and retain native light/dark styling after updates.
- Remove shared `St.Theme` replacement from stylesheet recovery. Unload distinct
  identifiable styles only from the applet's own directory; leave foreign and
  unidentifiable registrations intact. Already unaddressable stale CSS may need
  a fresh Shell session.
- Add isolated Shell regressions for theme object identity, use through cached
  references, foreign stylesheet order/effect, and unidentified entries across
  updates, rapid toggles, failed enable/recovery, and disable.
- Clear native active-row state before replacing station actors and restore keyboard
  focus safely, preventing disposed-actor errors while the popup remains open.
- Keep the popup open after activating saved/Recent stations or any inline control,
  including settings switches. Escape, outside clicks, and indicator toggling still close it.
- Replaced the unavailable `audio-radio-symbolic` icon with Adwaita's standard
  headphones symbol for the panel and notifications.
- Made repeated first-install instructions safe and cleaned up failed indicator
  registration. Added a tested no-logout recovery helper for duplicate actors and
  already cached extension modules.
