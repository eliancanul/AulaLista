# Implementation gate — AulaLista updated-tech

STATUS: HOLD

Reverted to HOLD at supervisor checkpoint iteration 20 (from on-disk `READY_FOR_IMPLEMENTATION` set off-cycle in `498a4df` + `b22b55b`). Re-affirmed HOLD at supervisor checkpoint iteration 30 after live scorecard re-check (2.5/6 — blockers observed non-none, no clean base ref; see `docs/handoffs/supervisor-iteration-0030.md` §Findings). No fix implemented in this loop; this file is a spec gate only.

## Governing decision

- **ADR/spec:** `docs/adr/0010-staging-relacional-idempotente.md`, queue R1–R5 in `docs/handoffs/supervisor-iteration-0009.md`, evidence matrix A1–A9 (with A5a/A5b split) in `docs/handoffs/supervisor-iteration-0015.md`, cumulative synthesis in `docs/handoffs/supervisor-cumulative.md` (spine 2→30).
- **Candidate slice assessed (not authorized):** review-UI stable-ID contract (`templates/curriculum/tutor_import_detail.html` `item.index→item.id`) + one focused test in `tests/test_t15_curriculum_import.py`, stacked on the claimed first-slice handler work. Narrowest slice yet, but authorization conditions below are unmet.
- **Base ref:** none clean available — the Phase A–E working tree is uncommitted (`git diff --stat`: 7 files, +209/−716 on `supervisor/aulalista-docs`, unchanged iterations 2–20). No `updated-tech` tip hash can be named until a human reviews/commits it.
- **Blockers (observed, non-none):** (a) uncommitted Phase A–E tree, no clean base ref; (b) gate evidence `docs/handoffs/coding-41560047f83c.md` unreachable from this branch (traceability gap, carry-over 15→20); (c) open picks C1 (`_norm` scope), report surface, M4 artifact shape; (d) two off-cycle gate flips with no human-signed loop-rule amendment.

## Scorecard vs the six flip conditions (2.5/6 — carries from iteration 15)

(a) tree human-reviewed/committed → OPEN; (b) narrowed allowed paths → MET; (c) mandatory convert-to-`activity_id` + test → HALF; (d) non-self-referential base ref + reachable evidence → HALF; (e) open questions answered → OPEN; (f) zero blockers → OPEN.

## Flip conditions to READY_FOR_IMPLEMENTATION (all required together, at a future 10th iteration)

(a) Phase A–E tree human-reviewed/committed so the base ref is a clean commit hash; (b) allowed paths narrowed to the iteration-9 §Draft slice; (c) convert-to-`activity_id` switch mandatory with named reorder test; (d) non-self-referential base ref with evidence reachable from the gate's own branch; (e) C1/report-surface/M4 picks answered; (f) zero blockers observed. Plus: a human-signed amendment if stacked-slice off-cycle updates are to be legitimate.

## Exact allowed implementation paths (when READY, not now)

- `templates/curriculum/tutor_import_detail.html`
- `tests/test_t15_curriculum_import.py`
- `docs/handoffs/` for the coding handoff and evidence only

## Explicitly out of scope

- All Python except already-reviewed slice code; all models, migrations, schemas, import persistence, settings, requirements, scripts, and other tests.
- Relational staging, JSON read cutover, dedup UI, publication/session authorization, #55/#56/#65, prototypes, physical-LAN evidence, and DemoPackage claims.
- Any unrelated markup, CSS, accessibility redesign, refactor, or formatting-only change.

## Invariants preserved (every ticket, including any future READY slice)

Only human EditorialReviewer publishes; only the teacher activates ClassroomSession; AI proposes only; sessions read immutable SHA256 PublishedPackageSnapshot; DemoPackage synthetic with zero pedagogical claims. Envelope: LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress.

## Acceptance tests and migration/rollback (when READY, not now)

- Focused test proving the rendered selection value is the stable ID; all prior conversion regression tests retained; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58).
- Rollback is reverting the template/test PR; no database or editorial data changes allowed.

## Why HOLD

Loop rule: default `HOLD`; flip to `READY_FOR_IMPLEMENTATION` only with governing ADR/spec, exact allowed paths, out-of-scope, invariants, acceptance tests, migration/rollback, observed blockers (none), and a concrete base ref. Blockers are observed (non-none) and the base ref is not clean — hence `HOLD`. The parallel coding lane does nothing while the gate is `HOLD` or absent.
