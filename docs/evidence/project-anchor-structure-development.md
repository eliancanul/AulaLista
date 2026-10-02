# Opt-in structural project-anchor coverage

## What changed

The separately frozen and independently reviewed
[structural contract](../development/project-anchor-structure-v1.md) adds a
bounded source-only proof to the existing offline catalogue. A book-project
reference is selectable only when the same physical planning block supplies a
literal title, planning root, scenario, purpose, product and an explicit
project-associated section. Bibliographic-only references, narrative mentions,
unknown boundaries, example/quotation/nonadoption context and mixed metadata
remain outside this new admission.

`governing_projects=False` (including the default) preserves v1 catalogue bytes.
The opt-in creates v2 catalogue evidence and available anchor options. It changes
neither literal extraction nor automatic unit assignment. Scope candidates stay
detached, pending human review; no production or editorial action is applied.

## Synthetic construction suite

The original source-only pre-implementation reference is fixed at 43 documents:
6 positive book-project targets, 26 references, 9 ambiguous targets and 2
narrative mentions. All 6 target anchors are selectable with exact original
spans/hash-bound proof. None of the 37 nonpromotion targets becomes selectable.
Independent ordinary project headings in these documents keep their v1 rules.
These are authored development cases, not blind semantic validation.

Supplemental implementation negatives include balanced quotation around required
witnesses, inline activity headings, mixed metadata labels and an unnumbered
weekday/session barrier found by independent review. They were fixed without
changing the 43-case source/reference freeze. The frozen canonical hash of all
43 v1 catalogue outputs is
`0333b27d240794c10b6524c7267630abf5022eb9eac7e770627fcc865f7ee36c`;
regression tests require both default and false to retain it without Git history.

## Same known development windows, separate diagnostics

Only catalogue availability was reevaluated. There were no new AGY, model or
provider calls and no historical response reuse. Source freezes, gold, literal
outputs, scores and windows were preserved. No FINAL/reserve source was read.

| Fixed window | Existing selectable projects | Opt-in selectable projects | Existing Mode A records | Records with a selectable project option before → after | Existing session options |
| --- | ---: | ---: | ---: | ---: | ---: |
| Physical pages 1–6, five documents | 1 | 2 | 8 | 0 → 6 | 2, unchanged |
| Physical pages 7–12, same five documents | 0 | 1 | 4 | 0 → 4 | 0, unchanged |

Each window gains one structurally corroborated book-project anchor in the same
source; other documents' catalogue eligibility is unchanged. An exact wrapped
`Temas asociados al` / `proyecto:` metadata label no longer masquerades as an
empty project unit under the opt-in.

The 7–12 catalogue uses exactly six supplied pages with an explicit +6 physical
page map. Its already-recorded 12-page literal evidence was source-checked and
projected only for this detached availability diagnostic; projected hashes/IDs
cannot replace the unchanged 12-page baseline or reuse its responses.

A selectable option means the existing contradiction guards admit a source
anchor for review. It is not proof that a declaration belongs to the project,
not a model proposal and not new joint accuracy. The three previously missing
project literal values remain missing; mixed and cross-page values were not
extracted. The unchanged additional-window baseline remains literal 20/23 and
joint 16/23 under its strict typed reference. No 90% global interpretation claim
is supported by this change.

## Verification and governance

- Source-only contract/reference review: approved before implementation
- Independent implementation/safety review: PASS_WITH_SCOPE_LIMITS; 72 original
  repros, 119 marker/quote mutations and 5 forged replay requests checked
- Independent availability review: 691 checks, zero errors; 159 unchanged routes
  and both source windows recomputed against hash-bound source snapshots
- Final focused tests: 190 passed
- Final whole-repository suite: 2973 passed, 10 skipped in 505.56 seconds
- Django system check: no issues; migration dry run: no changes
- Diff whitespace check: clean; older matcher/scorer/reference bytes and six
  historical contracts/receipts preserved

The opt-in remains off by default. This is a local development change;
publication requires a separate parent decision.
