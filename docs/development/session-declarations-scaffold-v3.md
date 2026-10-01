# Marker metadata and proposed session scaffolds: matcher v3

This is a bounded development extension of frozen commit
`8093752777fefdcd62bce89f54f8fb8c039cb910`, whose full suite passed with 1977
tests and 10 skips. The earlier `420334b` cut and its receipts also remain
preserved. The source/output envelope remains `session-declarations.v1`.
No production schema, dossier, scanner, provider, editorial gate or SEP identity
is added or changed. Existing synthetic fixtures and earlier outputs remain intact.

## A hyphen is formatting, not part of the label

A single leading `-` may introduce a complete typed declaration label ending
with `:` in the session's metadata block, before any Inicio/Desarrollo/Cierre
moment. The literal `label` span starts at the local code, PDA, or Contenido and
excludes the formatting marker and surrounding indentation. It still includes
the complete local code/number and colon. The span is a direct original slice,
never a reconstructed or normalized quotation.

This does not admit arbitrary activity bullets. A prose prefix such as `-Leer`,
a quoted or explicitly headed example, an incomplete label, and a bullet after
the first lesson moment continue to abstain. Existing negation, nonadoption,
combined/table ambiguity, truncation and source-boundary guards remain active.

## Structural scaffold admission is a proposal

The matcher may propose a session unit on the immediately preceding page only
when all of these guards hold:

1. The existing product scanner already admits the declaration page as a literal
   continuation of exactly one SessionSegment; the whole label and value are
   contained in that admitted prefix. This is a prerequisite, not independent
   proof of correctness, and no scanner admission is broadened.
2. That session's explicit anchor is the only session anchor on the preceding
   page and is its final unit. Earlier project context is allowed; a later
   project, session or reset is not. Multiple potential parents block admission.
3. From that anchor onward there is no lesson moment or actual activity. Its
   remaining tail is empty or contains only complete, explicitly labelled
   Fecha, Tiempo/Duración, Tema de la sesión, Organización or Campo(s) metadata.
   A hyphen before one of these metadata rows is formatting. Empty/truncated
   metadata, free prose, activity bullets and open quotes block admission.
4. The new page begins with explicit declaration/metadata structure. There is
   no display-heading exception in this bounded version. Its first explicit
   lesson moment must be `Inicio`; that moment must exist on this page. An
   earlier `Desarrollo` or `Cierre`, or no moment at all, blocks structural
   scope. The complete declaration is before that first `Inicio`. Loose initial
   text, an unlabelled sentence after a completed value, actual activity bullets,
   a new unit/project/reset, unresolved quotation or another possible scope
   block it.
5. Values remain page-local. In particular, `Contenido: Formas y` on the prior
   page followed by `colores.` is still truncated/ambiguous and cannot establish
   this scaffold or become a recovered declaration.

Unknown layouts retain `unresolved_scope`. No project scope is propagated across
pages. A lesson already developed before the page break is excluded from this
new route; its existing explicit `Continuación de la sesión N` route is unchanged.
Physical proximity alone never admits a unit.

For this bounded proof grammar, each planning-metadata row must fit on one
physical line and contain a nonempty value; implicit wrapping is not admitted.
An ending `y/e/o/u/de/del/para/con/en/a`, comma, semicolon, colon or dash is treated
as potentially truncated. Quote pairs `"..."`, `«...»` and `“...”` must be
balanced; an open quote entering or leaving the scaffold blocks admission.
Curricular values may wrap within one page only as continuation of an already
labelled open block. A new unlabelled sentence after terminal punctuation,
unknown heading, activity bullet, moment, unit or reset is not silently absorbed.
These guards are checked from source strings, not by using gold value spans to
discover or repair context.

## Distinct metadata and literal proof roles

Candidate claim metadata separates literal declaration evidence from unit scope:

- `unit_scope_basis: same_page_explicit` for a same-page unit
- `unit_scope_basis: explicit_continuation` for the existing named continuation
- `unit_scope_basis: structural_scaffold_proposal` for this new proposed join

`metadata.basis: explicit` still describes the labelled declaration itself. It
does not upgrade a structural join to an explicit continuation. Every candidate
remains `needs_human_review`, with `confidence: null` and no editorial authority.
The basis is stored in `claim.metadata.unit_scope_basis`; no new top-level
record field is required. It must agree with the physical unit location and
proof roles. `same_page_explicit` cannot describe a previous-page anchor, and
`explicit_continuation` cannot stand in for a structural proposal.

The structural route must retain exactly one `SourceReference` for each new role:

- `unit_scaffold_tail`: previous physical page, from the original unit anchor's
  start through the exact end of that page, including the anchor and tail
- `unit_scaffold_prefix`: declaration page, from offset 0 up to the physical start
  of the first Inicio heading, including original whitespace and line endings

Both use the existing `region={kind: text_offsets, start, end}` convention, source
hash and exact quote. Label and full value must lie within the second proof span.
The unit anchor remains separate. Record and AtomicClaim evidence must agree.
`unit_continuation` is reserved for a real named continuation phrase and cannot
be reused as a label for these structural proofs.

