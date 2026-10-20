# Changelog

## Unreleased

Planned first release: **0.1.0**. Final verification and publication are pending.

### Added

- Record maintainer-confirmed audible Nightride FM playback and physical
  Play/Pause pause/resume in the disposable GNOME 49.1 desktop; remaining manual
  acceptance checks stay open.
- Document a small disposable GNOME 49 live-VM profile for manual desktop checks,
  with contained assets, KVM/graphics acceleration, and explicit verification limits.
- Isolated Shell E2E coverage for installation of the real ZIP, forced replacement
  of existing runtime files, and uninstall preserving saved stations/settings.
- README architecture diagram showing process boundaries, D-Bus/MPRIS communication,
  playback, and station storage.
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

- Require a matching `v{release}` Git tag for each finalized release; planned
  versions remain Unreleased until final checks and release completion.
- Confirm GNOME's default user-session lifecycle as the intended policy: lock
  stops playback, and unlock restores the idle applet without automatic resume.
- Mark the standalone service entry point with the recommended GJS module header,
  place Shell enable/disable methods together for lifecycle review, and align the
  contributor guide with current controls, metadata, silent media integration,
  local filtering, and cooperative-only grouping.
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

- Allow up to two minutes for playback-service readiness instead of killing a
  healthy first activation after ten seconds during cold GStreamer discovery.
  Keep startup cancellable and report an exited backend promptly. Add isolated
  Shell regressions for delayed readiness, cancellation, early exit, and retry.
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
