# Verification

## Automated checks

Run `make container-build && make container-test` for offline tests with local
MP3/ICY fixtures. This executes the production GJS service and GStreamer pipeline
on a private bus, using a synchronized silent audio sink. The image contains all
test dependencies; the host source mount is read-only.

The packaging E2E check builds the real ZIP in a temporary checkout, verifies that
`LICENSE` and the packaged runtime match source, checks MIT identifiers on generated
wrappers, verifies the permanent UUID, support URL, clipboard disclosure, and
source metadata (including `version-name`) in the archive, and rejects unexpected
development/private files.
It needs only Python's standard library; run it alone with `python3 tests/e2e/package.py`.

The standalone service starts with the `#!@GJS@ -m` review marker and is launched
explicitly through `gjs -m`. Service and Shell E2E runs execute that same entry
point, covering startup and teardown after packaging/review changes.

At the end of the isolated Shell workflow, `gnome-extensions uninstall` must remove
extension files, preserve saved station/settings bytes, and leave no indicator or
playback service. All installer/uninstaller commands inherit the disposable XDG
directories and private bus; they do not target the user's desktop installation.
The test starts GNOME's extension-management helper explicitly on its private
Wayland display/bus for uninstall, then terminates it. Host service activation
remains disabled.

Name checks require **radiolina** in package metadata, the real service's MPRIS
identity, and the panel's accessible name and Quit label. The Shell workflow first
loads a development-ID fixture, saves/plays a local station, changes a preference,
and disables it. It waits for the old backend to exit, then loads
`radiolina@drdaniloromano.github.io` in the same session. Saved station identity,
selection, recent history, and preferences must survive without rewriting the
configuration. Only the new indicator is present; the old ID remains disabled.
This also exercises separate GType identities for cached modules at different
installation paths. Service identifiers and storage paths remain compatible.
The workflow additionally unloads the new ID, re-enables the development ID,
then runs the live updater through Looking Glass. The updater must disable the
old ID and service, activate the previously unregistered new ID, load the packaged
runtime, and preserve saved-file bytes. A ZIP installed on disk is not evidence
that its runtime is active in the current desktop session.

Nine critical unit cases cover URL validation, bounded metadata sanitization,
deduplication, saved-state validation, and private persistence/corruption safety.
Sixteen service E2E cases cover real decoding and MPRIS controls, ICY title changes
and legacy track-change signals, station CRUD/restart, HTTP failure/recovery, corrupt
configuration preservation, idle resource sampling, and Shell-owner loss.
The stalled-transport case disables the HTTP source's own timeout in a disposable
runtime copy, holds a real stream open without data, pauses beyond 30 seconds,
then verifies the resumed buffering deadline, cleared metadata, persistent error,
and successful retry. This exercises the fallback when GStreamer supplies no error.

Additional cases cover validated/persistent edits, renaming while playing, URL
changes while paused/playing, M3U/XSPF/redirect/content-type sources, malformed,
oversized and circular playlists, and cancellation of slow loads on edit/pause.
Critical parser tests cover relative links, namespaces/xml:base, CDATA, entities,
size bounds, and rejection of unsupported HLS and XML declarations.
Artist tests cover real ID3 artist tags, combined ICY artist/title fields, MPRIS
artist export, partial tag updates, sanitization, and clearing stale artists.
Recent-history tests play eleven stations, enforce ten-entry retained history and
unique ordering, replay an entry, restart, and delete it. The visible limit defaults
to three, rejects values outside 1–10, persists across restart, and changes without
interrupting playback or truncating history. Legacy files default safely to
empty history, three visible entries, and disabled favicons. The legacy
playback-position field remains validated/persistent but no longer reorders the UI.
Image tests reject oversized PNG dimensions,
malformed ICO ranges, SVG, and oversized payloads. Favicon service tests verify no
requests by default, malformed/oversized responses, cancellation, preference
persistence, and reuse of the cached image without another request.

