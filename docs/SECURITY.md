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
