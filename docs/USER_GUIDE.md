# User guide

See the [README](../README.md) for requirements, release status, and standard installation.

## Same-session installation and updates

These procedures target GNOME 49/50 and use the internal extension manager through
Looking Glass. A normal fresh login also loads installed files. Installing a ZIP
replaces files on disk; it does not replace JavaScript already imported by Shell.

### Migration from the development ID

If `gnome-radio@local` is installed, disable it before enabling radiolina:

```sh
gnome-extensions disable gnome-radio@local
```

Wait for its indicator and playback to stop, then install the new package:

```sh
gnome-extensions install --force build/radiolina@drdaniloromano.github.io.zip
```

Both IDs use the same configuration/cache paths, preserving stations, selection,
history, and preferences. Keep the old ID disabled. After checking the new
installation, you may uninstall `gnome-radio@local` while retaining its data directory.

### First installation without logging out

If the ZIP is installed but `gnome-extensions info radiolina@drdaniloromano.github.io`
says the extension does not exist, press **Alt+F2**, type **lg**, and press Enter.
Paste this single line into Looking Glass and execute it:

```js
if (!Main.extensionManager.lookup('radiolina@drdaniloromano.github.io')) await Main.extensionManager.loadExtension(Main.extensionManager.createExtensionObject('radiolina@drdaniloromano.github.io', Gio.File.new_for_path(GLib.get_user_data_dir() + '/gnome-shell/extensions/radiolina@drdaniloromano.github.io'), 2)); Main.extensionManager.enableExtension('radiolina@drdaniloromano.github.io')
```

Press Esc to close the console. This path is for an extension not yet loaded in
the session; use the updater below for an already imported version. The Shell
E2E workflow exercises this procedure. Remote D-Bus evaluator access stays disabled.

### Updating without logging out

Build and install the new ZIP, then run this in Looking Glass. Replace the example
path with your checkout's absolute path; it is JavaScript, not a shell command:

```js
(await import('file:///path/to/gnome-radio-applet/scripts/live-update.js')).update(Main)
```

Wait for `radiolina updated`, then press Esc. The helper stops the old playback
service, disables this project's former development ID if loaded, and loads the
installed content-addressed UI module and versioned stylesheet. Saved data and
unrelated extensions are preserved. Press Play to resume.

Check the current identity:

```sh
gnome-extensions info radiolina@drdaniloromano.github.io
```

Expect **Enabled: Yes** and **State: ACTIVE**; the old ID must remain disabled.
That status alone does not identify a particular build: the updater must finish
successfully, and the new behavior must appear. GNOME caches helper modules too;
if you changed a helper during this session, use a fresh file URI or a fresh login.

## Playback and station management

The infobox contains one Play/Pause button combining the circle and station/track
text, followed by optional Stop and Quit. Hover highlights the combined area;
Enter/Space activates it when focused. Station names are bold, with available
**Artist — Title** below in smaller, subdued text. A missing song title leaves
that line hidden. Metadata comes from the stream; combined `Artist - Title`
fields are interpreted without an external lookup and stale data is cleared.

| Action | Result |
| --- | --- |
| Pause | Keeps the service and paused pipeline/buffers; resuming may lag the live edge. No recording or dedicated time-shift buffer is created. |
| Infobox Stop | Closes the stream and exits the service, keeping the indicator and cached stations. Play, editing, or settings can restart the service on demand. |
| MPRIS Stop | Releases the stream pipeline while leaving the service available. |
| Quit / extension disable | Removes the indicator and stops the service; saved data remains. Re-enable radiolina in Extensions or with the README command. |
| Screen lock / unlock | GNOME's default user-session lifecycle stops playback on lock and restores the idle indicator on unlock, without autoplay. |

Media keys and the persistent native media card work while the service runs;
after infobox Stop, use panel Play to restart it. GNOME controls routing among
multiple media players. Track changes update the card silently, without banners
or notification sounds. Static signal marks indicate Playing; the plain radio
indicates paused, stopped, connecting, or failed playback.