`make test-shell` tests actual GNOME actors in a disposable headless GNOME 49
instance. Private settings disable hot corners and automatic locking so virtual
input stays on the test desktop; host settings are unchanged.
It uses `gnome-extensions install --force` on the built ZIP after Shell startup,
checks that a repeated install replaces an overwritten runtime file, and runs
the documented first-install
command through the real Looking Glass evaluator, then checks invalid/valid station
entry, a station/title infobox without a source line, play/pause, persistence, disable/re-enable, and
rapid toggles. Search tests cover field visibility, case-insensitive name/source
filtering, empty results, selection, and restoring the full list. Virtual keyboard
input verifies automatic search from a collapsed list, first-character preservation,
continued typing, Ctrl+F, clear-icon reset, and unaffected station-editor typing.
Virtual pointer input verifies hover-only Play/Edit/Remove actions without label movement;
keyboard focus reveals and retains the actions through child focus. Row Play is
checked while already playing, while paused, and when switching to another station.
Leaving a hovered or pointer-selected row must hide Play/Edit/Remove in both lists,
even if native menu handling retained focus on that row. Keyboard-only focus still
reveals its actions. Light/dark checks also align the Play/Pause button's left edge
with the Recent heading below it.
Escape closes the popup and resets search. Hover screenshot: `workspace/hover.png`.
Layout checks
verify the input aligns with the Stations heading and native search
button, and the information box stays compact relative to its text. Screenshots
are saved to ignored `workspace/search.png` and `workspace/popup.png`. The workflow
checks native foreground color and the absence of notification popups even after
enabling the legacy service preference. It checks a single compact **Artist — Title**
row, clearing the artist when missing, and saved-station names without URL labels,
with a screenshot in `workspace/artist.png`. This is actor-level
E2E with isolated virtual input, not physical hardware automation. The test-only
bootstrap and evaluator access are confined to temporary settings and a private
bus; they are not packaged. Host D-Bus services cannot be auto-activated on that bus.
The infobox must show Play/Pause, Stop, text info, and the Quit power icon in order,
without a bottom textual Quit row or a placement switch.
Checks use a real pointer click while playing and Enter activation after the
service exits. They verify persistent extension disable, disappearance of the
indicator and service, saved-state recovery on re-enable, and other indicators'
ownership/placement. Quit is the intentional exception to inline controls keeping
the popup open.
Stop checks verify the backend exits while the popup remains open, cached station
state and the inactive indicator remain, and track text clears. Play must start a
fresh backend; Stop during a pending restart must cancel it. Editing a cached
station after Stop must wake the service without starting audio automatically.

Real virtual-pointer clicks verify that station selection, row Play/Edit/Remove,
main Play/Pause, settings switches, Search, Add, Save, Cancel, and editor Copy keep
the popup open. Enter activation of a station also preserves the popup and expanded
list. These checks exercise native click gestures and automatic menu dismissal,
rather than only emitting actor signals. The virtual pointer must reach both target
coordinates before clicking. Escape and outside clicks still close/reset the popup.

Run `GNOME_RADIO_TEST_SCALE=1.5 GNOME_RADIO_TEST_THEME=light make test-shell` for
the screenshot regression at an actual temporary 150% virtual-monitor configuration.
This changes only the disposable Shell's display/settings, not the host desktop.
The Nightride/Mascarpone title is checked for containment inside the infobox, clear
separation from the divider, and space for playback inside the popup. Screenshots:
`workspace/screenshot-regression.png` and its `-light`/`-dark` variants.
Light/dark changes must update native text colors while preserving width/height,
with a bold infobox name and smaller track text dimmed from that theme's foreground,
including after repeated no-logout module updates. Screenshots from a confirmed
150% run can be retained in `workspace/light-150/` for comparison.
No disposed-actor errors are allowed during station refresh or cleanup.
The same workflow temporarily selects `Serif 12` and 125% text scaling in its
private settings, then checks light/dark popup, saved-row actions, search,
Add/Edit, and settings. It requires the actual font/label height to change,
checks fixed width and screen containment, preserves the full Stations heading
while searching, and verifies the 30/70 editor split. Screenshots are saved as
`workspace/large-text-{light,dark}-{popup,search,edit,editor,settings}.png`.
Restoring the original typography must restore compact editor/search geometry,
including hidden placeholder metrics. These checks use native Shell themes;
they do not establish compatibility with arbitrary third-party themes.
On 2026-10-20, the complete workflow passed at 100% display scaling (114.822 s)
and 150% (122.578 s), including light/dark and larger-font checks. Screenshots
were inspected for hidden row actions, playback alignment, and contained fields.
Pointer checks verify that Stations, Settings, and Add/Edit replace each other;
showing Search returns to the saved-list view without leaving another panel open.

