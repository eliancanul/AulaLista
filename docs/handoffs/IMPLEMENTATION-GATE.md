# Implementation gate — AulaLista updated-tech

STATUS: HOLD

## Why HOLD (10th-iteration review, iteration 10)

The prior `READY_FOR_IMPLEMENTATION` was committed off-cycle with defects: a self-referential base ref (its own docs branch), broader-than-one-change allowed paths, and a conditional convert-to-`activity_id` switch that iterations 3/5/7/8/9 spec as mandatory. Additionally: the uncommitted Phase A–E tree is still awaiting human review, and three agent-ready questions are undecided (`_norm` recursion pick, duplicate-report surface, M4 export shape). Any single gap requires `HOLD`. The parallel coding lane does nothing while the gate is `HOLD` or absent.

## Governing decision (applies when flipped)

- **ADR/spec:** `docs/adr/0010-staging-relacional-idempotente.md` plus the acceptance matrix in `docs/handoffs/supervisor-iteration-0005.md`, the M0→M4 sequence in `supervisor-iteration-0007.md`, the seam order in `supervisor-iteration-0008.md`, and the ready-for-agent queue in `supervisor-iteration-0009.md`.
- **Objective:** the first bounded slice of the fused #53/#98/#54 decision: convert-to-`activity_id` (R2) + duplicate report wiring at the three touchpoints (R3-slice, no M4), while preserving the JSON path and editorial state.

## Flip conditions (ALL required for READY_FOR_IMPLEMENTATION)

1. The Phase A–E working tree is human-reviewed and committed, so the base ref below can name a clean commit hash.
2. Allowed paths are narrowed to the slice in §Exact allowed paths (no new tables, no migration, no M4).
3. The convert-to-`activity_id` switch is mandatory with the named reorder test.
4. Base ref is a concrete, non-self-referential commit on `updated-tech` (verified tree: `views.py` 2950 / `models.py` 2038 / `staging_validation.py` 238 lines).
5. Open questions answered: `_norm` recursion pick, duplicate-report surface, M4 artifact shape (M4 stays out of the slice regardless).
6. Zero blockers observed at flip time.

## Exact allowed implementation paths (when READY)

- `curriculum/views.py` (convert block `views.py:2446-2475` + three `find_duplicate_groups` touchpoints only)
- `curriculum/staging_validation.py` (only if the canonicalization pick requires it)
- `tests/test_t54_staging_contracts.py` + one new focused test file
- `docs/DATABASE.md` (same PR, rule #58)

## Explicitly out of scope (when READY)

- New tables/M1, backfill/M2, flagged new-read/M3, M4 drop, schemas `v2/`, S-seam moves, `curriculum_import.py` model changes, any other Python/tests/templates/settings/requirements/migrations/scripts/configuration.
- #55/#56/#65, prototypes, physical-LAN evidence, DemoPackage claims, publication/session authorization changes, unrelated refactors.
- Dropping JSON fields or deleting the transitional path.

## Invariants preserved (always)

Human EditorialReviewer publishes; teacher-only ClassroomSession activation; AI proposes only; sessions read immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims. Envelopes from iteration 5 (evidence matrix A1–A9), 6 (LAN-only HTTP, staff-gated pipeline, sealed device cookies, single-process SQLite, no new egress), 7 (M0→M4 + per-step rollback), 8 (Steps 0–4, S1 fused with M3).

## Acceptance tests and evidence (when READY)

- New test: reorder-between-render-and-POST converts the intended draft (via `_activity_id`, never positional).
- `tests/test_t54_staging_contracts.py` + t15/t16/t19/t20/t22/t24 green; `python3 scripts/check_migrations.py` + `makemigrations --check` clean.
- Report + human confirm at the three touchpoints: `exact` collapses only with explicit confirm; `same_title_diff_content` side-by-side, never silently merged; one section per `(topic, sub, title)` key with per-pair badges.
- No physical-LAN or concurrent-write claims; cite current lines only.

## Migration and rollback (when READY)

- No migration in this slice; JSON untouched as truth; code-only revert.
- M4 (drop JSON writes) is a separate human-confirmed ticket with a named JSON-export artifact + restore runbook — never bundled.

## Observed blockers

- Human review of the uncommitted Phase A–E tree (pending since iteration 2).
- Undecided: `_norm` recursion pick; duplicate-report surface; M4 export shape.
- Base ref uncommitted; self-referential refs not accepted.

## Delivery (when READY)

- Work in an isolated worktree on `agent/aulalista-implementation-<gate-hash>`.
- Commit only allowlisted paths, push, and open a non-merged PR targeting `main` with tests, risks, and rollback.
