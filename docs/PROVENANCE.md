# Provenance review

## Scope and findings (2026-10-20)

Reviewed the tracked source, bundled icons, test fixtures, and generated extension
ZIP against the initial baseline.

| Material | Findings |
| --- | --- |
| `extension/`, `src/` | No vendored third-party libraries, copied-code notices, or existing author/license headers were identified. Platform APIs are imported from the installed GNOME stack. |
| `extension/icons/*.svg` | Two small vector radio drawings using paths, rectangles, and circles; no embedded images, external resources, or author/license notices. Their upstream origin cannot be established from the files alone. |
| `src/service/*.xml` | Compact D-Bus interface declarations, including the standard MPRIS interfaces; no bundled specification prose or implementation. |
| `tests/` | Test audio and image data are generated locally. Panel fixtures use native Shell widgets and do not load another installed extension. |
| Release ZIP | Contains application JavaScript, interface XML, layout CSS, metadata, and the two SVGs. No downloaded station artwork, recorded audio, or platform libraries are bundled. |

UI examples supplied during development describe desired native GNOME behavior;
they do not by themselves establish code or artwork reuse.

## Limits and release gate

No copied code or artwork requiring a specific attribution was identified in this
review. This is a repository inspection, not proof of original authorship: Git
history begins at the baseline and cannot trace earlier snippets or drawings.

The project license remains undecided. Before publishing, confirm any known
external sources, retain their required notices, choose a compatible project
license, and include it in both the repository and ZIP. Do not remove an actual
third-party attribution merely to simplify project documentation.
