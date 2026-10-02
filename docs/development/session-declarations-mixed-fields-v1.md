# Mixed Contenido/PDA fields: source-only v1

Status: frozen synthetic reference before implementation. Base contract:
`session-declarations-contract.md`; base commit `27b2b5850908ba3c088458f5d866077de58b20cf`.
This is an additive, detached experiment. It does not change production,
publication, curricular validation, typed declarations, unit scanning, a scorer,
or any earlier reference. No real corpus, private reference, FINAL reserve,
matcher output or product output was used to author this reference.

## Compatibility and authority

The base contract already allows a challenge to carry one exact `value` span
without a typed claim. The combined label does **not** distinguish contenido
from PDA, even when its value resembles a learning statement, a list, or codes.
Recovering that value is therefore compatible only as additional evidence on an
existing combined-label abstention:

- opt-in `mixed_fields=False` by default; disabled behavior is identical to the
  baseline, including records, evidence, identifiers, units and limits;
- an eligible existing record remains `kind=null`, `decision="abstained"`,
  `reason="combined_label"`, `claim=null`;
- add exactly one page-local `value` SourceReference using existing conventions;
- keep the existing record ID, label and all prior evidence unchanged, and keep
  every other record unchanged, including incidental mentions inside the value;
- preserve its existing `unit` metadata exactly, whether known or null; never
  assign a unit from this recovery, change an anchor, create a unit or a claim;
- a record with an existing value is unchanged, so repeated application cannot
  duplicate value evidence; a missing baseline record is not invented;
- records blocked with other reasons are unchanged. A source-side opportunity
  does not authorize rewriting `quoted`, `conditional`, `negated` or any other
  baseline abstention into `combined_label`.

This is an evidence-only postprocess, not a new extraction or classification
pass. A generic literal such as `Comunicación` is recoverable as an untyped
mixed value when its structural boundaries are explicit. It is never a typed
PDA. `AB7(PDA1,PDA2)` remains that exact string: do not expand codes, infer SEP
identities or split it into declarations. Preserve `*`, `-`, `•`, continuation
lines, repetitions and internal whitespace as one whole value. Lists are not
contenido/PDA partitions. The two typed controls in this reference remain the
responsibility of the existing typed path and are unaffected by this option.

If a safe value or an existing eligible record cannot be established, the
required fallback is the unchanged baseline abstention, not a guessed prefix,
new unit, typed candidate, claim or broader label recognizer. Recovery of these
mixed values must not increase any typed-detection or session-claim numerator
in the existing scorer. A future mixed-field measure needs its own denominator.

## Bounded source grammar

### Label and complete value

The field must start on its own physical line, after optional ordinary spaces,
without prose, a bullet, a quotation marker, table cell or code-fence prefix.
The label is `Contenido` or `Contenidos`, followed by `/` or the word `y`, then
`PDA` or `PDAs`, followed by a required ASCII colon. ASCII case and ordinary
spaces around the separator or before the colon do not change its meaning.
The `(s)` notation here describes alternatives; literal `Contenido(s)/PDA(s)`,
reversed order, long-form combined labels and a missing colon are out of v1.
A label mention in running prose is not a field. These source constraints do
not authorize expanding baseline label recognition.

A value may start after the colon on the same line or on following lines. It
extends to an explicit closing heading on the **same page**, excluding only
external whitespace. A complete sentence or balanced code expression alone is
not evidence of closure. Page end, file end, the next page, a blank line, and
terminal punctuation are never closing headings. Do not award partial recovery
for an unfinished or contaminated block.

The closing heading must occupy a separate physical line. The bounded v1
headings are `Inicio`, `Desarrollo`, `Cierre`, `Actividades`, `Descripción de
actividades`, `Recursos`, `Materiales`, `Evaluación`, and `Observaciones`, with
an optional final colon and ordinary outside spaces. A genuine, standalone
session heading already established by the existing structural path may also
close the preceding block; this option must not recognize additional sessions.
`Inicio:` embedded in a value line does not close it. A closer bounds only the
preceding field and never licenses later fields after an activity has begun.

Reject the entire proposed mixed block if it contains an explicit child label
such as `Contenido:` or `PDA:` (including list-prefixed children), another mixed
label, another metadata field, a table, an activity marker such as `Actividad
1:`, a heading-like unknown separator, or ambiguous quotation/delimiters.
A typed child is not a closer allowing credit for the preceding fragment.
For adjacent mixed labels, neither overlapping field is safely isolated merely
because a later activity heading exists. Do not suppress baseline records of
such children or mentions. Ordinary words inside a literal are not structural
markers: `PDA1` inside a balanced code and `no` in a learning statement do not
by themselves constitute a typed child or a negation of adoption.

### Source context, not unit assignment

Eligible contexts are a clean initial metadata fragment, a clean metadata
continuation, or metadata after a genuine explicit session already recognized
by the existing structural path. `context_reset` in the reference records only
that source-side reset; it is **not** an expected physical unit assignment.
An absolute document-start field with only empty/whitespace prefix, including
preceding blank pages, may supply clean initial context. A blank page is never a
reset for unsafe context that already exists. Initial project metadata may
supply literal context without authorizing project inheritance or a new unit.

