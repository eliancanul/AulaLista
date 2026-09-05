# Implementation gate — AulaLista updated-tech

STATUS: READY_FOR_IMPLEMENTATION

## Governing decision
- **ADR/spec:** `docs/adr/0010-staging-relacional-idempotente.md` and the R2 recommendation in `docs/handoffs/supervisor-iteration-0010.md`.
- **Scope:** first, independently safe implementation slice: eliminate the positional activity identity hazard in the conversion path. This is deliberately narrower than the full relational-staging migration.
- **Base ref:** `supervisor/aulalista-docs` at this gate commit.
- **Blockers:** none for this isolated slice; the broader #53/#98/#54 migration remains separately gated.

## Exact allowed implementation paths
- `curriculum/views.py`
- `tests/test_t15_curriculum_import.py`
- `docs/handoffs/` for the coding handoff and evidence only

## Explicitly out of scope
- `curriculum/models.py`, migrations, schemas, staging-validation redesign, import persistence, templates, settings, requirements, scripts, and all other tests.
- The full relational staging migration, JSON read cutover, dedup UI, publication/session authorization, #55/#56/#65, prototypes, physical-LAN evidence, and DemoPackage claims.
- Any unrelated refactor or formatting-only change.

## Required behavior
1. Replace the targeted conversion lookup that uses a submitted/list position with stable activity identity, using the existing identity convention in the current branch.
2. Preserve the existing valid/selected/editorial behavior and all inviolable contracts: only EditorialReviewer publishes; only the teacher activates ClassroomSession; AI proposes only; sessions read immutable SHA256 PublishedPackageSnapshot; DemoPackage is synthetic with zero pedagogical claims.
3. Add a focused regression test in `tests/test_t15_curriculum_import.py` proving that reordering or a stale positional index cannot convert the wrong activity, while the intended stable identity still converts correctly.
4. Do not alter the import schema or perform the relational migration in this slice.

## Acceptance and rollback
- Run the focused test file and any directly required Django checks; report exact commands/results.
- `git diff --name-only` before commit must contain only the allowlisted paths.
- Commit, push branch `agent/aulalista-implementation-<gate-hash>`, and open one non-merged PR targeting `main`; include tests, risks, and rollback. No force-push or merge.
- Rollback is reverting this focused PR; no database migration or destructive data change is permitted.
