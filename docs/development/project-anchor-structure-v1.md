# Structural project anchors: opt-in development contract v1

This source-only extension is frozen before its implementation and synthetic
matcher run. It extends the local `429397d` offline catalogue, not the literal
matcher or production interpreter. Development windows 1–6 and 7–12 remain
separate. No FINAL/reserve sources, new provider calls or historical-response
reuse are permitted. Synthetic sources below were authored for this hypothesis;
they are not a blind validation set or copied PDF excerpts.

## Three textual roles

1. A governing project heading explicitly names a planning unit. Existing
   single-line `Proyecto:` headings retain their v1 rules. This extension admits
   only a narrower book-project form with the structural proof below
2. A bibliographic project reference names a book or source. `Proyecto del Libro`
   and `de Texto:` alone, with or without a title/page citation, remain
   `reference_only`. Other reference families are not promoted by this cut
3. A narrative project mention or wrapped metadata label is not a unit.
   `Temas asociados al` immediately followed by `proyecto:` is a single metadata
   label, not an empty project heading. Only that exact physical two-line form
   receives this exemption; a bare `proyecto:` stays ambiguous

No title similarity, local-code matching, SEP IDs, pedagogical interpretation,
nearest-project rule or proximity-based declaration assignment is allowed.

## Sufficient structural proof for a book-project heading

All of these original-text witnesses must occur on the same physical page,
within one planning block, in order:

The block starts at the last standalone planning root preceding the heading
and ends at the next standalone planning root, session or actual project cue,
or the page end. Wrapped `Temas asociados al` / `proyecto:` is not that cue.
Any such barrier between the heading and association defeats proof. The first
association is not a block end: duplicates before the next unit/root defeat
proof. Citation/example/nonadoption and open-quote context is checked at the
root start using the supplied pages in order. A blank line after the root cannot
erase inherited context already present at that root. Adjacent pages without
CR/LF use one virtual newline for classification only, never evidence/identity.
An earlier blank physical paragraph may close an example block normally.

Required witnesses:

- A standalone `Planeación didáctica` root heading
- Exactly one `Proyecto del Libro [de Texto]:` heading, either on one physical
  line or the exact two-line `Proyecto del Libro` / `de Texto:` form
- One complete, nonempty single-line literal title, inline or on the next
  nonblank line. Balanced quoted titles are allowed. Wrapped/unfinished,
  mixed/table, labelled, conditional, example or nonadopted titles are not
- Nonempty labelled `Escenario:`, `Propósito:` and `Producto:` lines, in that
  order. Their values may wrap; they are witnesses, never new extracted values
- An explicit `Contenidos/PDA asociados al proyecto:` section heading. Its only
  admitted optional same-line tail is `Vinculación con otro(s) campo(s):`

A bare page citation such as `(p.30-34)` is never a title. After the title,
only blank lines and at most one standalone parenthesized page citation may
precede `Escenario:`. An unknown next physical title line defeats proof; no
completion or crop is inferred. Labels and all title characters remain literal.

There must be exactly one of each witness and no second project/unit/root,
activity moment, activity/example/citation/nonadoption block, quoted context,
control/nonphysical vertical separator or pipe/mixed-row marker between the
planning root and the associated section. A title alone, planning root alone,
canonical field name, many metadata labels or a declaration nearby is
insufficient. An association heading on a later page is insufficient. If the
proof cannot be justified, retain the v1 reference/ambiguous state.

The supported wrapped `Temas asociados al` / `proyecto:` label may occur between
`Producto:` and the associated section. It is recorded as literal supporting
metadata, not used as a project identity. Other wrapped project cues veto proof.
Narrative text cannot create a governing heading. This is bounded textual
structure, not a general discourse classifier; an unrelated reference placed
inside a matching structure is an observable limitation for human review.

## Identity and detached pipeline

The new keyword `governing_projects=True` is explicitly opt-in and boolean.
Absent/false uses `anchor-catalogue.v1` unchanged, including its exact bytes and
IDs. Enabled uses `anchor-catalogue.v2` and includes `project_structure_version`
and literal support spans. Each new book anchor covers the original complete
heading plus title, excluding external trailing whitespace. Every proof witness
retains document/text-snapshot SHA256, physical page, original Unicode offsets,
exact excerpt, excerpt SHA256 and role. Anchor IDs still hash exactly the v1
physical identity tuple; added proof is included in the catalogue hash but
cannot manufacture an ID from a title or curriculum code.

The opt-in travels through `ScopeAuditConfig` and `ScopeRequest`. Replay must
reconstruct the same opt-in catalogue and current Mode A route. Requests or
responses bound to v1 cannot be reused as v2. Support must be supplied and
source-exact. Scope validation may ignore only the exact witnessed wrapped
metadata label as an intervening unit cue. All other barriers, repeated-heading,
prior-anchor, foreign-source and unsupported-context guards remain unchanged.

Catalogue eligibility is only an available selectable option. It does not
assign any declaration, change records/evidence/values/units/claims, approve
curriculum or prove semantic belonging. A recorded/synthetic provider may
propose the available anchor; the result remains detached `needs_human_review`,
`semantic_validation=false`, `production_applied=false`. No new network adapter
or extraction fallback is introduced.

## Pre-matcher synthetic reference and evaluation

`tests/fixtures/interpretation/project_anchor_structure_v1.json` contains
original synthetic pages with authored positive, reference-only, narrative and
ambiguous expectations. Those roles and `expected_selectable` describe only the
book-project occurrence under study, not every unit in the document. A separate
explicit `Proyecto: Otro trabajo` must keep its existing v1 eligibility. Authored
ambiguous cases require nonpromotion; their old reference/ambiguous catalogue
state need not be relabelled. The independent reference test imports no catalogue,
matcher, scanner or scorer. It checks exact witness spans and hashes, fixed
separate denominators, authored classifications and preserved input strings.
An independent review of this contract and reference precedes implementation.

Implementation tests compare v1/default equivalence, v2 evidence and physical
IDs, positive eligibility, negative/ambiguous nonpromotion, wrong-source/hash,
wrong-mode replay rejection and unchanged literal outputs. Whole-repo tests and
an independent implementation review precede a clean local commit. No push or
publication occurs until parent review.

Development evaluation changes catalogue eligibility only. Freeze bytes,
baseline outputs, literal extraction, gold, scores and windows stay unchanged.
Report per-window anchor counts and the availability of source-supported options
for already extracted Mode A records, separately from actual proposals and
joint correctness. Zero new AGY/provider calls means no new model-quality or
joint-accuracy result. Remaining absent/ambiguous literals stay abstained.

Frozen synthetic source/reference SHA256: `266bcf93012d61774489fe82884e1a5979c43a5a142b47988b4f6992541be21e`.
