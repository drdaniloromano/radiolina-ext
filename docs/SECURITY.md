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
make container-security-check > workspace/security-container.json
```

The desktop check writes `workspace/security-desktop.json`. Add
`CONTAINER_ENGINE=docker` to the container command when using Docker. Reports are
private machine metadata: keep them ignored and review before sharing. Ordinary
tests remain offline; security queries are separate, opt-in tooling.

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

## Repeatable advisory triage

Review one finding at a time; agents must follow this procedure too:

1. **Identify the snapshot.** Retain the original report unchanged. Record its
   timestamp, source/checker/inventory fingerprints, image ID or desktop identity,
   exact package build, advisory/CVE IDs and coverage gaps. Confirm that the
   inspected source and environment still match; otherwise collect a new report.
2. **Verify the defect.** Read primary upstream and distribution notices. Record
   the affected operation, input/configuration prerequisites and vendor fix or
   backport evidence. A version comparison alone cannot establish patch status.
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
   limitations, classification and next action. Mark partial reviews explicitly;
   keep later reassessments as new dated reports referencing the earlier decision.
   Use **affected**, **vendor-fixed**, **justified not-applicable**, or **unknown**.
   Justified not-applicable requires evidence that the vulnerable operation's
   prerequisites cannot occur in the reviewed paths. Missing evidence stays unknown.
5. **Resolve and recheck.** Keep affected/unknown findings and incomplete coverage
   open. Propose package/image updates separately; never update the host or add an
   advisory exclusion silently. After an approved update, rerun inventory and
   relevant contained tests. Reassess previous decisions when source, factory,
   package, image or advisory details change; no permanent CVE allowlist.

Machine-specific findings belong in the private review, not `AGENTS.md` or a
public claim that all installations are safe. Manual decisions do not rewrite the
raw report or turn `release_approved` into an automatic approval. Do not run
exploit samples or resource-exhaustion probes on the maintainer's desktop.

## Review conclusions and resolution guidance

These **2026-10-21 Unreleased** notes describe the reviewed application paths,
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
| [CVE-2026-15712: GOAWAY over-read](https://bugzilla.redhat.com/show_bug.cgi?id=2500132) | Open, conditional on HTTP/2 debug logging. The [upstream patch](https://gitlab.gnome.org/GNOME/libsoup/-/commit/3a6fb56a0cba42d11f5fd1db6dedcc7c2e92757b.patch) identifies the logging prerequisite. Normal dropped debug messages avoid the formatting operation; inherited debug settings can enable it. |
| [CVE-2026-15713: HTTP/2 cleanup](https://access.redhat.com/security/cve/cve-2026-15713) | Unknown/potentially applicable: client HTTP/2 is supported; the precise native cleanup prerequisites and installed fix remain unverified. |
| [CVE-2026-15709: WebSocket deflate](https://access.redhat.com/security/cve/cve-2026-15709), [CVE-2026-15711: control frames](https://bugzilla.redhat.com/show_bug.cgi?id=2500545) | Justified not-applicable: the app establishes no WebSocket connection or upgrade handshake. |
| [CVE-2026-15714: multipart reader](https://access.redhat.com/security/cve/cve-2026-15714) | Justified not-applicable: the app reads the response stream directly and never constructs `Soup.MultipartInputStream` or requests multipart parts. |
| [CVE-2026-77680: Range coalescing](https://access.redhat.com/security/cve/cve-2026-77680), [CVE-2026-77014: Range sorting](https://access.redhat.com/security/cve/cve-2026-77014) | Justified not-applicable: the app runs no `Soup.Server` and never invokes Range parsing APIs. |
| [CVE-2026-12549](https://access.redhat.com/security/cve/cve-2026-12549) | Unknown: the vendor description discusses server Range handling while its statement/mitigation discusses WebSockets. Neither is used here, but the contradictory metadata needs clarification before closure. |

The Range notice also cites CVE-2025-32907 as historical context. Its
[server Range handling](https://access.redhat.com/security/cve/cve-2026-77680)
is outside the same current app paths; this is not an additional new finding.

**Resolution:** use the distribution's supported update process to obtain a
vendor-fixed libsoup build. Fedora identifies `libsoup3-3.6.6-5.fc43` as fixing
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

## Future distribution automation

A release preflight can run these commands, retain timestamped JSON as an artifact,
and block on unresolved findings, incomplete/stale data or changed source/image/package
fingerprints. Then require recorded maintainer review of upstream notices,
backports and applicability before tests, final packaging and release approval.
Every report currently has `release_approved: false`: exit `0` alone must never
authorize publication. Scheduled CI queries are possible later; no release workflow,
automatic updates or publication is configured by this checker.

See the [DNF5 advisory reference](https://dnf5.readthedocs.io/en/latest/commands/advisory.8.html)
and [backporting explanation](https://access.redhat.com/security/updates/backporting).
