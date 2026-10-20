# Implementation plan

## Objective and constraints

Deliver radiolina, a lightweight GNOME 49 top-bar radio applet: saved custom streams,
play/pause and media keys, a compact native popup, and stream title/artist metadata
without song-change notifications. Online station discovery,
accounts, podcasts, and recording are deferred; saved stations can be filtered locally.
Keep playback independent of Shell so future desktop adapters can reuse it.

## Decisions

- License original project files under MIT and include the full license/copyright
  notice in the release ZIP. Preserve upstream licensing for external components.
- Use GJS and GStreamer already provided by the GNOME platform. No web runtime,
  JavaScript package manager, Python runtime dependency, or application window.
- Run playback in a separate on-demand session D-Bus service. This keeps decoding
  and network work out of Shell. Export MPRIS for media keys.
- Pause uses GStreamer's PAUSED state and resumes the same pipeline, satisfying
  MPRIS PlayPause semantics. There is no disk recording or dedicated time-shift
  buffer; resuming can briefly lag the live edge. Stop releases the connection.
- Store stations atomically in XDG configuration; preserve legacy config compatibility.
- Persist the ten most recently played unique stations, a visible Recent limit
  (1–10, default 3), and an opt-in favicon preference. Expand saved stations on
  demand; keep Recent visible by default. Lowering the limit preserves history.
- Use fixed Play/Pause, Stop, text info, Quit controls in the infobox. Stop exits
  the backend; Play and station/settings operations restart it on demand. Retain
  cached station state in Shell and cancel stale startup/call completions.
- Fetch bounded PNG/ICO favicons asynchronously in the service only when enabled,
  cache by stream origin, and cancel stale work without affecting playback.
- Use native Shell popup widgets; title/artist metadata is event-driven.
- Show distinct static active/inactive symbolic icons: signal
  marks only while Playing, plain radio for paused, stopped, connecting, or failed
  playback. Inherit the system indicator's theme color and sizing.
- Inherit the active Shell theme's fonts, colors, borders, and states. Keep CSS
  limited to layout and compact sizing; use native station menu rows and standard
  Shell controls, retaining theme colors, shapes, and interaction states. Search,
  Name, and URL share compact native entry styling; Search matches action-button height.
- Persist optional grouping intent, off by default, with the compatibility warning.
  No host is currently supported: keep standalone placement and report that fallback.
  Future integrations require explicit cooperative support and lifecycle validation.
- Target the locally available GNOME 49 first; do not claim untested versions.

## Delivery phases

1. Implement critical station validation, persistence, and metadata deduplication.
2. Implement the GStreamer service and D-Bus/MPRIS contract, including failure and
   cleanup handling. Verify it against deterministic local audio/ICY fixtures.
3. Implement the native indicator popup, station form, playback state, metadata,
   saved-station filter, and clean enable/disable lifecycle.
4. Add container builds/tests, an isolated desktop launcher, and reproducible
   package output. Never install development dependencies on the host.
5. Run critical unit tests, real service E2E tests, and isolated Shell E2E checks
   where supported. Measure idle resources, document validation limits, and update
   README, contributor guide, and changelog.

## Acceptance checks

- Station/list actions and all inline buttons keep the popup open; Escape, outside
  clicks, and indicator toggling retain normal dismissal behavior. The infobox's Quit
  action disables radiolina, stops its service, and preserves saved stations/preferences.
- Station Play/Edit/Remove controls appear on hover or keyboard focus without layout shifts.
- Recent defaults to three visible entries; Settings changes persist without
  interrupting playback or erasing history. Inputs and form actions use two compact rows.
- The infobox hides URLs; Copy beside the editor URL writes its current contents
  without saving, selecting a station, or affecting playback.
- Popup width remains fixed across all views. Infobox height stays fixed, centering
  the name alone and fitting name/track rows when present. Errors use a separate row.
- Infobox height follows native font metrics; text fits the available width without
  covering separators or displacing playback. Native light/dark changes update widgets.
- Saved list/search, Add/Edit, and Settings replace one another; only one is visible.
- Controls retain their fixed order and box dimensions with or without metadata.
  Stop must release the backend while keeping the popup usable; subsequent Play,
  editing, and rapid Stop/restart cycles must recover without orphan processes.
- Typing in the popup or Ctrl+F opens the saved-station filter without dropping the
  first character; editor inputs remain unaffected. Expansion sits beside Stations.
- The Stations separator has equal clearance from Recent action icons above and
  toolbar action icons below. Opening search preserves toolbar geometry; entry
  compact native input styling and padding remain stable on focus/hover. Search
  stays vertically centered with the icons and adds no margin when shown.