**Recent** defaults to three entries, newest first. Settings allows 1–10 visible
entries; ten unique played stations are retained, so lowering the count does not
erase history. The saved list starts collapsed. Expand it with the Stations arrow,
click Search, start typing, or press Ctrl+F. Filtering matches saved names and
source URLs without case sensitivity; it is not an online station directory.
Clear the query with its clear icon, or hide Search to restore the full list.
Typing in the editor changes its fields normally.

Hover or keyboard-focus a station row to reveal Play, Edit, and Remove without
moving its label. The selected row has a playback-state icon and a **(playing)**
suffix only during active playback. Play leaves an already playing station running. Edit preserves
station identity: renaming does not interrupt playback, changing a playing URL
reconnects, and a paused station stays paused. Name and URL share a row at 30/70
of available input width. Copy beside the URL copies the current field without
saving or changing playback. Remove deletes saved/history entries and stops
playback if that station is selected. Save, Cancel, and Delete share the editor's next row.

Stations, Add/Edit, and Settings replace one another in the lower area; the
infobox and Recent remain visible. Actions keep the fixed-width popup open.
Escape, outside clicks, and clicking the indicator dismiss it.

## Settings

- **Recent stations:** 1–10 visible entries; default 3.
- **Show Stop button:** off by default; persists without changing playback.
- **Group with other app indicators:** off by default. No cooperative host is
  currently supported, so enabling it reports that radiolina stays standalone.
  It does not move, restyle, or change input handling for other indicators.

The grouping option displays this warning:

> Grouping may be incompatible with some extensions or panel customizations. Disable this option if icons, menus, or clicks behave unexpectedly.

## Stream formats and saved data