The native notification-center media card is verified to update artist/title in
place, remain during pause, resist notification clearing, and resume through its
own play/pause control. Track changes produce neither queued nor visible popup
banners. A screenshot is saved to `workspace/media-center.png`.

Station rows are checked for native menu styling rather than button-card styling;
edit controls use native `icon-button` styling. Panel checks verify `system-status-icon`
and native controls without flat styles. Light/dark checks compare the indicator
with a generic panel-only reference using a box and zero icon padding/margins.
Width, glyph size, and button height must match, including after live updates;
the standard padded-icon reference must be wider. No clipboard code or other
extension installation is required for tests. Layout checks confirm edit/search/add
buttons are smaller than play/pause, station rows have tight vertical padding,
and names remain centered beside their edit buttons. Missing song metadata produces an
empty, hidden song label, which becomes visible when a title arrives.
Ownership checks use two arbitrarily named app extensions on the private desktop.
All three indicators must retain separate panel containers regardless of startup
order, visibility, re-enable, and live updates. Being a non-system indicator does
not opt an extension into grouping. Real pointer clicks open each app's own popup
independently. GNOME system containers remain untouched, and disabling radiolina
preserves the peers. Fixtures run no clipboard code and depend on no installed apps.
Checks compare the other visible indicators' panel order before and after preference
changes, radiolina restarts, live updates, error recovery, and radiolina disable.
Grouping preference checks verify the default is off, the warning text matches
exactly, and enabling it reports the unsupported-host fallback without changing
other actors. The preference persists across service/UI restarts and live updates.
Visibility changes, peer reloads, toggling it off, radiolina disable, and recovery from
an injected duplicate-indicator error must preserve independent ownership/clicks.
Critical configuration tests cover legacy defaults and invalid preference types;
service E2E checks cover persistence and uninterrupted playback.
Recent rows persist and start playback. Saved stations begin collapsed and collapse
again on closing the popup; Search expands them. Section headings render bold and
Stations has a preceding separator. Current names remain regular weight with a
small play/pause/stop icon, a playing-only suffix, and no selection ornament.
The infobox divider retains equal gaps to the playback control above and heading below. The Stations divider uses
equal gaps to the action buttons and their icon glyphs above/below it, with and
without track metadata and with search open, allowing only pixel-rounding differences.
Opening search must preserve toolbar height, control positions, and separator size.
Focused, blurred, and hovered search fields keep identical dimensions/padding
and native entry styling. Search matches the action-button height and the native
styling/geometry of Name and URL inputs. Popup width is checked across forms,
search, errors, settings, and metadata changes.
Clipboard checks copy the URL from the editor without changing playback or selection;
list rows expose Remove in place of Copy. Both saved/Recent removal actions are
exercised, including history cleanup. Compact-form geometry checks align name/URL and
Save/Cancel into two rows. Settings tests change the Recent limit, verify the default
three-row cap with four played stations, retained history, disabled decrement at one,
and persistence across a live service/UI restart. Settings tests also toggle favicon downloads and
verify cached icon display/removal. Screenshots: `workspace/recent.png` and
`workspace/settings.png`; the PNG fixture also decodes with the installed image loader.