- Adding/selecting stations persists across service restart; invalid URLs fail.
- Play/control over both app D-Bus and MPRIS reaches the same pipeline and state.
- Stream metadata updates the popup and MPRIS; missing titles do not remain stale.
- Song changes update the infobox and GNOME's native persistent media card silently,
  even with a legacy enabled preference; no popup banners or duplicate notifications.
- Network failures show a useful error without blocking the popup.
- Disabling the extension releases UI, signals, bus objects, and playback process.
- Offline tests use project-local configuration and a private bus, no public radio.
- Idle playback service has no recurring timers; resource measurements are recorded.

## Progress

- All five delivery phases completed for the initial GNOME 49 implementation.
- Nine critical unit tests and fifteen service E2E tests pass inside the offline
  development container, including unexpected Shell-disconnect cleanup.
- The real headless Shell E2E workflow passes: popup form, title/artist metadata,
  no desktop notifications, persistence, disable/re-enable, and rapid toggles.
- Idle service sample: about 37 MiB RSS and 0.000s CPU over one second in the
  container. This is a short service-only sample, not a full-desktop benchmark.
- Audible Nightride FM playback was confirmed by the maintainer in the disposable
  Fedora 43/GNOME 49.1 VM through SPICE on 2026-10-20.
- Physical Play/Pause pause/resume was also confirmed with the VM focused.
- Guest lock/unlock was confirmed: audio stops on lock, unlock returns the idle
  indicator without autoplay, and Play resumes audio.
- Native light/dark readability and layout were confirmed by the maintainer for
  the popup, expanded Stations, and Add/Edit form in the GNOME 49.1 VM.
- Native high contrast with the dark preference was also confirmed, including
  readable text/icons, visible keyboard focus and contained controls. Restore
  guest theme preferences after the checks.
- Guest suspend verification remains open after the live VM became unresponsive
  and required restarting. Establish a working environment sleep/wake cycle
  before attributing the failure or repeating the applet check.
- Multiple-player media-key routing, suspend, and custom-theme/font checks remain manual
  verification tasks. Automated tests do not install into the host session.
- Native light/dark switching and the screenshot regression at 150% monitor scaling
  are covered by the real Shell workflow, with bounded metadata/control geometry.

## Subsequent completed work

- Diagnose first-activation failure as premature teardown during cold GStreamer
  registry discovery (69.6 seconds cold versus 1.1 seconds cached in the guest).
  Extend the cancellable readiness deadline to 120 seconds and fail promptly on
  child exit. Cover delayed initialization, cancellation, early exit, and recovery
  in the isolated Shell workflow; remove the local VM launcher's re-enable workaround.
- Prepare a contained Fedora 43/GNOME 49.1 live desktop with 2 vCPUs and 2 GiB
  guest RAM, hardware acceleration, and no installed guest system disk. Verify
  applet/service startup without autoplay; document the profile and keep local VM
  assets excluded. Audible playback, physical keys, and lock/suspend checks remain
  manual acceptance work.
- Confirm default GNOME user-session behavior: lock stops playback; unlock restores
  an idle applet. Keep this lifecycle and document manual lock/suspend checks.
- Audit runtime/package structure against EGO review guidance. Add the standalone
  GJS service marker, keep Shell enable/disable adjacent, and reconcile contributor
  instructions with implemented behavior. Verify cleanup and package exclusions;
  cover real ZIP installation/replacement and uninstall preserving saved data in
  isolated Shell. Desktop audio/media-key and suspend/lock/resume checks remain separate.
- Document the Shell/service process boundary and playback/storage ownership in a
  README Mermaid diagram, including D-Bus state updates and MPRIS media controls.
- Choose `0.1.0` for the first release and set `version-name` in metadata. Document
  version increments and `v<version>` tags; keep the changelog unreleased until
  final checks pass. Leave numeric submission versions to extensions.gnome.org.
- Set the permanent extension ID to `radiolina@drdaniloromano.github.io`, add
  repository/support links in metadata/docs, and declare the Copy URL clipboard
  write. Build package paths from metadata; use the same ID in update helpers.
  Keep existing storage/service identifiers. Verify saved data and old-service
  shutdown through a same-session development-ID transition in isolated Shell.
  Include the full module URI in GType identity to distinguish installation paths.
- Set the public-facing name to **radiolina**, including panel accessibility,
  media identity, user-agent strings, update helpers, and docs. Preserve existing
  service identifiers and storage paths across the rename.
  Use `radiolina-ext` as the repository name and review name availability
  separately before publication.
- Review source/artwork provenance and describe UI behavior through native GNOME
  conventions. Record findings and unresolved origins in `docs/PROVENANCE.md`;
  apply MIT to original files and ship `LICENSE` with an E2E packaging check.
