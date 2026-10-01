# Experimental literal session declarations: v1

This is a detached, offline research contract. The production interpreter,
dossier, UI, Atlas, tribunal and editorial gates are not changed or invoked by
this experiment. `contenido_declarado` and `pda_declarado` are distinct proposed
field predicates, not aliases for `tema` or `objetivo`. They assert only what a
source labels inside a physical session. They never establish a SEP catalogue
identity, curricular alignment, pedagogical truth or publication authority.

## Freeze and reference

The first reference is authored before the experimental matcher. It contains 36
synthetic documents, 45 literal declaration opportunities (36 session candidates
and 9 project/unresolved scope abstentions), 22 non-declaration/ambiguous-label
challenges and 15 documents without affirmative declarations (2 without challenges). These denominators are separate.
The primary activity/session and activity/annex fixtures remain unchanged.

`tests/fixtures/interpretation/session_declarations_v1.json` SHA256:
`3c7a9aedf5be30b8755d12e6567d154b5d54859d1ff0a868727b8576060201f5`.

Reference shape (all keys required):

```text
{version: "session-declarations-reference.v1", reference_kind, scope,
 documents: [{id, pages: [original page string],
   units: [{id, kind: "session"|"project", anchor: Span}],
   declarations: [{id, kind: "contenido"|"pda", label: Span, value: Span,
     unit_id: string|null, expected_decision: "candidate"|"abstained", reason}],
   challenges: [{id, anchor: Span, reason}], absence_expected: boolean}]}
Span = {page: one-based integer, start: integer, end: integer, quote: string}
```

Offsets index the original Python/Unicode string, not UTF-8 bytes or normalized
text. End is exclusive. Every quote must equal the original slice; CRLF, accented
characters, emoji and internal whitespace are preserved. Label excludes preceding
indentation and following space/newline; it includes its colon when present.
Value excludes only external whitespace, never internal lines. Each distinct
physical labelled block is one opportunity, even if its text repeats exactly.
A multi-item list under one label remains one block; multiple labelled blocks
in one session produce multiple opportunities. No singular cardinality is assumed.

The v1 `value` is one **page-local** span. Multi-line and CRLF blocks on a page are
supported; an unfinished block at a page boundary must abstain. It must not be
silently joined to a later page or awarded partial detection credit. A unit anchor may be on a previous page only when explicit, unambiguous physical
continuation within the supplied window proves identity and no new session,
project or reset intervenes. The initial matcher may conservatively support
only an explicit continuation heading naming the unique preceding session;
continuation evidence uses role `unit_continuation`. A complete declaration
on a page with uncertain continuation must abstain with `unresolved_scope`.

`units` are authored reference identities, not product IDs or matcher output.
`unit_id: null` means the declaration has no safely assigned physical unit.
`absence_expected` is true if and only if `declarations` is empty. It can coexist
with ambiguous/combined-label challenges and does not mean curricular information
is physically absent.

Project declarations are positive detection opportunities but **never** inherited
by sessions. Their records must be explicit abstentions from a session claim.

## Detached prediction contract

```text
{version: "session-declarations.v1", source_doc_sha256, extraction_sha256,
 records: [{id, kind: "contenido"|"pda"|null,
   decision: "candidate"|"abstained", reason,
   unit: {id, kind: "session"|"project", anchor: SourceReference}|null,
   evidence: [SourceReference], claim: AtomicClaim|null}], limits: [string]}
```

Only `candidate` records with a literal, affirmative, typed declaration and an
explicit session scope have an `AtomicClaim`. Its existing `claim_type` is
`field`, subject is the physical session identity, predicate is exactly one of
the two proposed predicates, and object is the complete literal value. State is
always `needs_human_review`, confidence is null. No experimental state is a
curricular accuracy result. `abstained` records have `claim: null`; a known literal
kind/value may remain in their evidence, without asserting the session relation.