Infobox checks keep height constant with missing metadata, populated title/artist,
stopped playback, and validation errors. The station name centers by itself and
moves up when the track row appears; both lines stay within the fixed area. The
fixed control order is checked even with a legacy placement preference present.
Screenshot: `workspace/play-left.png` (the filename is retained for compatibility).

The workflow also repeats the safe loading command, reproduces the reported
duplicate-indicator conflict, and recovers through the real Looking Glass helper.
It verifies the panel loads the inactive radio SVG initially and after pause,
MPRIS Stop, and service restart, and the signal-marked active SVG during playback
and after resume. Playback checks verify the icon stays at full opacity without
an animation transition; status is conveyed by the static symbol.

The workflow also saves/cancels station edits, validates an edited URL, plays an
XSPF source, preserves saved changes, and swaps to a distinct UI module then back
in the same Shell to verify updates despite its JavaScript module cache.
Before loading, the test activates the earlier form-wide 276px entry rule and
verifies it affects an old-style probe. New startup must remove those applet
styles, keep the Name field narrow, and contain URL/Copy within the fixed popup.
Add and Edit also check the 30/70 Name/URL width ratio, excluding spacing and Copy.
An unrelated stylesheet must survive. Ordinary updates change versioned CSS and
restore the original version; field widths must follow each version and native
light/dark switching must work. Radio operations must preserve the actual shared
theme object, and a peer's cached reference must still load/unload effective rules.

After normal theme-variant checks, the test injects duplicate identifiable applet
styles and an unrelated unaddressable parsed sheet. It verifies that an update,
rapid disable/re-enable, failed enable/actor recovery, and final disable preserve
the theme object, foreign stylesheet order, and the orphan rule's effect. Radio
must not discard unidentified entries; test enumerations tolerate missing files.
Shell's own theme changes may legitimately replace the theme. On tested GNOME 49.8, an
unaddressable entry can make Shell's native light/dark reload fail with a null-file
error. Such pre-existing damage is left alone and may require a fresh Shell session,
rather than global registry repair by Radio. Disable removes identifiable applet
styles while retaining foreign and unidentified entries.

On 2026-10-14, the user also confirmed the indicator became visible in their
running GNOME 49.8 session after the recovery helper, without logging out.

Latest verification: 2026-10-20, Fedora 43, GNOME Shell 49.8/Mutter 49.7, GJS 1.86,
GStreamer 1.26.11. The 9 unit, 16 service E2E, and 1 Shell workflow tests pass.
The Shell workflow passes at 100% and 150% scaling, including native light/dark
switching, unsupported-group fallback, indicator ownership, and lifecycle recovery.
The service idle sample was 36.6 MiB RSS and 0.000s CPU over 1.00 second inside the
container. RSS includes shared library pages; results are not a guaranteed budget.

A separate 2026-10-20 sample used the production service in the offline development
container, a local MP3 fixture, and synchronized silent output. After playing and
settling in Pause for five seconds, the service used 46.9 MiB RSS (41.4 MiB PSS)
and recorded 0.000 CPU seconds over 10.002 seconds. MPRIS Stop retained 47.0 MiB RSS;
Quit exited the process and released its D-Bus name. These are service-only samples,
not whole-applet memory measurements: the UI shares GNOME Shell's process. Pause
retains the playback pipeline and buffers; it does not close the applet. Real
streams, codecs, audio output, and allocator behavior can change these figures.
The new infobox Stop instead terminates that service, leaving only the Shell UI;
E2E checks verify disappearance of its bus owner and restart with a new owner.
The final native 150% run measured 54.7 MiB backend RSS before infobox Stop and
confirmed the process was absent afterward, with the indicator still usable.

