# Provenance review

## Scope and findings (2026-10-20)

Reviewed the tracked source, bundled icons, test fixtures, and generated extension
ZIP against the initial baseline.
The findings below describe that baseline; MIT identifiers and a license file
were subsequently added for publication.

| Material | Findings |
| --- | --- |
| `extension/`, `src/` | No vendored third-party libraries, copied-code notices, or existing author/license headers were identified. Platform APIs are imported from the installed GNOME stack. |
| `extension/icons/*.svg` | Two small vector radio drawings using paths, rectangles, and circles; no embedded images, external resources, or original author/license notices. The initial file-only review could not establish their origin; see the subsequent creation-history review below. |
| `src/service/*.xml` | Compact D-Bus interface declarations, including the standard MPRIS interfaces; no bundled specification prose or implementation. |
| `tests/` | Test audio and image data are generated locally. Panel fixtures use native Shell widgets and do not load another installed extension. |
| Release ZIP | Contains application JavaScript, interface XML, layout CSS, metadata, and the two SVGs. No downloaded station artwork, recorded audio, or platform libraries are bundled. |

UI examples supplied during development describe desired native GNOME behavior;
they do not by themselves establish code or artwork reuse.

## Icon creation history (2026-10-21)

Local development conversation records contain the coding assistant's inline SVG
creation patches for `radio-symbolic.svg` (2026-10-14 11:56:33 UTC) and
`radio-active-symbolic.svg` (13:58:28 UTC). The second adds signal marks to the
first drawing to indicate playback. Both patches match the files in the initial
Git baseline, `f72310f`, and the current files byte for byte after excluding the
MIT license comment added in `ede9b30`.

These records establish that the assistant created the bundled SVG markup during
this project's development. No external artwork source is identified in the
creation records. Detailed conversation evidence remains private; this conclusion
does not depend on assuming that the maintainer drew or remembered the icons.

## Limits and release gate

No copied code or artwork requiring a specific attribution was identified in this
review. Git history alone begins at the baseline; the local conversation records
extend the evidence for the two icons. This establishes their recorded creation
history, not a guarantee of uniqueness or an exhaustive comparison with other
artwork. Earlier origins of unrelated code snippets remain outside this review.

The project's original files are now licensed under [MIT](../LICENSE), with the
same license bundled in the ZIP. This choice does not establish the origin of
unverified material or change upstream licenses. Confirm any known external
sources and retain their required notices before publishing. Do not remove an
actual third-party attribution merely to simplify project documentation.

## Optional VM verification material (2026-10-24)

`scripts/gnome49-vm/` retains Fedora's public release-signing key and signed
`Fedora-Workstation-43-1.6-x86_64-CHECKSUM` as verification data. The key was
obtained from the host's distribution-supplied
`/etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-43-primary`; its pinned fingerprint is
`C6E7F081CF80E13146676E88829B606631645531`. The checksum accompanied the official
Fedora 43 Workstation release download, and its signature is checked against
that key before media preparation. These unmodified upstream verification files
are not project-authored MIT code and are not included in the extension ZIP.
The ISO itself remains ignored and is downloaded only on explicit request.
