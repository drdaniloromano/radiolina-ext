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
   `workspace/`, including reviewer, report reference, identities above, source
   links, commands/results, reasoning, limitations, classification and next action.
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