In the earlier manual compatibility check, Nightride's real `.mp3.m3u` and
`.mp3.xspf` files were fetched and parsed successfully. Both advertised
`http://lissen.to:8000/nightride.mp3` at verification time. This checks playlist
format compatibility, not the availability of that advertised stream endpoint.
PyGObject emits upstream Python 3.14 deprecation warnings, without test failures.
The minimal test desktop also logs missing calendar/accessibility services.

## Small disposable desktop profile

A Fedora 43 Workstation Live VM provides GNOME Shell 49.1 for the remaining
desktop checks. A locally verified profile uses **2 vCPUs, 2 GiB guest RAM,
KVM, and accelerated virtio graphics** at 1280×720. The ISO and extracted boot
files occupy about 2.9 GiB; no installed guest disk is required. Verify Fedora's
signed checksum and the ISO hash before booting. Use the built extension ZIP as
read-only guest media, user-mode networking, and output-only audio through SPICE.
Keep clipboard/file transfer and host-directory sharing disabled.

Install the ZIP inside the live guest, then enable radiolina after the desktop
has finished starting. The verified applet was ACTIVE with its service Stopped,
a saved test station, and no reported playback error. Configured guest RAM is
not total host usage: a short QEMU sample used about 2.3 GiB RSS, including guest
RAM and virtualization/graphics overhead. These are environment measurements,
not applet resource figures or a guaranteed minimum.

The earlier ten-second deadline killed the backend during cold GStreamer registry
discovery. A controlled guest sample took 69.6 seconds with an empty registry,
then 1.1 seconds with that registry cached. Readiness now has a cancellable
120-second deadline and fails promptly if the child exits. An isolated Shell
regression delays the backend for twelve seconds, checks successful readiness,
Stop during startup, early-exit reporting, and recovery. No recurring timer or
additional runtime dependency is introduced. Check the backend's bus/state as
well as the extension's ACTIVE flag.

On 2026-10-20, the delayed-start regression failed with the old deadline and the
expanded Shell workflow passed with the fix (100.007 seconds), including startup
cancellation, early exit, recovery, and backend removal after Stop. Packaging
checks passed. The fixed ZIP also passed fresh live-VM activation without a
disable/re-enable workaround, with playback Stopped and no reported error.

Live guest changes disappear on power-off; repeat installation on the next boot.
Set a guest-only password and enable normal screen locking for lifecycle checks.
Stop the VM and close its viewer when unused. Physical media keys may be
intercepted by the host; verify keyboard capture. Guest suspend checks do not
establish hardware suspend compatibility. Preparing this environment does not
complete the manual acceptance checks below.

## Manual acceptance on a disposable desktop

Autonomous verification on 2026-10-20: the offline service suite passed in 143.363
seconds; the expanded Shell workflow passed in 101.058 seconds. Light/dark error
screenshots were visually inspected and checked for native foreground, full text
opacity, containment, persistence across popup reopening, and recovery. A forced
teardown race covers an object disappearing before its bus name is released.
In the GNOME 49.1 VM, actual virtual-link loss produced the visible timeout in
38.46 seconds, including buffered audio; reconnecting and activating Play restored
Playing with the error hidden. Popup width remained 394 pixels. Guest screenshots
were inspected directly; networking was restored and temporary guest-only evaluator
access was disabled afterward. The host desktop was not modified.

On 2026-10-20, the maintainer confirmed audible Nightride FM playback in the
Fedora 43/GNOME 49.1 live VM through the SPICE viewer, using the fixed startup
build. The maintainer also confirmed that the physical Play/Pause key pauses and
resumes radiolina with the VM focused. Guest locking stopped audio; unlocking
restored the idle indicator without autoplay, and Play resumed audible output.
The maintainer also confirmed readable text/icons and contained fields/buttons
in the popup, expanded Stations list, and Add/Edit form in native light and dark
modes, switching the guest's system preference without restarting the applet.
Native high contrast with the dark preference also passed the maintainer's visual
check of these views, including visible keyboard focus during Tab navigation and
no clipping. The guest's original theme preferences were restored afterward.
These results cover that stream/environment; multiple-player routing, suspend,
and the remaining checks below are pending.