- Add native Play/Pause, Stop, and Quit icons around the infobox text. Quit uses
  normal extension teardown after its input event; Stop ends only the backend.
  Replace the bottom Quit row and old left/right placement option.
- Add the persisted, default-off grouping preference and its compatibility warning.
  Report the standalone fallback until a cooperative host is explicitly supported.
- Keep panel ownership independent. Shared grouping is deferred until a documented,
  explicitly compatible cooperative host is available and lifecycle-tested.
- Use compact icon-only panel spacing with zero icon padding/margins and native
  button padding, icon size, height, and theme states.
- Bold infobox station name with smaller, subdued track text using the theme's
  foreground color; list station names retain their regular weight.
- Shared Add/Edit inputs divide their available width 30/70 for Name/URL,
  reserving the gap and optional Copy control without widening the popup.
- Versioned layout styles and UI module identities that change for CSS-only edits.
  Startup unloads distinct identifiable applet styles without replacing the shared
  Shell theme. Foreign and unidentifiable entries remain untouched. Upgrade checks
  cover compact fields, cached theme references, foreign style order, and lifecycle;
  unaddressable stale CSS may require a fresh Shell session.
- Font-relative infobox sizing and flexible text width, with regression coverage for
  the supplied Nightride/Mascarpone screenshot at 150% monitor scaling.
- Mutually exclusive Stations-area views, native light/dark styling, and safe active-row
  deactivation/focus restoration when list contents are refreshed.
- Suppressed automatic menu-item dismissal throughout the applet's own menu/sections,
  retaining standard pointer/keyboard input and explicit popup dismissal.
- Fixed popup width, narrower name fields, shared compact native entry styling,
  hover/focus Remove actions in both lists, and Copy URL moved into the editor.
- Fixed-height infobox with centered single/two-line metadata, separate readable
  errors, and a fixed transport layout with backend-unloading Stop.
- Persisted Recent count in Settings (1–10, default 3) with ten-entry retained history.
  Compact horizontal name/URL fields and a shared Save/Cancel/Delete row. Removed
  the infobox source line and added native clipboard access (now in the editor).
- Hover/focus station actions, explicit row Play, and type-to-search
  with native search/clear icons. Isolated virtual keyboard/pointer checks cover
  activation, first-character preservation, clearing, Ctrl+F, and editor isolation.
- Balanced the Stations separator using native row/toolbar action icons as the
  reference, removing text-based allocation corrections. The native search field
  matches action-button height without changing toolbar padding/height.
- Editable station names/source URLs with atomic validation and persistence.
- Bounded asynchronous M3U/XSPF resolution and stale-load cancellation.
- Per-station pencil actions and a native inline editor.
- Restored default GNOME text and button styling, retained the station
  information/playback box, and placed Search/**+** controls above the saved list
  below the divider. Search reveals a local name/source filter; the song-notifications
  toggle was removed. The revised workflow passes the real Shell E2E test.
- Made the search field inline with Stations and native circular Search/**+**
  buttons, and reduced vertical padding/spacing in the information box. Real
  Shell checks cover alignment, compact height, filtering, and same-session updates.
- Replaced station cards with native menu rows/selection markers and hid unavailable
  song titles. Restored standard indicator/popup control styles and removed the
  Foliate-inspired flat buttons. No additional GTK/libadwaita runtime dependency.
- Bundled theme-colored radio SVGs without icon animation or recurring callbacks.
- Added persistent active/inactive panel symbols with E2E checks for play/pause,
  MPRIS Stop, restart, and static full-opacity icons during playback.
- Added explicit/combined stream artist metadata to the infobox and MPRIS, clearing
  missing/stale artists. Removed Shell song-change notifications while preserving
  the legacy service contract and existing station files.
- Combined artist/title into one compact infobox line and reduced saved-station
  rows to names only. URLs remain available through Copy, editing, and search.
- Verified the native notification-center media card persists and updates in place
  without song-change banners, including pause/resume through its own controls.
- Reduced station-row height, edit/search/add button padding, and infobox spacing,
  keeping the native theme and standard play/pause control size.
- Added persistent Recent history, a collapsed saved list, Settings
  with optional cached favicons, and selected names with a playing-only suffix.
  Unit/service/Shell checks cover migration defaults, history ordering, bounded
  images, cache/cancellation, expansion, and native settings interaction.
- Added a separator before Stations and bold section headings, replacing bold
  current-station names with small status icons and reducing infobox bottom padding.
- Balanced infobox separator spacing against text and Stations separator spacing
  against icons, verified with rendered actor positions with/without song metadata.
- Same-session updates through fresh content-addressed modules, verified in the
  Shell E2E workflow. Activation of installed UI code uses Looking Glass without
  logging out. Build/test commands do not install into the user's session.
