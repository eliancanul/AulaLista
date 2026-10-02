# Explicit PDA after a dotted local descriptor: opt-in development contract

This is a detached literal-recovery experiment against base
`27b2b5850908ba3c088458f5d866077de58b20cf`. Default extraction, production,
the scorer, frozen prior references and unit-scaffold grammar stay unchanged.
The known development observation is a fully typed PDA after `CODE. description`;
the descriptor supplies textual context only. It is never a Contenido declaration,
a catalogue identity, evidence of field membership or a unit anchor.

## Source-first admission

A clean page-local metadata region begins with an existing canonical campo name.
An already recognized explicit same-page unit may restart such a region; a campo,
DATOS GENERALES, descriptor or empty project heading cannot erase unknown prose,
activities, examples, quotation or nonadoption. Open source quotation and active
example/nonadoption context are checked against supplied preceding pages, without
inheriting a field or assigning a unit across pages.

A descriptor is one Spanish-alphabet local code (the existing 1–4 letters plus
1–4 ASCII digits grammar), a literal dot, horizontal whitespace and a nonempty
complete description on at most eight physical lines. It ends with sentence
punctuation and is immediately corroborated by a complete numbered PDA label on
the next nonblank line. A descriptor's code need not match the PDA code: neither
is an identity relation. One formatting hyphen and horizontal indentation may
precede the PDA label; no other bullet, unknown prefix or normalization is used.
Ordinary inline colons in the descriptor do not create a field. Typed labels,
activity/example/nonadoption markers, quotes, table pipes and vertical/control
characters make the descriptor ineligible. Completed description followed by
additional loose prose cannot be silently absorbed as wrapping.

A subsequent descriptor or campo is a boundary only after the previous value is
already complete and the following descriptor/PDA block corroborates it. Campo
transitions may use the canonical name, wrapped across at most three physical
lines, or replace one interior word by its first letter followed by a dot while
retaining the first and last words. This compositional textual signal does not
create a field alias or classify any declaration. An abbreviation alone cannot
start a region. Original spelling, punctuation, whitespace, accents and offsets
are retained in every reference. Unfinished previous values stay uncertain and
block recovery beyond them, rather than being cropped at the new descriptor.

Values remain full original page-local slices. Every recovered record was already
an explicit complete typed PDA label in the legacy output, but had no value. The
new route only adds a literal value to eligible `label_mention` records. It does
not replace any prior value, resolve any other ambiguity, emit a new descriptor
record or change existing claims. New records remain `pda`,
`abstained/unresolved_scope`, `unit=null`, `claim=null`, even beside a session or
project. Unit decisions are deliberately separate and require another validated
stage.

## API and evidence

`extract_declarations(..., pda_context=False)` is default-compatible.
`pda_context=True` adds a source-backed `pda_context` sidecar: method version,
record ID, full label/value hashes, exact descriptor/field/boundary witnesses.
Only primary label/value references enter declaration evidence; textual context
is never misrepresented as a unit proof. The CLI opt-in is `--pda-context`.

The source-only structural scan does not consume references, document IDs, source
names or expected answer spans. No external model/provider calls are needed.
The existing scope-audit replay channel must not silently treat the new source
state as an old group; this cut does not claim transport or semantic validation
of a new scope.

## Evaluation

Synthetic source and expected spans are independently authored and frozen before
implementation. Adversaries cover ambiguous predecessor values, malformed codes,
control/vertical separators, unknown prefixes, quotations, activities, examples,
nonadoption, field/reset spoofing, page boundaries and wrong-type promotion.

Private exposed-development comparison reuses exact pages 1–6 and frozen
`reference_frozen_v1.json` (36) and `reference_frozen_v2.json` (35), with their
original hashes and unchanged scorer. Literal recall, whole-value precision,
unit assignment, joint detection/unit and safety are reported separately. Exact
literal recovery cannot be advertised as reliable global interpretation, semantic
validation, SEP alignment, unseen performance or reaching a global 90% target.
No FINAL/holdout source or prediction is used; no publication or merge is made.