Legacy outputs without `unit_scope_basis` retain their previous checks on
legacy references. They cannot opt into a structural scaffold merely by supplying
the new roles. Every candidate opportunity pinned by the new pre-output supplement
requires its exact basis regardless of the implementation version claimed by the
output. Missing or contradictory basis, missing/duplicate/cropped/altered proof,
`unit_continuation` substituted for a scaffold, or differing record/claim proof
evidence invalidates unit/joint/strict claim credit. Otherwise exact literal
detection remains separately credited. Source errors in the label or value
itself still invalidate literal detection as before. A proof must cover the
whole prescribed tail/prefix, not just enclose the declaration or match a
convenient subset. Record and claim proof references must match role, document
hash, page, offsets and exact excerpt; evidence ordering alone is immaterial.

## Independent evaluation and limits

Scorer v1.3 independently checks the literal proof ranges and these guard
conditions against the supplied original page strings. It does not import the
product scanner, matcher or an admission flag supplied by either. Fixed gold
anchors still determine whether the proposed physical association is correct.
Neither structural admission nor human-review state earns curricular truth.

The additional fixture is authored and frozen before matcher implementation,
without running the matcher or scanner. Its source strings are synthetic and
its patterns are already-exposed development hypotheses, not a held-out test.
Keep this stratum separate from earlier fixtures and from any separately
authorized private development comparison. No 90% global reliability, SEP
alignment, pedagogical validation or teacher time savings is implied.

## Pre-output supplement and fixed expectations

The archived `session_declarations_scaffold_v1.json` is copied without byte
changes: SHA256 `3b83730070b9e04859a39af78065dbf70399bdfb3a6d5edbbc3a8941d71f3b09`.
Its 25 documents, 28 declarations (17 session candidates and 11 scope
abstentions), 12 challenges and 8 negative documents remain a separate stratum.
The source metadata's historical base stays `420334b`; this amendment is
explicitly recorded in the supplement instead of rewriting that provenance.

`session_declarations_scaffold_supplement_v1.json` has envelope version
`session-declarations-scaffold-supplement.v1`. `base_reference` binds the
historical fixture path and SHA256. `candidate_scope_requirements` identifies
all 17 historical candidate opportunities by `document_id` and `declaration_id`,
with `unit_scope_basis` and exact authored `proofs`. Each proof uses the reference
shape `{role, page, start, end, quote}` and maps losslessly to a SourceReference
with `region.kind=text_offsets`. It adds no geometry. The fixed basis counts are:

- 7 `same_page_explicit`: five marker opportunities and two new-session controls
- 8 `structural_scaffold_proposal`: two opportunities in each of four scaffolds
- 2 `explicit_continuation`: the named continuation of a developed session

The four structural tail/prefix pairs, as `(page, start, end)`, are:

- `scaffold_empty_tail`: `(1, 0, 27)` and `(2, 0, 69)`
- `scaffold_complete_metadata`: `(1, 0, 163)` and `(2, 0, 63)`
- `scaffold_bullet_metadata`: `(1, 0, 154)` and `(2, 0, 110)`
- `scaffold_crlf_metadata`: `(1, 0, 68)` and `(2, 0, 159)`

The supplement's `additional_reference` is a normal
`session-declarations-reference.v1` envelope with exactly five new synthetic
documents. Each has one complete, page-local PDA declaration, no challenges,
`absence_expected=false`, `unit_id=null`, `expected_decision=abstained`, and
`reason=unresolved_scope`. The five structural blockers are an empty `Fecha`
in the prior tail; a current-prefix `Tema de la sesión: Tarjetas de`; a free
sentence after a completed PDA before Inicio; DATOS GENERALES after the prior
anchor; and Desarrollo before the current PDA without Inicio. They contribute
five literal-detection and five scope-abstention opportunities, zero positive
session-claim opportunities. Never merge their abstentions into positive recall.

The future scorer consumes the supplement explicitly, verifies its bound base
reference hash, and reports these five opportunities separately. The supplement
is not merged into or written over the historical fixture. Basis/proof mutation
tests must remove or contradict each basis and independently remove, duplicate,
crop, alter, substitute or desynchronize each proof role. Such mutations must
lose scope/joint/strict credit while preserving exact literal detection. The
pre-output tests currently validate authored IDs, denominators, coordinates,
quotes and required shapes only; they do not run a matcher, scanner or scorer.
Implementation and behavioral mutation tests follow review of this freeze.

## Historical-score invariance

Scorer v1.3 must preserve all pre-existing metric values for frozen `bfa5146`
and `8093752` outputs on their prior references when those outputs lack
`unit_scope_basis`. Absence of this newly introduced metadata is not a retroactive
error. Keep those original score receipts, and compare identical frozen output
bytes under the earlier scorer and the common new scorer before reporting
improvement. New report-version/definition metadata may differ; historical
metric values may not silently change.

The required basis and exact proofs govern the new structural route. The
explicit supplement additionally pins all 17 expected bases for the future
matcher, including its seven same-page and two named-continuation controls.
This supplemental requirement is not applied to old baselines on old references.
Compatibility never permits a previous-page unit to gain credit through
proximity alone or through unproved structural roles.
