# Supervisor iteration 0031 — baseline architecture and domain contracts

Iteration: 31 | Phase focus: baseline architecture and domain contracts
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–30)

`git status --short --branch` at pass time:

```text
## supervisor/aulalista-docs...origin/supervisor/aulalista-docs
 M aulalista/settings.py
 M curriculum/models.py
 M curriculum/views.py
 M docs/DATABASE.md
 M docs/implementation-current.md
 M docs/teacher-flow.md
 D health/templates/health/local_access.html
?? .DS_Store
?? curriculum/schemas/
?? curriculum/services/
?? curriculum/staging_validation.py
?? docs/.DS_Store
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

(`?? docs/handoffs/supervisor-iteration-0021…-0030.md` entries present in prior passes are now tracked after the iteration-30 checkpoint commit `bef32fd`; the remaining `??` set is otherwise identical to iteration 30. `git diff --cached --name-only` → empty at pass start. HEAD `bef32fd`. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 OPEN, unmerged.)

Prior memory: `supervisor-iteration-0030.md` (checkpoint: ten-pass no-drift verdict, gate HOLD re-affirmed 2.5/6, Q8 settled) + `supervisor-cumulative.md` (spine 2→30, deltas 21–30) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`).

## Scope

Non-checkpoint rotating-phase pass (baseline architecture/domain contracts, resuming the 21→28 cycle order per iteration-30 §Next move). Spec only — nothing implemented, no issue created/edited/labeled, no gate edit, no cumulative edit, no PR push (checkpoint duties next due at iteration 40). This pass re-verifies CONTEXT/DESIGN vocabulary against current code anchors and re-checks tree drift + gate movement.

## Files inspected

