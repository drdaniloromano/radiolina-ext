# Dependency security checks

## Why check

Stream validation limits accepted input; native libraries still parse and decode
it. An exploitable library defect can remain reachable through an accepted format.
The playback process runs with the user's privileges. Development containers and
crash recovery do not provide an installed runtime sandbox.

The ZIP uses the destination desktop's libraries. Checking the development image
does not check users' machines. The current advisory backend supports **Fedora,
RPM and DNF5**; other distributions need their own vendor review.

## Run before a release

Use existing tools; the checker never installs/upgrades packages or imports keys
interactively. It uses temporary cache/state directories and needs repository
network access. The installed applet performs no advisory monitoring.

```sh
umask 077
mkdir -p workspace
make security-check
make container-refresh
make container-test
make container-security-check > workspace/security-container.json
```

The desktop check writes `workspace/security-desktop.json`. Add
`CONTAINER_ENGINE=docker` to the container command when using Docker. Reports are
private machine metadata: keep them ignored and review before sharing. Ordinary
tests remain offline; security queries are separate, opt-in tooling.
`container-refresh` pulls the base and rebuilds without cache with vendor package
updates inside the image. Use a separate `IMAGE=...` consistently across commands
to preserve an existing development image. Rebuilding alone is not an advisory
review, and it does not update libraries used by an installed desktop extension.

## Read and review the report

The report records source/checker fingerprints, environment/image identity, exact RPM
builds/architecture, installed explicit GStreamer factories, conservative recursive
package dependencies, repository metadata and available/installed security notices.
The Fedora backend queries enabled `fedora`, `updates` and
`fedora-cisco-openh264`; excluded repositories, foreign vendors and refresh failures
produce incomplete coverage. Successful repository results are retained.

| Script exit code | Meaning |
| --- | --- |
| `0` | No outstanding vendor advisories returned within the automated scope. Manual review remains required. |
| `1` | Vendor security advisories need review; this does not establish exploitability. |
| `2` | Incomplete inventory, metadata, schema, repository or distribution coverage. |

Make returns nonzero for failures; use JSON `exit_code` for the precise reason.
An empty/malformed/missing report cannot pass. Inspect `coverage.issues` even when
some advisory queries succeeded.

