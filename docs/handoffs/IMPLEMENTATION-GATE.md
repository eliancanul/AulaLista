# Implementation gate — AulaLista updated-tech

STATUS: READY_FOR_IMPLEMENTATION

## Governing decision
- **ADR/spec:** `docs/adr/0010-staging-relacional-idempotente.md`, R2 in `docs/handoffs/supervisor-iteration-0010.md`, and coding result `docs/handoffs/coding-41560047f83c.md`.
- **Scope:** second bounded slice: make the review UI submit the stable `item.id` that the completed conversion handler now consumes.
- **Base ref:** `agent/aulalista-implementation-41560047f83c` (the reviewed first-slice implementation branch).
- **PR base:** `agent/aulalista-implementation-41560047f83c` (stacked PR; do not merge automatically).
- **Blockers:** none for this UI contract slice; full relational staging remains separately gated.

## Exact allowed implementation paths
- `templates/curriculum/tutor_import_detail.html`
- `tests/test_t15_curriculum_import.py`
- `docs/handoffs/` for the coding handoff and evidence only

## Explicitly out of scope
- All Python except the already-reviewed first-slice code; all models, migrations, schemas, import persistence, settings, requirements, scripts, and other tests.
- Relational staging, JSON read cutover, dedup UI, publication/session authorization, #55/#56/#65, prototypes, physical-LAN evidence, and DemoPackage claims.
- Any unrelated markup, CSS, accessibility redesign, refactor, or formatting-only change.

## Required behavior
1. In the activity review form, submit `item.id` as the `select` value, not `item.index`, so the browser uses the stable identity expected by `_import_action_convert`.
2. Preserve the existing form action, CSRF, valid-only behavior, remove form, and all inviolable contracts: only EditorialReviewer publishes; only the teacher activates ClassroomSession; AI proposes only; sessions read immutable SHA256 PublishedPackageSnapshot; DemoPackage is synthetic with zero pedagogical claims.
3. Add one focused test in the allowlisted test file proving the rendered/declared selection value is the stable ID (or an equivalent contract test) and retain all prior conversion regression tests.

## Acceptance and rollback
- Run the focused tests and relevant Django check with `/tmp/aulalista-test-env/bin/python` or `/tmp/al-venv/bin/python` if available; report exact results.
- Before commit, `git diff --name-only` must contain only the two implementation paths plus the coding handoff.
- Commit, push a new `agent/aulalista-implementation-<gate-hash>` branch, and open a non-merged stacked PR targeting the declared PR base.
- Rollback is reverting this template/test PR; no database or editorial data changes are allowed.
