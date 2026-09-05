# Supervisor iteration 0033 — idempotency, deduplication, ambiguity policy

Iteration: 33 | Phase focus: idempotency, deduplication, and ambiguity policy
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–32)

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
?? docs/handoffs/supervisor-iteration-0031.md
?? docs/handoffs/supervisor-iteration-0032.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

(`git diff --cached --name-only` → empty at pass start. HEAD `bef32fd`. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 OPEN, unmerged.)

Prior memory: `supervisor-iteration-0032.md` (staging join + `:56-62` declared-intent refinement, C1 reframed) + `supervisor-iteration-0031.md` (baseline re-verification) + `supervisor-cumulative.md` (spine 2→30, deltas 21–30) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6).

## Scope

Non-checkpoint rotating-phase pass (idempotency/dedup/ambiguity, per the 21→28 cycle order and the iteration-32 §Next move). Spec only — nothing implemented, no issue created/edited/labeled, no gate edit, no cumulative edit, no PR push (checkpoint duties next due at iteration 40). This pass re-verifies the hash/dedup helpers, their wiring state, and the ambiguity policy, and sharpens the spec with one new test-pinned observation without touching code.

## Files inspected

`supervisor-iteration-0032.md` (full) + `supervisor-iteration-0031.md` (§Findings only) + `supervisor-cumulative.md` (spine + deltas 21–30 headers) + `IMPLEMENTATION-GATE.md` (status + scorecard lines only, no edit); `curriculum/staging_validation.py` (full re-read, 238 lines); `tests/test_t54_staging_contracts.py:108-127` (hash + dedup tests, direct read); `docs/adr/0010-staging-relacional-idempotente.md` (§Decisión-2, by reference — unchanged); live greps: `activity_content_hash|find_duplicate_groups|group_by_subtopic` across `curriculum/` + `tests/`, title-copy writes (`views.py:2221-2222,2383-2384`), `group_by_subtopic` call sites (`views.py:2343,2346/:2423,2426`); `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127 — all byte-identical to iterations 2–32); `ls curriculum/schemas/` (README + 3 `.schema.json`, flat, no `v2/`); migrations tail (head still 0029); `python3 scripts/check_migrations.py` → OK; 42 test files; `gh issue list --label ready-for-agent` (6: #95/#97/#98/#103/#104/#107); `gh pr view 112` (OPEN); `git log` (HEAD `bef32fd`); `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–32; migrations head still 0029; `schemas/` still flat; `check_migrations.py` OK (re-run this pass); 42 test files; `git diff --stat` identical (+209/−716); status shape identical to iteration 32 modulo the now-present untracked `supervisor-iteration-0032.md`. No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no hash wiring, no head advance, no settings hardening, no new service module. Thirteenth consecutive no-drift pass (21–33).
2. **Hash/dedup still spec-only helpers, zero pipeline call sites (observed).** `activity_content_hash` (`staging_validation.py:189-208`) and `find_duplicate_groups` (`:211-238`) appear only in their defs plus `tests/test_t54_staging_contracts.py:109,113,116,120,125`. `views.py` calls only `group_by_subtopic` (`:2343,2346` and `:2423,2426`); no view imports either hash helper. The three legal wiring touchpoints (post-generate guard, pre-topup count, pre-convert list) remain unwired, consistent with the standing R2-before-wiring order. No change since iteration 32.
3. **Ambiguity-policy precision sharpened by direct test read (observed, spec impact).** `test_find_duplicates_reports_without_merging` (`test_t54:119-127`) pins behavior the ADR text does not state: with inputs `[base, exact-dup, same-title-diff-proposal]`, the report is `exact == [[0, 1]]` AND `same_title_diff_content == [[0, 1, 2]]` — i.e. the ambiguous group is a **title-keyed superset that overlaps the exact pair**, not a disjoint partition. Any consumer that treats the two lists as disjoint (e.g. "deduplicate exact, then human-review the rest") would double-process indices 0–1. The report-surface spec must therefore state: ambiguous lists may overlap exact lists; the review surface must render them as overlapping, and the pre-convert guard must check exact-membership before presenting an ambiguous group.
4. **C1 halves re-verified unchanged (observed).** Hash `_norm`s topic/subtopic (`:201-202`) but serializes `proposal` with `sort_keys` only (`:203-205`, no `_norm` recursion into proposal strings — question-a half open); join stays exact-`==` (`:76-77`, declared intentional at `:56-62` per iteration 32) while `by_title` keys on `_norm` triples (`:232`) — question-b half open. Consequence restated: proposal-internal case/whitespace variance ("Hola" vs "hola ") yields different hashes (missed dedup, false negative), while topic/subtopic case variance yields equal hashes the exact join will never group (join-vs-hash disagreement). The iteration-23 draft pick (`_norm`-join + outer-keys-only hash) stands; P1 must pin exactly this boundary.
5. **Gate and issue set unmoved (observed, not edited).** `IMPLEMENTATION-GATE.md` still `STATUS: HOLD` (2.5/6); `gh` returns exactly #95/#97/#98/#103/#104/#107 — same six as iterations 19/29/30/31/32. Only #98 sits on the staging critical path (0/7 re-grade at 29 carries; body not re-read this pass — no tree/issue change alleged). PR 112 OPEN, unmerged. The parallel coding lane does nothing while the gate is `HOLD` or absent.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate: HOLD observed at iteration 33** (no edit — checkpoint-only file per loop rules). Next gate review due at iteration 40.
- Ambiguity-spec refinement: the R1/report-surface work must now cite `test_t54:119-127` as the overlap baseline — ambiguous groups are title-keyed supersets overlapping exact pairs, never disjoint partitions; the review-screen + pre-convert list surface must render overlap explicitly and the guard must check exact-membership first. This joins (not replaces) the iteration-32 `:56-62` declared-intent refinement inside the C1/P1 package.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→33.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? (Carry-over 11→33.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→33.)
4. Agent-ready (C1, reframed at 32, re-verified at 33): confirm `_norm`-join + outer-keys-only hash, or keep exact reads with a P1 boundary test pinning the exact-vs-`_norm` disagreement? (Carry-over 3→33.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list (now with explicit overlap rendering per the `:119-127` observation), `llm_log` audit copy. (Carry-over 5→33, sharpened.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→33.)
7. Agent-ready (C3, directly re-verified at 27): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→33.)
8. Evidence debt: is `views.py:1068` direct `group_progress.current_activity_id` a true duplicate of `_roadmap_cursor.current_activity_id(group)` (`:2505…:2866`), or a legitimate pre-normalization alias? Needs one 50-line read of `:1046-1094`. (Carry-over 11→33, actionable.)
9. Seam-spec: keep S-numbers with the iteration-28 span pins, or retire them post-shrink? Recommend keeping with 28 spans as the pin table. (Carry-over 18→33.)
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
11. Security (from 26): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie/SECURE flags, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.
12. Branch anomaly: supervisor passes run on `supervisor/aulalista-docs`, not `updated-tech` per the prompt's "Work starts on" line (carry-over 9→33). Confirm whether future passes should switch branches or amend the prompt — switching with a dirty Phase A–E tree is unsafe, so the anomaly persists until a human directs otherwise.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Human reviews/commits the Phase A–E tree first — it is the load-bearing blocker for every downstream step (clean base ref, C1–C5 landing, R1→R4 queue).
3. Land the five R1 doc-precision patches (C1 three-site + draft pick updated with the `:56-62` declared-intent quote and the `:119-127` overlap rule, C2–C5) plus the P1/P2 pending-row names as the first committed work once a base ref exists; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface.
4. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23, reframed at 32/33) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface (now with overlap rendering) + iteration-25 P1/P2 rows + iteration-28 S-span pins and `:1068` cursor verdict before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order. Per Q8 (settled at 30), the upgrade rides as handoff Markdown in the docs-only PR, never as a created issue.
5. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
6. Refresh the loop prompt with the qualified #98 sentence, current line cites (six-issue set with #98 sole on-path at 0/7; join `staging_validation.py:76-77` + declared-intent `:56-62` + overlap rule `test_t54:119-127` + writes `views.py:2221-2222,2383-2384` + call sites `:2343,2346/:2423,2426`; cursor `:1068` vs `:2505…:2866`; `curriculum_import.py:23`; template `item.index` vs `item.id`; head 0029; 42 test files; `check_migrations.py` OK; AST views 91 top-level), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, the 7-slot draft rubric, and settled Q8.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: hash `:189-208` + dedup `:211-238` + `_norm` `:25-26` vs `:201-202` vs `:232` + overlap rule `test_t54:119-127`; join writes `views.py:2221-2222,2383-2384` + read `staging_validation.py:76-77` with declared-intent `:56-62` + call sites `views.py:2343,2346/:2423,2426`; `views.py` 2950 / AST 91 top-level defs; cursor `views.py:1068` vs 7 service sites; `roadmap_cursor.py` 27/1-def; `results.py` 552; `models.py` 2038, `CurriculumImportJob :1760` (no Topic/Subtopic/ActivityProposal tables), `ClassroomSession :762-1230` + `:1233/:1253`, `PublishedPackageSnapshot :376`, `EditorialReviewer` `:36/:308/:1961`, DemoPackage `:121/:137`; `models.py:1130` `in_bulk`, `:1875` C3 path caveat; `curriculum_import.py:23` timeout; template `item.index` vs `item.id`; `schemas/` flat; migrations head 0029; 42 test files; `check_migrations.py` OK; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; six-issue `ready-for-agent` set with #98 sole on-path at 0/7), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; ambiguous groups may overlap exact pairs (`test_t54:119-127`) and the surface must render overlap with exact-membership checked first; named surface + P1 (join-agreement, pinning the exact-vs-`_norm` boundary) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only, M2 re-runnable with C1 scope stated, M3 flagged read, M4 separate ticket with named export artifact + restore runbook); seam slices (S5→S4→S2, S1-LAST-fused-with-M3) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 34): continue the rotating phase loop (suggested: ADR/documentation contradiction reconciliation, following the 21→28 cycle order). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, `:1068` resolved, settings hardened) and whether the gate moved. Checkpoint duties next due at iteration 40 (cumulative deltas 31–40 + gate review + docs-only PR push packaging handoffs 0031–0040); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push. This handoff (`supervisor-iteration-0033.md`) remains untracked in the working tree for packaging at the iteration-40 checkpoint into PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged — https://github.com/eliancanul/AulaLista/pull/112), never merged.
