# Mixed fields: split metadata supplement v1

Status: frozen, source-only synthetic supplement to
`session-declarations-mixed-fields-v1.md`. The existing 70-document reference
and its expectations are unchanged. No runtime, matcher, scorer, product output,
private corpus or FINAL reserve was read to author this supplement. Reading the
base source fixture only established its schema and source-span conventions.

## Narrow interpretation

This supplement interprets planning metadata already allowed by the base
contract. It does not recognize sessions, add labels, or assign scope. Its
positive annotations are opportunities to add one literal `value` span to an
already eligible `combined_label` abstention, conditional on that record existing.
The default remains disabled. IDs, prior evidence, `unit`, anchors, `kind=null`,
`decision="abstained"`, `reason="combined_label"`, and `claim=null` are preserved.
Other abstention reasons and all other records remain unchanged. There is no
new typed declaration, session claim, curriculum identity, code expansion or
mixed-value scoring credit in the typed numerator.

Two arrangements may supply clean metadata context:

1. A genuine dated session heading **already established by the existing
   structural path** has the form illustrated by
   `Sesión 1 Fecha: Martes 8 Tema de la`. Its final literal `Tema de la` begins a
   known metadata label; the immediately following physical line `sesión:`
   completes it. A thematic value follows, then known `Tiempo` and `Campo`
   metadata, then a separately closed mixed field. The exact suffix follows the
   dated heading with ordinary spaces, without an intervening title, unknown
   label, or additional suffix text. `Tema de la vida`, `Título: Tema de la`,
   and `Asunto de la` do not qualify. An arbitrary line containing `sesión`
   does not become a session or a valid label continuation.
2. A known metadata row can read
   `Fecha: 4 de octubre de 2026 Tema de la`, followed by `sesión:`, then
   `Tema largo`, then `con continuación. Tiempo: 35 minutos` on separate lines.
   The final line contains the end of the thematic value and a new, known
   `Tiempo:` label. Both are metadata; do not treat the thematic prefix as
   unknown prose merely because `Tiempo:` starts later on the same line.
   This bounded inline transition does not admit an unknown colon label such
   as `Duración:`. Existing standalone known metadata labels keep their prior
   treatment; the supplement does not whitelist new labels.

The `sesión:` continuation requires its ASCII colon and completes the literal
`Tema de la sesión` label only. Neither `sesión` without a colon nor
`sesión 24:` completes it. An attached, multiline thematic value does not
license consuming arbitrary prose as metadata.

Interpretation can inspect metadata that begins **inside** the full existing
anchor and finishes after its boundary. It must never implement this by
truncating, replacing, splitting or moving the original anchor or its reset
span. In this reference, a dated `context_reset` includes the entire physical
heading through `Tema de la`, excluding only outside ordinary spaces. The
following `sesión:` is never an additional reset, session, or unit. The reset
annotation describes a source-side context opportunity, not an expected unit
assignment; a null baseline unit stays null.

ASCII spaces are the only structural horizontal whitespace; LF and paired
CRLF are the only line breaks. These restrictions cover the entire metadata
admission path, including the suffix inside the anchor, the split label, theme
continuations and inline metadata transition. Tabs, bare CR, C0/C1 controls,
Unicode format controls, U+2028/U+2029 and non-ASCII structural whitespace are
unsafe. Never remove a control or normalize source text to manufacture an
admission. Ordinary accented letters, combining accents and emoji in literal
text remain exact. All offsets index original Python Unicode strings,
end-exclusive; no byte offsets or newline conversion.

Metadata is not a context reset. Activity or unadopted-example context remains
blocked unless a genuine new session is already established outside unresolved
containers. A heading inside an open quotation cannot reset anything. A closed
quotation followed by a genuine session can be safe. No positive admission
relaxes the base mixed-field grammar, same-page explicit closure, complete-value
requirement, 2,048-codepoint/32-nonempty-line limits, or contamination guards.
A valid metadata prefix cannot rescue an unclosed mixed field. Rejection always
means no additional evidence, never deletion of a baseline record or anchor.

## Freeze and independent integrity check

Fixture: `tests/fixtures/interpretation/session_declarations_mixed_metadata_supplement_v1.json`.
The 24 page arrays were saved without any annotations, then frozen, then
annotated using only their literal source strings. A preliminary unannotated
heading spelling was corrected to the requested `Sesión N Fecha: weekday day`
form before this final freeze; no expectation was authored against that draft.
The final source arrays are immutable.

- Source-only SHA256 over ordered `[{id, pages}, ...]`, UTF-8 JSON with
  `ensure_ascii=False, separators=(",", ":")`:
  `8fbe9730c40cf4a5896fb3062f0ccf6526272b4458ab0c95625b6b3740da843b`
- Exact saved unannotated fixture SHA256:
  `1532d4a098934b3db425f5861b819cca8c21fdbb44ed4010e97db5a19f28f84e`
- Exact final annotated fixture SHA256:
  `ff93882fc51e2fc1e7e30be1aa693ec7bf069ccae013713159cf0b0b1b9b5083`

Fixed denominators: **24 documents, 8 literal recovery opportunities,
16 rejected challenges, 0 typed controls**. Each document has exactly one
opportunity or challenge. The base fixture schema is retained; the only extra
top-level field is `source_unannotated_fixture_sha256`, which authenticates the
source-only saved stage. `context_reset` is either the complete source reset or
null. Rejection categories describe source safety, not new runtime reasons.
There are no expected unit IDs, scope assignments or typed claims.

Run the standalone standard-library test:

```sh
python tests/test_session_declarations_mixed_metadata_supplement_reference.py
```

It verifies source-first and final hashes, the reconstructible pre-annotation
snapshot, unchanged base fixture bytes, exact spans, schema, complete values,
full dated reset spans, metadata boundaries, limits and positive/negative
coverage. It does not import or run a matcher, runtime, scorer, corpus or other
fixture test suite. Passing demonstrates reference integrity only, not measured
implementation performance, teacher validation or production readiness.
