# Implementation gate — AulaLista updated-tech

STATUS: READY_FOR_IMPLEMENTATION

## Governing decision
- **ADR/spec:** `docs/adr/0010-staging-relacional-idempotente.md` plus the acceptance matrix in `docs/handoffs/supervisor-iteration-0005.md`.
- **Objective:** implement the first bounded slice of the fused #53/#98/#54 decision: relational staging with deterministic identity/idempotency, while preserving the JSON transition path and editorial state.
- **Base ref:** `supervisor/aulalista-docs` (the documentation checkpoint branch containing this gate and ADR-0010).

## Exact allowed implementation paths
- `curriculum/models.py`
- `curriculum/migrations/0030_relational_staging.py`
- `curriculum/curriculum_import.py`
- `curriculum/views.py`
- `curriculum/staging_validation.py`
- `tests/test_t54_staging_contracts.py`
- `tests/test_t15_curriculum_import.py`
- `tests/test_t16_activity_generation.py`
- `docs/DATABASE.md`
- `docs/adr/0010-staging-relacional-idempotente.md`
- `docs/handoffs/` for the coding handoff and evidence only

## Explicitly out of scope
- Any other Python, tests, templates, settings, requirements, migrations, scripts, or configuration.
- #55/#56/#65, prototypes, physical-LAN evidence, DemoPackage claims, publication/session authorization changes, and unrelated refactors.
- Dropping JSON fields or deleting the transitional path in this slice.

## Required behavior
1. Add relational `Topic`, `Subtopic`, and `ActivityProposal` storage per ADR-0010 with FKs, ordering, stable `id_estable`, `content_hash`, validity/issues, proposal payload, selection, and top-up provenance.
2. Add the migration without colliding with existing migration numbering; run `python3 scripts/check_migrations.py` and `makemigrations --check`.
3. Wire deterministic hash/idempotency and duplicate/ambiguity reporting into the import staging path without silently merging same-title/different-content proposals and without changing editorial decisions.
4. Keep JSON serialization as a compatibility path; do not switch destructive reads or remove fields in this slice.
5. Preserve human EditorialReviewer publication, teacher-only ClassroomSession activation, AI-proposes-only, immutable SHA256 snapshot, and synthetic DemoPackage contracts.
6. Switch any touched conversion path from positional identity to stable activity identity only if required by the above staging integration and covered by a focused test.

## Acceptance tests and evidence
- Existing focused tests: `tests/test_t54_staging_contracts.py`, `tests/test_t15_curriculum_import.py`, `tests/test_t16_activity_generation.py`.
- Run the full available suite if dependencies permit; otherwise report the exact environment blocker.
- `python3 scripts/check_migrations.py`, `python manage.py check`, migration dry-run/check, schema/hash fixtures, retry idempotency, same-title/different-content ambiguity, and partial-job compatibility must be evidenced.
- Update `docs/DATABASE.md` with model/transition details in the same PR.

## Migration and rollback
- Migration is additive and reversible; keep JSON fields and existing code path until a later, separately gated read cutover.
- On failure, do not delete or mutate existing JSON/editorial decisions; rollback the additive migration and revert only this implementation branch.

## Blockers
- None for this bounded additive slice. CI may expose environment issues; do not weaken acceptance criteria to hide them.

## Delivery
- Work in an isolated worktree on `agent/aulalista-implementation-<gate-hash>`.
- Commit only allowlisted paths, push, and open a non-merged PR targeting `main` with tests, risks, and rollback.