Read the relevant [upstream notices](https://gstreamer.freedesktop.org/security/)
and GNOME library release links in `manual_review.sources`. Compare affected
components with actual pipelines and vendor package builds. Distribution backports
can fix defects without adopting the newest upstream version. Record each finding
as affected, vendor-fixed, justified not-applicable, or unknown; installed historical
advisories and an empty result do not prove complete security. Upstream applicability
and dynamically selected native backends are not automatically assessed.

## Release priorities

Use a proportionate review of radiolina's code and actual network/decoder paths,
not an audit of every package in the desktop dependency closure. Before release,
check vendor/upstream advisories, run relevant isolated tests and record a
maintainer decision. GNOME's [extension review rules](https://gjs.guide/extensions/review-guidelines/review-guidelines.html)
also require lifecycle cleanup and careful process handling; they do not prescribe
reconstructing every dependency's source patches.

Keep **technical status** (affected, fixed, not-applicable, unknown) separate from
**release priority**:

- **Block the affected release/runtime:** a confirmed or credibly suspected serious
  defect exposed through the intended app path, such as native memory corruption,
  secret disclosure or remotely triggered resource exhaustion. Obtain a fix,
  supported backport or justified mitigation and verify it before endorsement.
- **Focused follow-up:** contradictory metadata, uncertain indirect reachability
  or limited coverage. Record evidence, potential impact, owner, next action and
  a review trigger. Unknown does not automatically block or clear a release;
  investigate before release if a serious app-path exposure remains plausible.
  Any deferral needs an explicit rationale and maintainer decision, not silence.
- **Distribution maintenance:** broader desktop findings without an established
  radio-controlled path. Keep vendor update advice and uncertainty visible, but
  do not require radiolina to certify unrelated system services. Escalate if new
  evidence connects the vulnerable operation to playback or Shell integration.

Vendor notices identifying exact fixed builds normally suffice for patch status.
Inspect source/backports when important applicability or fix evidence conflicts;
do not routinely reconstruct patches, execute exploits or prove every possible
indirect native call. Incomplete reports remain incomplete, never an automated
pass or a claim of complete security. Functional tests do not prove parser safety.

### Current decision summary

This **2026-10-22** prioritization uses retained reviews, not a fresh package scan
or release approval. It replaces blanket rules that every unknown finding blocks
publication; the detailed technical findings below remain unchanged.

| Remaining item | Priority and next action |
| --- | --- |
| Older Fedora 43 GStreamer builds with missing fixes, including selected Opus/WAV paths | Block endorsement of that unpatched runtime. Choose a supported patched baseline/backport and verify it; GNOME 49 compatibility alone does not require using these old native builds. |
| Reviewed Fedora 44 GStreamer fixes | Retain the scoped source evidence; no need to repeat each reconstruction without a relevant change. This does not certify all dependencies or user desktops. |
| Older caption/caps/buffer reachability and libsoup identity conflicts | Focused follow-up, technical status still unknown. Resolve serious plausible exposure on the chosen runtime; metadata disagreement alone is not a confirmed vulnerability or an automatic blocker. |
| AAC/FFmpeg and third-party codec coverage | A separate Fedora 44 profile now verifies ADTS AAC and AAC-in-M4A using the vendor libav decoder. Original Shell profiles still lack AAC decoders; other codecs/vendors remain scoped separately. Missing advisory coverage is uncertainty, not proof of a flaw or a fix. |
| Broad desktop/system dependency findings | Vendor maintenance unless evidence establishes app-path relevance. Preserve open technical assessments; no blanket exclusions or host-wide source audit. |
| Physical audio/media keys, lock/suspend and genuine Docker | Separate coverage limits, not automatic blockers. Use available isolated environments for targeted checks and record untested scope. Full desktop VMs are optional; keep the [automated container checks](TESTING.md). |

Use the reviewed patched-runtime reference and codec results for final scoped
review and packaging. Optional desktop checks do not require another guest OS.
No supported Shell version, format, host package or release status changes merely
because this prioritization is recorded.

## Repeatable advisory triage

Start with the priorities above; related findings may share a bounded review.
Agents must follow this procedure too. Preserve per-advisory records; a grouped
priority review can reference them without repeating source investigations:

1. **Identify the snapshot.** Retain the original report unchanged. Record its
   timestamp, source/checker/inventory fingerprints, image ID or desktop identity,
   exact package build, advisory/CVE IDs and coverage gaps. Confirm that the
   inspected source and environment still match; otherwise collect a new report.
   Preserve archive member paths or use collision-free evidence names: runtime
   and test sources can share a basename. Verify the saved file's hash and member
   identity before comparison. Retain flawed historical artifacts and document
   corrections in a new dated report rather than rewriting the original evidence.
2. **Verify the defect.** Read primary upstream and distribution notices. Record
   the affected operation, input/configuration prerequisites and vendor fix or
   backport evidence. A version comparison alone cannot establish patch status.
   Prefer clear vendor evidence; inspect native source only when needed to resolve
   an important uncertainty or contradiction.
3. **Trace reachability.** Explain why the package appears in the inventory, then
   trace accepted bytes through `src/core/validation/media.js`,
   `src/service/source.js` and `src/service/decoder.js`. Inspect actual factories,
   fallback codecs and dynamic audio backends as relevant. Package presence or a
   loaded library alone does not establish that the vulnerable operation runs;
   absence in one trace does not prove that it cannot run.
4. **Record a bounded decision.** Save a dated review under ignored
   `workspace/security-reviews/`, one Markdown report per advisory review.
   Start filenames with the UTC review time for chronological sorting:
   `YYYY-MM-DDTHH-MM-SSZ--desktop-or-container--ADVISORY-ID.md`. Include reviewer,
   report reference, identities above, source links, commands/results, reasoning,
   limitations, classification, release priority and next action. Mark partial
   reviews explicitly; keep reassessments as new dated reports referencing the earlier decision.
   Use **affected**, **vendor-fixed**, **justified not-applicable**, or **unknown**.
   Justified not-applicable requires evidence that the vulnerable operation's
   prerequisites cannot occur in the reviewed paths. Missing evidence stays unknown.
5. **Resolve and recheck.** Keep affected/unknown findings and incomplete coverage
   open; being open alone does not determine release priority. Record the reason
   for blocking, following up or assigning distribution maintenance. Propose
   package/image updates separately; never update the host or add an
   advisory exclusion silently. After an approved update, rerun inventory and
   relevant contained tests. Reassess previous decisions when source, factory,
   package, image or advisory details change; no permanent CVE allowlist.

Machine-specific findings belong in the private review, not `AGENTS.md` or a
public claim that all installations are safe. Manual decisions do not rewrite the
raw report or turn `release_approved` into an automatic approval. Do not run
exploit samples or resource-exhaustion probes on the maintainer's desktop.

## Review conclusions and resolution guidance

These **2026-10-21** notes describe the application paths included in **0.4.0**,
not the security status of every installation. Detailed environment evidence and
working review notes remain private. The dependency review is still open.

- **AV1 encoder: justified not-applicable to current playback paths.**
  [CVE-2026-56208](https://bugzilla.redhat.com/show_bug.cgi?id=2544505) requires
  AV1 video encoding with look-ahead processing. The explicit audio pipelines
  neither construct nor configure that encoder. The
  [upstream fix](https://aomedia.googlesource.com/aom/%2B/243f8ae84b%5E!/)
  changes encoder buffer handling. This conclusion does not mark an installed
  `libaom` package fixed or cover other applications using it. Update affected
  environments through their vendor; reassess if playback/encoding paths change.

### libsoup advisory applicability

`HttpSession` uses `Soup.Session`; native protocol parsing precedes media-byte
inspection. The reviewed [upstream 3.6.6 source](https://download.gnome.org/sources/libsoup/3.6/libsoup-3.6.6.tar.xz)
offers HTTP/2 over direct TLS connections by default. URL/format validation cannot establish
protection from HTTP/2 defects. Assessment of the eight current CVE IDs referenced by
`FEDORA-2026-fce2f41203`:

| Issue | Current radiolina paths |
| --- | --- |
| [CVE-2026-15712: GOAWAY over-read](https://bugzilla.redhat.com/show_bug.cgi?id=2500132) | Verified test builds are vendor-fixed at matching-source scope; see the reassessment below. The earlier desktop `3.6.6-3.fc43` snapshot remains conditional on HTTP/2 debug logging. The [upstream patch](https://gitlab.gnome.org/GNOME/libsoup/-/commit/3a6fb56a0cba42d11f5fd1db6dedcc7c2e92757b.patch) identifies that prerequisite; inherited settings can enable it on unfixed builds. |
| [CVE-2026-15713](https://gitlab.gnome.org/GNOME/libsoup/-/work_items/541) | Upstream identifies authenticated-response leakage through a shared cache: justified not-applicable to current app paths, which attach no `Soup.Cache`. Both test builds include that fix at matching-source scope. The vendor's conflicting HTTP/2 cleanup description remains unresolved; see below. |
| [CVE-2026-15709: WebSocket deflate](https://access.redhat.com/security/cve/cve-2026-15709), [CVE-2026-15711: control frames](https://bugzilla.redhat.com/show_bug.cgi?id=2500545) | Justified not-applicable: the app establishes no WebSocket connection or upgrade handshake. |
| [CVE-2026-15714: multipart reader](https://access.redhat.com/security/cve/cve-2026-15714) | Justified not-applicable: the app reads the response stream directly and never constructs `Soup.MultipartInputStream` or requests multipart parts. |
| [CVE-2026-77680: Range coalescing](https://access.redhat.com/security/cve/cve-2026-77680), [CVE-2026-77014: Range sorting](https://access.redhat.com/security/cve/cve-2026-77014) | Justified not-applicable: the app runs no `Soup.Server` and never invokes Range parsing APIs. |
| [CVE-2026-12549](https://access.redhat.com/security/cve/cve-2026-12549) | Unknown: the vendor description discusses server Range handling while its statement/mitigation discusses WebSockets. Neither is used here, but the contradictory metadata needs clarification before closure. |

The Range notice also cites CVE-2025-32907 as historical context. Its
[server Range handling](https://access.redhat.com/security/cve/cve-2026-77680)
is outside the same current app paths; this is not an additional new finding.

**2026-10-22 GOAWAY reassessment:** the loaded libsoup libraries belong to
`3.6.6-5.fc43` and `3.6.6-10.fc44`. Their matching official source RPMs include
the exact upstream GOAWAY patch, applied by both build recipes. Reconstructing
the HTTP/2 source in declared patch order with exact contexts confirms `%.*s`
plus the frame's explicit data length; classify this CVE as vendor-fixed at
matching-source scope for both test profiles. Separate process-local logging
checks confirm default debug suppression can be overridden. No request or malformed
frame was sent; no installed source/library was changed or binary rebuilt.
The historical desktop snapshot was not rescanned. Other libsoup CVEs and
publication requirements remain open; this is not a complete advisory scan.

**2026-10-22 cache/identity reassessment:** upstream issue 541 and its
[patch](https://gitlab.gnome.org/GNOME/libsoup/-/commit/24fb645fa949ece7d7e10363b77cf2d5fa2c2469.patch)
identify CVE-2026-15713 as authenticated responses being stored in a shared cache
without explicit permission. Radiolina never attaches a cache; offline probes
using its session constructor confirm no cache feature in either test profile.
Both matching source RPMs apply the byte-identical upstream patch; exact
recipe-ordered reconstruction confirms all three runtime fix contexts.
This verifies the cache fix in `3.6.6-5.fc43` and `3.6.6-10.fc44`, without
rebuilding binaries or running an attack. Reassess if caching is introduced.
The [vendor tracker](https://bugzilla.redhat.com/show_bug.cgi?id=2499941) instead
describes an HTTP/2 cleanup leak. That description is not established as fixed
by this cache patch: retain the identity conflict and potentially applicable
HTTP/2 claim as unknown pending authoritative clarification. This corrects the
earlier cleanup-only assessment; it does not rescan the historical desktop or
clear the complete advisory.

**Resolution:** use the distribution's supported update process to obtain a
vendor-fixed libsoup build. Fedora identifies `libsoup3-3.6.6-5.fc43` and
`libsoup3-3.6.6-10.fc44` as fixing
the GOAWAY issue; that fact alone does not verify every CVE in the advisory.
Confirm fixes/backports individually, restart affected processes, and rerun
inventory plus relevant transport tests in isolation. Keep debug logging disabled
on an unfixed GOAWAY implementation; this does not resolve the other open issues.
These are source/vendor assessments, not successful exploit reproductions or a
claim of parser immunity. Reassess when client features or native packages change.

Third-party codec packages and repositories without advisory coverage remain a
separate open item. Do not equate missing vendor results with absence of flaws,
remove those repositories automatically, or substitute Fedora patch status for
another vendor's package. Changes to the host or development image require a
separate agreed update step.

### Native decoder release blockers

Upstream review found issues absent from the vendor query's outstanding results.
The Fedora `1.26.11-1.fc43` source RPMs matching the reviewed Base/Good/libav builds
retain the old code in the five selected parser/decoder paths below; their build
recipes do not apply these backports. Additional core/container cases remain
unverified. This is source evidence, not an executed exploit. The
bounded admission prefix does not validate every later codec frame or metadata tag.

| Upstream advisory | Reviewed path / result |
| --- | --- |
| [2026-0053: Opus channel positions](https://gstreamer.freedesktop.org/security/sa-2026-0053.html) | Selected `opusdec`; the source lacks the greater-than-64-channel position guard. |
| [2026-0064: WAV streaming metadata](https://gstreamer.freedesktop.org/security/sa-2026-0064.html) | Selected `wavparse`; the source lacks the `adtl` chunk availability guard. |
| [2026-0081: FFmpeg audio channel mapping](https://gstreamer.freedesktop.org/security/sa-2026-0081.html) | Desktop `avdec_aac` is available; the wrapper source retains unbounded channel-position operations. The default development image lacks this decoder. |
| [2026-0033: ID3v2 parsing](https://gstreamer.freedesktop.org/security/sa-2026-0033.html) | The accepted ID3/audio path reaches native tag parsing; the reviewed source retains affected parsing contexts. |
| [2026-0032: XMP tags](https://gstreamer.freedesktop.org/security/sa-2026-0032.html) | Audio MP4 metadata can reach the XMP parser through `qtdemux`; the source retains the affected contexts. |
| [2026-0079: MP4 captions](https://gstreamer.freedesktop.org/security/sa-2026-0079.html) | Old code remains. Initial admission rejects non-audio tracks, but complete native container-state reachability is unverified; keep open. |
| [2026-0078: caps comparison](https://gstreamer.freedesktop.org/security/sa-2026-0078.html) | The app owns its caps strings and uses no RTP caps input; indirect native mixed-list reachability remains unresolved. Core source fixes are scoped below. |
| [2026-0028: buffer deserialization](https://gstreamer.freedesktop.org/security/sa-2026-0028.html) | The app builds its own pipeline strings and uses no RTP caps input; full indirect core reachability/backports remain unverified. |

**2026-10-22 scoped reassessment — Opus only:** the matching Fedora 44
[`gstreamer1-plugins-base-1.28.8-1.fc44` source package](https://kojipkgs.fedoraproject.org/packages/gstreamer1-plugins-base/1.28.8/1.fc44/src/gstreamer1-plugins-base-1.28.8-1.fc44.src.rpm)
contains the exact [upstream channel-position guard](https://gitlab.freedesktop.org/gstreamer/gstreamer/-/commit/178ae5ac20db75e56d65e4c4bc142bb234387807.patch),
and its build recipe applies no patch to that decoder. The GNOME 50 test image's
`opusdec` is owned by that RPM build: classify this advisory as vendor-fixed at
matching-source scope. The GNOME 49/Fedora 43 image still selects the reviewed
`1.26.11-1.fc43` build with the affected source. This is not binary reproducibility,
exploit testing, a fresh complete advisory scan, or clearance of other findings.
GNOME version alone does not establish the desktop's native-library patch status.

**2026-10-22 scoped reassessment — WAV only:** the matching Fedora 44
[`gstreamer1-plugins-good-1.28.8-1.fc44` source package](https://kojipkgs.fedoraproject.org/packages/gstreamer1-plugins-good/1.28.8/1.fc44/src/gstreamer1-plugins-good-1.28.8-1.fc44.src.rpm)
contains the exact [upstream streaming availability check](https://gitlab.freedesktop.org/gstreamer/gstreamer/-/commit/010db8a2246e00796b1ae7002fa43264898083c3.patch),
with no recipe patches. The GNOME 50 image's `wavparse` belongs to that build:
classify this advisory as vendor-fixed at matching-source scope. Fedora 43's
`1.26.11-1.fc43` still lacks the check. Accepted WAV headers can be followed by
unchecked metadata chunks on a nonseekable response; initial format admission
does not prevent the native crash. No crash payload, binary reproducibility or
complete advisory scan was performed; other publication blockers remain open.

**2026-10-22 scoped reassessment — FFmpeg wrapper:** neither original Shell image has
`gst-libav`, any permitted `avdec_*` fallback, or an eligible AAC decoder. The
wrapper path is absent in those snapshots; successful AAC decoding remains untested.
The official Fedora 44
[`gstreamer1-plugin-libav-1.28.8-1.fc44` source package](https://kojipkgs.fedoraproject.org/packages/gstreamer1-plugin-libav/1.28.8/1.fc44/src/gstreamer1-plugin-libav-1.28.8-1.fc44.src.rpm)
contains the reviewed [upstream decoder/mapping fixes](https://gitlab.freedesktop.org/gstreamer/gstreamer/-/merge_requests/12439.patch),
was initially inspected only; the later AAC profile below installs/tests it.
The earlier desktop's affected
`1.26.11` wrapper and RPM Fusion codec coverage remain open. Updating FFmpeg alone
does not fix the adapter; checking the adapter does not clear its loaded FFmpeg
library. Verify both layers before testing a separately agreed codec profile.

**2026-10-22 AAC profile verification:** a separate Fedora 44 image now installs
that exact `gstreamer1-plugin-libav-1.28.8-1.fc44` build and loads Fedora's
`libavcodec-free-8.1.3-1.fc44`. Real generated ADTS AAC and AAC-in-M4A fixtures pass
the service/control tests. The exact-image vendor query returns no outstanding
advisories or reported repository coverage gaps within its automated scope;
`release_approved` remains false. [FFmpeg's security notices](https://ffmpeg.org/security.html)
were consulted; neither that list nor an empty vendor result attests every native
operation. The earlier wrapper-source evidence applies to this matching build;
it is not blanket FFmpeg clearance. Original images and host packages are unchanged.
Other AAC backends, ADIF, historical RPM Fusion coverage and physical acceptance
remain separate; see the [repeatable profile](DEVELOPMENT.md#optional-aac-test-profile).

**2026-10-22 scoped reassessment — ID3v2:** both images' `id3demux` loads
`libgsttag` from the matching Base RPM. Fedora 44's reviewed `1.28.8-1.fc44`
source contains the [upstream ID3 fixes](https://gitlab.freedesktop.org/gstreamer/gstreamer/-/merge_requests/11794.patch):
initialized peak state, the RVA2 remaining-byte check, and local-copy custom-frame
sanitization. Classify this advisory as vendor-fixed at matching-source scope for
that profile; Fedora 43's `1.26.11-1.fc43` retains the affected contexts. The total
ID3 size limit does not validate individual frames. This is source and loaded-library
ownership evidence, without hostile-tag tests or binary reproducibility; other
findings remain open. The advisory describes a very-low-impact read and custom-tag
data corruption, not an established code-execution result.

**2026-10-22 scoped reassessment — XMP:** the MP4 UUID metadata path in
`qtdemux` can call Base's XMP parser without a video track. Both images map the
matching Base tag library. Fedora 44's `1.28.8-1.fc44` source contains all four
[upstream fix contexts](https://gitlab.freedesktop.org/gstreamer/gstreamer/-/merge_requests/11793.patch),
including the input boundary and temporary-string termination changes; classify
this advisory as vendor-fixed at matching-source scope. Fedora 43's
`1.26.11-1.fc43` retains all four old contexts. The native call path was rechecked
from exact archive members after finding an older source/test filename collision.
No malformed XMP, exploit or binary-reproducibility test was performed; other
publication findings remain open.

**2026-10-22 scoped reassessment — MP4 captions:** exact native source members
reconfirm all four old contexts in Fedora 43 Good `1.26.11-1.fc43` and all four
[fixed contexts](https://gitlab.freedesktop.org/gstreamer/gstreamer/-/merge_requests/12433.patch)
in the installed Fedora 44 `1.28.8-1.fc44` parser's matching source. Classify the
newer profile as vendor-fixed at matching-source scope. Keep the older profile
**unknown, fix absent**: the first-header check rejects caption tracks, but native
fragmented-stream handling can parse later `moov` headers beyond that check.
Caption preprocessing can run before downstream output; audio caps alone do not
establish exclusion. A complete admitted caption path was not demonstrated, and
no malformed sample was decoded. This review does not clear other findings.

**2026-10-22 scoped reassessment — caps comparison:** the loaded core libraries
map to the exact Fedora 43 `gstreamer1-1.26.11-1.fc43` and Fedora 44
[`gstreamer1-1.28.8-1.fc44` source packages](https://kojipkgs.fedoraproject.org/packages/gstreamer1/1.28.8/1.fc44/src/gstreamer1-1.28.8-1.fc44.src.rpm).
The newer comparator has the three critical fix contexts and checks each pair's
type; its source matches the official upstream 1.28.8 release. Classify that
comparison crash as vendor-fixed at matching-source scope. The older source
lacks the fix; admitted-media reachability stays unknown despite the absent
RTSP/RTP route. Not every additional parser-hardening change in the linked patch
series is present in 1.28.8; this is a scoped comparison-fix decision. Only a benign
owned caps comparison was run, without mixed-type crash inputs or a full advisory scan.

**2026-10-22 scoped reassessment — buffer deserialization:** the same loaded
core/package identities were rechecked. Fedora 44 `1.28.8-1.fc44` contains the
exact [upstream cleanup fix](https://gitlab.freedesktop.org/gstreamer/gstreamer/-/commit/e3212c8a2c1e762182884d98d0c169adea69de13.patch):
unmap before unref on invalid characters, and release the allocation if mapping
fails. Classify this advisory as vendor-fixed at matching-source scope. Fedora
43 `1.26.11-1.fc43` retains the old order; application reachability stays unknown.
Radiolina does not directly deserialize server-provided buffer strings. A limited
native-source scan does not prove all indirect paths impossible. A fixed, valid
four-byte buffer value parsed successfully in both profiles; malformed input and
the vulnerable error path were not executed. Other publication gates remain open.

**Runtime decision:** use native packages fixing applicable defects or verified
vendor backports, then repeat relevant isolated and target-desktop checks.
The linked upstream notices identify fixes through the `1.28.8` release; a package
version comparison alone cannot attest a distribution build. Do not silently
remove advertised formats, add post-decoder caps as a substitute for an internal
decoder fix, overwrite host libraries, or bundle native libraries in the ZIP.
The selected Opus/WAV paths make the reviewed unpatched older runtime unsuitable
for endorsement. Resolve that baseline; assess unknown cases using the priorities
above rather than making every incomplete trace an unconditional blocker. A green
Fedora query and passing functional tests do not close known native defects.

### Other dependencies and third-party codecs

Component mapping matters: the [nghttp2 notice](https://bugzilla.redhat.com/show_bug.cgi?id=2502788)
concerns the `nghttpx` proxy, which radiolina does not run; loading the HTTP/2 client
library is not that proxy operation. Tracker-module, OCR, WebKit, SQLite FTS and
pip operations are also absent from current runtime workflows. These scoped
exclusions do not certify the desktop or other applications. Broader Bluetooth,
system-service, libevent and OpenSSL findings retain their open assessments.
Use normal vendor maintenance; investigate further for this project when the
chosen backend or new evidence establishes a plausible affected operation.

When an `avdec_*` decoder is selected, inspect the actual loaded `libavcodec`, not
just the GStreamer plugin's package owner. Third-party packages can supply that
library. The reviewed RPM Fusion repositories advertised no `updateinfo`; an empty
advisory query therefore provided no security coverage. Review their exact builds,
upstream fixes and backports manually, using [FFmpeg's security notices](https://ffmpeg.org/security.html)
alongside vendor evidence. A repository's latest available version or a working
AAC stream does not establish that all security fixes are present.

## Future distribution automation

A release preflight can run these commands and retain timestamped JSON as an artifact.
Unresolved findings, incomplete/stale data or changed fingerprints must require
maintainer review rather than automatic approval. Block on unresolved serious
app-path exposures; record the rationale and next action for deferred uncertainties
and distribution-maintenance items. Review upstream notices, vendor fixes and
applicability before final packaging and release approval.
Every report currently has `release_approved: false`: exit `0` alone must never
authorize publication. Scheduled CI queries are possible later; no release workflow,
automatic updates or publication is configured by this checker.
Include upstream advisory IDs without assigned CVEs and native bug-fix releases;
vendor CVE feeds alone missed relevant decoder fixes in this review.

See the [DNF5 advisory reference](https://dnf5.readthedocs.io/en/latest/commands/advisory.8.html)
and [backporting explanation](https://access.redhat.com/security/updates/backporting).