Each `SourceReference` uses the existing convention
`region={kind: "text_offsets", start, end}` and roles `label`, `value`, or
`unit_anchor`, or `unit_continuation`. These are text offsets, never invented geometric coordinates.
Label and value evidence each contain exactly one span where available. A
challenge has a label span and may omit value evidence. A unit anchor is retained
in both the unit and candidate claim evidence. Every reference retains source
document hash, physical page, and exact quote. IDs incorporate physical offsets,
not merely the lexical value, so repeated declarations cannot collapse.

`source_doc_sha256` is a caller-supplied document binding, not proof that this
experiment read the PDF. `extraction_sha256` is SHA256 of UTF-8 JSON of the exact
page array with `ensure_ascii=False, separators=(",", ":")`. Synthetic evaluation
uses that text-snapshot hash as its source binding and labels it accordingly;
it must never be described as an original PDF-byte hash.

## Decisions and conservative boundaries

Candidates require standalone explicit singular/plural or long-form labels;
prose merely discussing a label is not a declaration. Support includes
`Contenido(s)`, `Contenido(s) curricular(es)`, `PDA(s)` and
`Proceso(s) de desarrollo de aprendizaje(s)` with optional `(PDA)`.
Bare standalone labels may introduce a following block. Inline prose, incomplete
quotes, combined `Contenidos/PDA`, shared or flattened tables, empty blocks,
negated application, conditional application and suggestions not adopted abstain. A negative word inside
the learning text does not alone negate its declaration (for example, explaining
why water should not be wasted).

The first version does not reconstruct tables, resolve cross references such as
"same PDA as session 1", split lists into SEP entities, infer objectives from
activities, or propagate project metadata. Unknown continuation after a completed
sentence can be an uncertain boundary; retain an explicit abstention instead of
contaminating a value. This is a bounded Spanish textual grammar, not general
discourse understanding. Reasons used by this reference are `explicit_session`,
`project_scope`, `unresolved_scope`, `combined_label`, `table_ambiguous`, `negated`,
`label_mention`, `quoted`, `conditional`, `nonaffirmative`, `empty_value`,
`uncertain_boundary`.

## Independent evaluation

The evaluator consumes original pages, manually authored spans and detached
predictions. It must not import the matcher or product scanner in its scoring or
reference-validation functions. A separately invoked prediction adapter may call
the experiment. Exact type/label/value matching measures literal detection;
one-token excerpts, contaminated values, wrong spans and wrong types cannot earn
full detection credit. Physical unit-anchor matching is a separate measurement.
Repeated guesses for the same opportunity make it incorrect; extras remain visible.

Report at least these separate denominators and outcomes:

1. Literal declarations: detected exactly / fixed 45, incorrect, omitted,
   extras, duplicates, and precision over emitted typed-value records. A
   correctly detected project declaration earns detection credit even though
   its session claim is withheld.
2. Unit assignment: correct exact session/project anchor (or explicit unresolved
   null where referenced) / the same fixed 45; joint detection + unit assignment
   must also be reported. Scope correctness alone is not literal detection.
3. Session-candidate decision: correct / fixed 36; explicit abstentions,
   incorrect decisions and omissions remain separate.
4. Scope abstention: correct explicit abstained records / fixed 9. Silence is an
   omission of detection and is never counted as abstention.
5. Challenges: fixed 22; correct explicit abstention, silence/no-claim, wrong
   candidate, duplicate or invalid record are separate. Silence can correctly
   avoid a false claim, but does not demonstrate an explicit abstention.
6. Documents without affirmative declarations: fixed 15, with false candidate
   emissions, explicit abstentions and clean silence reported separately. Two
   documents also have no challenges and should produce no records. Negative
   document counts are never added to a positive-recall numerator.

An abstention requires an explicit `abstained` record with exact identifying
evidence. `needs_human_review` is governance, not abstention and not an accuracy
criterion. Missing/zero denominators are N/A. Hash mismatches, fabricated quotes,
invalid states or claim/evidence contradictions are invalid outputs, never
silently corrected. No result establishes global reliability, teacher validation,
performance on private/final-reserve material, OCR accuracy or real API cost.