Use HTTP(S) audio URLs or ordinary M3U/M3U8 and XSPF playlists. Resolution chooses
the first usable HTTP(S) entry and supports relative URLs, redirects, XML entities,
CDATA, and namespaces. The original playlist URL remains saved. HLS manifests
and XML DTD declarations are not supported. See the [input bounds](DEVELOPMENT.md#input-and-resource-bounds).

The validation policy admits MP3, AAC, FLAC, Ogg Vorbis/Opus/FLAC,
PCM/float WAV, and audio-only MP4/M4A containing an allowed codec. Availability
also depends on installed decoders; missing support reports **Required codec
unavailable**. No codecs are downloaded automatically. Video, HTML, HLS, and
other formats are rejected even when the URL ends in `.mp3`. Filename extensions
and HTTP content types alone do not establish the format.

Identification reads at most 64 KiB from the actual response, then passes the
same buffered stream to an explicit decoder pipeline. ID3 and MP4 audio headers
must fit within that prefix; MP4 headers must precede audio data. Large artwork
or non-streamable M4A files can therefore be rejected. Normal ICY/ID3 track
metadata remains supported.

Redirects are limited to five across playback/playlist resolution. Credentials
and fragments in URLs, and HTTPS-to-HTTP redirects or playlist destinations, are
rejected. HTTP URLs entered explicitly and local/LAN stations remain supported.
If an HTTPS station points to HTTP-only audio, use its HTTP URL explicitly if
you accept an unencrypted connection. These validation rules apply from 0.4.0;
the `v0.3.0` tag retains its original behavior.

A manual example is `https://stream.nightride.fm/nightride.mp3`; see
[Nightride's stream server](https://stream.nightride.fm/) for stream endpoints.

Configuration is `${XDG_CONFIG_HOME:-~/.config}/gnome-radio/stations.json`.
The legacy directory name intentionally preserves existing data. Corrupt configuration is reported
and retained for repair rather than overwritten.

To edit stations manually, Quit radiolina and back up the JSON file first. Edit
its `stations` array, preserving other settings; each entry has this form:

```json
{"id":"my_radio","name":"My radio","url":"https://example.com/live.mp3"}
```

IDs must be unique ASCII letters/digits/underscores/hyphens, 1–128 characters; URLs must also be
unique. `selected` must reference an existing ID or be empty, and `recent` may
contain only unique existing IDs, at most ten. Up to 200 stations are allowed,
with names up to 80 characters and URLs up to 2,048 characters. URLs must not
contain credentials, fragments, whitespace, or control characters. Re-enable
radiolina to load the edited file. There is no one-URL-per-line saved-list importer.

The UTF-8 JSON file must fit within **1 MiB**
(including whitespace); unknown fields are rejected. Supported top-level fields
are `version`, `stations`, `selected`, `notifications`, `recent`, `recentLimit`,
`fetchFavicons`, `showStopButton`, `playButtonOnLeft`, and `groupWithAppIndicators`.
Station entries accept only `id`, `name`, and `url`. Existing version-1 files
without newer optional settings still receive their defaults. A rejected file
is left untouched and settings/station writes are blocked: back it up, repair it,
then restart radiolina. These limits address local configuration resource use;
they do not establish protection against malicious same-user processes.

Favicon fetching and its setting are removed in 0.4.0. The legacy
`fetchFavicons` boolean is accepted but always inactive, including through older
clients. Existing cache files under `${XDG_CACHE_HOME:-~/.cache}/gnome-radio/favicons/`
are left untouched and no longer read or written. You may delete that directory
after quitting radiolina if you want to reclaim its space.

## URL privacy

MPRIS media metadata omits the stream URL;
station/track names, artist and media controls remain available. The final redirect
URL is not published in application state. Application errors use bounded,
code-authored messages or generic fallbacks instead of raw backend diagnostics.

Saved URLs can contain access tokens in their paths or query parameters. They
remain complete for playback, editing and explicit **Copy**, in the unencrypted
`stations.json` file (mode `0600`) and station-management D-Bus state. Other
processes running as your user may access these; this is not credential isolation.
Copy places the full URL on the desktop clipboard, where clipboard tools may retain
it. The stream server still receives the URL needed for playback. Stream-provided
titles/artists remain visible as metadata. Avoid sharing private URLs or station
files; review diagnostic output before attaching it to reports. Native-library
debugging, enabled separately, is outside the application's safe-message policy.

## Troubleshooting

| Symptom | Checks and recovery |
| --- | --- |
| No indicator after installation | Verify GNOME 49/50 and the permanent UUID with `gnome-extensions info`. For an unregistered first install, use Looking Glass above or log out/in. Quit deliberately disables the extension; re-enable it to reopen. |
| Old layout or missing new option | Installing a ZIP does not reload imported UI modules. Run the same-session updater, verify it succeeds, and reopen the popup. |
| Slow first activation | Cold GStreamer plugin discovery can take over a minute. Readiness has a cancellable 120-second deadline; Stop, Quit, or disable cancels it. ACTIVE alone does not prove the backend is ready. |
| Connection error or stalled stream | Check the URL, codec availability, and networking. Playlist resolution has a 15-second limit; connection/rebuffering has a 30-second one-shot deadline, excluding normal playback/Pause/Stop. The popup preserves errors across reopening; Play retries. |
| Service unavailable | A backend crash clears metadata and leaves the indicator with a retry message. Play starts a new service; saved stations remain and there is no automatic restart loop. |
| No song information | Some streams send no metadata. Audio can still play; there is no external song lookup. |
| Media keys stop working after Stop | The service is absent. Restart it using Play in the indicator. With multiple players, routing belongs to GNOME. |
| Unexpected theme after repeated development loads | Only identifiable applet styles can be removed safely. Unaddressable stale CSS may require a fresh Shell session; radiolina never replaces the shared theme or removes unidentified/foreign styles. |

For a duplicate-indicator error after a loading attempt, install the current ZIP
and run this helper in Looking Glass, substituting your checkout's absolute path:

```js
(await import('file:///path/to/gnome-radio-applet/scripts/live-recover.js')).recover(Main)
```

It removes this applet's orphaned actors, stops its old service, and loads one
instance while preserving saved data and other extensions. Do not manually create
a second extension instance. Report remaining problems via [GitHub Issues](https://github.com/drdaniloromano/radiolina-ext/issues)
with your GNOME version, reproduction steps, and relevant errors; omit credentials
and private station URLs from reports.