The subsequent guest Suspend attempt left the live VM unresponsive. QEMU still
reported running and rejected its wake command; keyboard and ACPI power-button
events did not restore the console. The disposable guest required a restart.
Suspend/resume remains unverified: this observation does not establish an applet
cause. Validate the environment's full sleep/wake cycle before repeating this check.

1. Install the built ZIP in a GNOME 49 VM, enable it, and open the indicator.
2. Add a direct stream from [Nightride FM](https://nightride.fm/); confirm audible
   playback, pause/resume, station switching, and persistence after restart.
3. Confirm text, station rows, and native controls follow the active Shell theme,
   including theme changes and high contrast. Check long-label ellipsizing,
   keyboard navigation to controls/form, and popup fit at different scales.
4. Press physical Play/Pause keys, including with another MPRIS player running.
   Confirm signal marks appear while playing and disappear while paused/stopped,
   without any icon animation. Check theme color and visibility at different scales.
5. Start typing or press Ctrl+F; confirm search expands the list without losing
   the first character. Click Search to toggle its inline field; clear a query
   with its clear icon. Hover/focus a row to reveal Play/Edit/Remove without moving names,
   and verify typing in the editor does not trigger search. Check equal icon clearance
   on either side of the Stations separator, including while searching, and confirm
   search shares Name/URL's native styling, matches action-icon height, and has
   stable padding. Confirm popup width remains constant through all views.
   Filter by name/source, then hide it to restore the
   list. Click **+** to add a stream; confirm the station name remains in the compact
   information box, artist and title share a single row, and song changes show
   no desktop notifications. Check a track without artist displays only its title,
   and the infobox/list rows hide URLs while the editor and Copy retain them.
   Copy from the editor and Remove from both lists; check current-station removal
   stops playback. Confirm the fixed transport order and readable ellipsized metadata.
6. Disconnect networking; verify a useful error and successful manual retry.
7. Click infobox **Stop** while playing; confirm the backend exits, the indicator
   and stations remain, and Play restarts the stream. Check editing after Stop and
   repeated Stop/Play clicks. Click the infobox **Quit** power icon; confirm the
   indicator and service disappear. Re-enable radiolina in Extensions or with
   `gnome-extensions enable radiolina@drdaniloromano.github.io`; saved stations/preferences must
   survive. Quit must also work when the service is unavailable. Verify normal
   extension disable still stops playback and removes the indicator.
8. Play four or more saved stations; verify only three Recent rows appear by default,
   change the count (1–10) in Settings, and check recent ordering, retained history,
   persistence, and collapsed saved-list behavior. Verify paused names lose the
   playing suffix. Enable favicons in Settings and check available real-world
   stream-host icons; disable it and confirm icons disappear without stopping audio.
9. Confirm **Group with other app indicators** starts off and displays the exact
   compatibility warning. With no supported host, enabling it must report that
   radiolina stays separate. Check independent app clicks, panel order, reloads, and
   radiolina disable/re-enable; no other extension should move or change behavior.
   Test any future cooperative host adapter's join, leave, host loss, and error
   recovery in this isolated desktop before enabling it on a user's session.
10. While playing, lock the disposable desktop and confirm audio stops. Unlock;
    confirm the indicator returns with saved stations/preferences intact and no
    automatic playback. Press Play to reconnect. Repeat around suspend/resume
    using the guest's normal lock settings; verify the same behavior when locked.

Audible playback, basic physical Play/Pause, lock/unlock, and native high contrast
have the maintainer confirmations recorded above. Multiple-player media-key
routing, suspend/resume, third-party themes, and display scales beyond those tested
remain open. Native light/dark switching, an alternate font with 125% text scaling,
and 150% display scaling are covered by the automated Shell workflow. The local tests
never install dependencies or enable the extension in the user's desktop session.