`supervisor-iteration-0030.md` (full) + `supervisor-cumulative.md` (spine + deltas 21–30 headers) + `IMPLEMENTATION-GATE.md` (status + scorecard lines only, no edit); `CONTEXT.md` (full) + `DESIGN.md` (full) + `AGENTS.md` (full); `docs/DATABASE.md` (full re-read) + `docs/implementation-current.md` (header + state lines) + `docs/teacher-flow.md` (authority table + progress rules); `docs/adr/0010-staging-relacional-idempotente.md` (full); `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127 — all byte-identical to iterations 2–30); AST def count (`views.py` 91 top-level, `models.py` 5 top-level — method-inclusive `grep -c` figures intentionally not re-cited per iteration-21 methodology); code-anchor greps (`EDITORIAL_REVIEWER_GROUP_NAME` `models.py:36`, DemoPackage `models.py:121/:137`, `PublishedPackageSnapshot` `models.py:376`, `ClassroomSession` `models.py:762`, `ClassroomSessionConfirmation :1233` / `Closure :1253`, `EditorialReviewerWorkflowActionView :1961`); cursor pair (`views.py:1068` direct vs 7 service sites `:2505,:2579,:2599,:2634,:2770,:2807,:2866`, `roadmap_cursor.py:6` single def); `curriculum_import.py:23` (`CHAT_TIMEOUT_SECONDS = 180`); `ls curriculum/schemas/` (README + 3 `.schema.json`, flat, no `v2/`); migrations tail (head still 0029); `python3 scripts/check_migrations.py` → OK; 42 test files; `gh issue list --label ready-for-agent` (6: #95/#97/#98/#103/#104/#107); `gh pr view 112` (OPEN); `git log` (HEAD `bef32fd`); `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–30; AST top-level defs unchanged (views 91); migrations head still 0029; `schemas/` still flat; `check_migrations.py` OK (re-run this pass); 42 test files; `git diff --stat` identical (+209/−716); status shape identical to iteration 30 modulo the now-committed 0021–0030 handoffs. No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no hash wiring, no head advance, no settings hardening, no new service module. Eleventh consecutive no-drift pass (21–31).
2. **Domain-contract anchors re-verified against code (observed).** CONTEXT vocabulary resolves to current lines: `EditorialReviewer` group constant (`models.py:36`) + human-gated publish path (`models.py:308` group requirement, `:1961` workflow action view); `PublishedPackageSnapshot` class (`:376`); `ClassroomSession` class (`:762-1230`) with confirmation/closure companions (`:1233/:1253` — teacher-activates-session boundary); DemoPackage synthetic flag (`:121` docstring, `:137` `is_demo`); pseudonymity classes (`StudentTurn`/`PseudonymousResult` per DATABASE §Retención). No contradiction with the spine's inviolable contracts found this pass. Two known doc-staleness items (C2 `DATABASE.md:103-105` missing ADR-0010 pointer; C4 `implementation-current.md:3-6` header `main`/`d4fcb99`) reconfirmed present and already carried as R1 — not re-edited (root docs out of scope).
3. **DESIGN contract re-verified by reference (observed).** Dirección C + authority boundary (AI proposes only; EditorialReviewer publishes; teacher activates) + LAN-only/no-CDN + synthetic-demo labeling all consistent between `DESIGN.md`, `CONTEXT.md`, `teacher-flow.md` authority table, and the code anchors above. No new surface, token, or state added (no tree change to contradict). Full token/state audit not repeated — unchanged tree makes the iteration-30 root-doc verdict carry without re-derivation.
4. **Gate unmoved (observed, not edited).** `IMPLEMENTATION-GATE.md` still `STATUS: HOLD` with the 2.5/6 scorecard; log tip `bef32fd` is this branch's own checkpoint commit (prior gate-revert `606aa64` still in history). Non-checkpoint pass → no gate review edit per loop rules; re-affirmation recorded here only as observation. The parallel coding lane does nothing while the gate is `HOLD` or absent.
5. **`ready-for-agent` set unchanged at six, live re-verified (observed).** `gh` returns exactly #95/#97/#98/#103/#104/#107 — same six as iterations 19/29/30. Only #98 sits on the staging critical path (0/7 re-grade at 29 carries; body not re-read this pass — no tree/issue change alleged).
6. **Cursor evidence debt unchanged (observed).** `views.py:1068` direct `group_progress.current_activity_id` vs 7 `_roadmap_cursor.current_activity_id(group)` service sites re-cited live; the 50-line read of `:1046-1094` remains pending (Q9 carry-over). No new duplicate/remove/convert movement (tree identical).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate: HOLD observed at iteration 31** (no edit — checkpoint-only file per loop rules). Next gate review due at iteration 40.
- Baseline verdict: CONTEXT/DESIGN vocabulary resolves to live code anchors with no contradictions; remaining work is documentary (R1 C1–C5) + human-gated (Phase A–E review/commit, C1/report-surface/M4 picks), not a re-modeling of the domain.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→31.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? (Carry-over 11→31.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→31.)
4. Agent-ready (C1, draft pick at 23, three-site at 24, P1/P2 rows at 25): confirm `_norm`-join + outer-keys-only hash, or take the exact-join-intentional alternative with inverted P1? (Carry-over 3→31.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list, `llm_log` audit copy. (Carry-over 5→31.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→31.)
7. Agent-ready (C3, directly re-verified at 27): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→31.)
8. Evidence debt: is `views.py:1068` direct `group_progress.current_activity_id` a true duplicate of `_roadmap_cursor.current_activity_id(group)` (`:2505…:2866`), or a legitimate pre-normalization alias? Needs one 50-line read of `:1046-1094`. (Carry-over 11→31, actionable.)
9. Seam-spec: keep S-numbers with the iteration-28 span pins, or retire them post-shrink? Recommend keeping with 28 spans as the pin table. (Carry-over 18→31.)
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
11. Security (from 26): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie/SECURE flags, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.
12. Branch anomaly: supervisor passes run on `supervisor/aulalista-docs`, not `updated-tech` per the prompt's "Work starts on" line (carry-over 9→31). Confirm whether future passes should switch branches or amend the prompt — switching with a dirty Phase A–E tree is unsafe, so the anomaly persists until a human directs otherwise.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Human reviews/commits the Phase A–E tree first — it is the load-bearing blocker for every downstream step (clean base ref, C1–C5 landing, R1→R4 queue).
3. Land the five R1 doc-precision patches (C1 three-site + draft pick, C2–C5) plus the P1/P2 pending-row names as the first committed work once a base ref exists; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface.
4. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface + iteration-25 P1/P2 rows + iteration-28 S-span pins and `:1068` cursor verdict before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order. Per Q8 (settled at 30), the upgrade rides as handoff Markdown in the docs-only PR, never as a created issue.
5. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
6. Refresh the loop prompt with the qualified #98 sentence, current line cites (six-issue set with #98 sole on-path at 0/7; cursor `:1068` vs `:2505…:2866`; `curriculum_import.py:23`; template `item.index` vs `item.id`; head 0029; 42 test files; `check_migrations.py` OK; AST views 91 top-level), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, the 7-slot draft rubric, and settled Q8.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / AST 91 top-level defs; cursor `views.py:1068` vs 7 service sites; `roadmap_cursor.py` 27/1-def; `results.py` 552; `models.py` 2038, `ClassroomSession :762-1230` + `:1233/:1253`, `PublishedPackageSnapshot :376`, `EditorialReviewer` `:36/:308/:1961`, DemoPackage `:121/:137`; `models.py:1130` `in_bulk`, `:1875` C3 path caveat; `staging_validation.py` hash `:189-208`, dedup `:211-238`, join `:76-77`; `curriculum_import.py:23` timeout; template `item.index` vs `item.id`; `schemas/` flat; migrations head 0029; 42 test files; `check_migrations.py` OK; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; six-issue `ready-for-agent` set with #98 sole on-path at 0/7), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; named surface + P1 (join-agreement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only, M2 re-runnable with C1 scope stated, M3 flagged read, M4 separate ticket with named export artifact + restore runbook); seam slices (S5→S4→S2, S1-LAST-fused-with-M3) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 32): continue the rotating phase loop (suggested: curriculum staging join and relational model, following the 21→28 cycle order). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, `:1068` resolved, settings hardened) and whether the gate moved. Checkpoint duties next due at iteration 40 (cumulative deltas 31–40 + gate review + docs-only PR push packaging handoffs 0031–0040); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push. This handoff (`supervisor-iteration-0031.md`) remains untracked in the working tree for packaging at the iteration-40 checkpoint into PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged — https://github.com/eliancanul/AulaLista/pull/112), never merged.