Planning rows may precede the mixed label: explicit `Fecha`, `Tiempo`, `Tema de
la sesión`, `Organización`, `Campo`/`Campo formativo`, `Fase`, and `Páginas` labels,
and their clearly attached value lines. A wrapped `Tema de la` / `sesión:` row
remains metadata, not a new session. Plain unknown prose is not assumed to be
metadata. Do not reconstruct tables or silently consume an arbitrary passage as
a multiline metadata continuation.

Entering an activity, moment, table, quotation, example, unadopted proposal,
conditional/negated application or unknown prose blocks recovery in that source
context. A combined heading, `Campo`, `DATOS GENERALES`, page break, or a fake
session heading inside an open quote cannot clear that state. A genuine new
session may reset earlier activity/example context only when outside quotations
and other unresolved containers. A previously closed quotation followed by a
real session can be safe; an inherited or mismatched quotation remains unsafe.
The supplied page window carries these blockers across page boundaries.

A complete field on a later page is distinct from a field split across pages:
clean metadata continuation can be recovered without inferring that it belongs
to the preceding session. Any baseline unit metadata remains exactly unchanged.

### Exact text and bounds

Offsets index original Python Unicode strings, end-exclusive. No byte offsets,
normalization, whitespace folding or newline conversion is allowed. Label
includes its colon; value excludes external whitespace only. CRLF, NFC/NFD,
accents and emoji inside the accepted span must survive byte-for-byte in its
UTF-8 serialization. Repeated physical fields retain distinct source offsets
and existing record IDs despite equal text.

A value has at most 2,048 Unicode codepoints and 32 nonempty physical lines;
line counting treats CRLF as one newline. Both limits are inclusive. Over-limit
fields are rejected whole, never truncated. Empty values are rejected. LF and
paired CRLF are the only permitted line breaks. A tab, bare CR, other C0/C1
control, Unicode format control (including bidi/zero-width controls), U+2028 or
U+2029 in the candidate field is unsafe. Never sanitize such input into a match.
These added guards may withhold evidence, but may not erase or alter the base
record or any base limits.

## Frozen source and independent reference

File: `tests/fixtures/interpretation/session_declarations_mixed_fields_v1.json`.
SHA256 of the exact fixture bytes:
`cffc43ca220904ebf38e50b9be8e83a919f1beaeae01cbea07c124508256dc8b`.

Source-only digest, computed over UTF-8 JSON of ordered `[{id, pages}, ...]`
with `ensure_ascii=False, separators=(",", ":")`:
`570b412ecaed11e286349526a405bcfd68d0a3e546f79c08026bae6e8f95c297`.
Sources were written before their annotations: 68 initial documents, then two
supplemental sources for a compositional activity heading and an inline false
closer, each saved before its expected spans. The final 70 original page arrays
are immutable. Expected spans were authored from literal source strings, never
from a matcher, prediction adapter, scorer, or product output.

The fixed denominators are 70 documents, 24 complete mixed-value recovery
opportunities, 48 rejected mixed-field challenges and 2 typed controls. A
single document may contain both a recoverable field and a rejection. Repeated
fields count separately; document counts are not added to opportunity counts.
These are source-side expectations, conditional on an already eligible baseline
record. A baseline miss remains an omission, not permission to invent a record.

Required shape:

```text
{version, reference_kind, source_first_sha256, source_freeze_stage,
 default_mixed_fields: false, enabled_patch_contract, counts,
 documents: [{id, tags, pages,
   expected_recoveries: [{id, label: Span, value: Span,
     closing_heading: Span, context, context_reset: Span|null}],
   expected_rejections: [{id, anchor: Span, category,
     expected_effect: "no_value_added"}],
   typed_controls: [{kind: "contenido"|"pda", label: Span, value: Span,
     expected_effect: "unchanged_by_mixed_fields"}]}]}
Span = {page: one-based integer, start: integer, end: integer, quote: string}
```

Rejection `category` explains the source-side safety challenge; it is **not** a
replacement prediction `reason`. An anchor identifies the exact challenged text
and need not satisfy the accepted standalone-label grammar. No expected unit ID,
new claim, curriculum identity or inferred contenido/PDA split exists here.

`tests/test_session_declarations_mixed_fields_reference.py` validates source
hashes, exact spans, schema, bounds, distinct occurrences, coverage and invariants
using only the Python standard library. It neither imports nor runs the matcher,
product scanner, scorer, existing fixture suite, corpus, or prediction outputs.
Run in isolation with:

```sh
python tests/test_session_declarations_mixed_fields_reference.py
```

Passing this reference-integrity suite validates the frozen annotations only.
It is not implementation verification, measured recovery performance, OCR
validation, teacher validation or a production-readiness result. After this
freeze, implementation tests should verify the additive patch and preservation
against the exact baseline, and report omissions separately from wrong values.
