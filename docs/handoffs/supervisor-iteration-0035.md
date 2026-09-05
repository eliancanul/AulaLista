# Supervisor iteration 0035 — tests, evidence, and acceptance matrix

Iteration: 35 | Phase focus: tests, evidence, and acceptance matrix
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–34)

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
?? docs/handoffs/supervisor-iteration-0033.md
?? docs/handoffs/supervisor-iteration-0034.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

(`git diff --cached --name-only` → empty at pass start. HEAD `bef32fd`. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 OPEN, unmerged.)

Prior memory: `supervisor-iteration-0034.md` (C1–C5 three-way reconciliation) + `supervisor-iteration-0033.md` (overlap rule `test_t54:119-127`) + `supervisor-iteration-0032.md` (declared-intent `:56-62`) + `supervisor-cumulative.md` (spine 2→30, deltas 21–30) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6).

## Scope

Non-checkpoint rotating-phase pass (tests/evidence/acceptance matrix, per the 21→28 cycle order and the iteration-34 §Next move). Spec only — nothing implemented, no issue created/edited/labeled, no gate edit, no cumulative edit, no PR push (checkpoint duties next due at iteration 40). This pass re-verifies the A1–A9 acceptance net against current files, re-pins the convert/cursor/secrets cites, and adds one new matrix precision datum without touching code.

## Files inspected

`supervisor-iteration-0034.md` (full) + `supervisor-iteration-0033.md` (§Findings only) + `supervisor-cumulative.md` (spine + deltas 21–30 headers) + `IMPLEMENTATION-GATE.md` (status + scorecard lines only, no edit); `docs/adr/0010-staging-relacional-idempotente.md` (full re-read, 58 lines); `docs/adr/0006-teacher-workflow-and-human-curriculum-progress.md` (`:29` state line, direct re-read); `curriculum/staging_validation.py` (full re-read, 238 lines); `tests/test_t54_staging_contracts.py` (full re-read, 127 lines); `curriculum/models.py:1860-1889` (`clean()` + `:1875` path, direct re-read) + `:1125-1135` (`in_bulk`, direct re-read); `curriculum/views.py:2218-2225,2380-2387` (title-copy writes, direct re-read) + `:1046-1070` (cursor direct-read site, direct re-read) + `:2301-2320` (`_activity_id`/remove, by grep); `aulalista/settings.py:8-21,107` (secrets/DEBUG/hosts/validators, by grep); `curriculum/curriculum_import.py:23` (180s timeout, by grep); `templates/curriculum/tutor_import_detail.html:148/:157` (`item.index` vs `item.id`, by grep); live greps: `activity_content_hash|find_duplicate_groups|group_by_subtopic` (9 matches), `current_activity_id|group_progress` (cursor census); `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127 — byte-identical to iterations 2–34); AST views 91 top-level defs / models 5 defs + 21 classes (recomputed this pass); `ls curriculum/schemas/` (README + 3 `.schema.json`, flat, no `v2/`); migrations tail (head still 0029); `python3 scripts/check_migrations.py` → OK; `ls tests/test_*.py | wc -l` → 42 (matrix files t15/t16/t19/t20/t22/t24 + t54 all present); `gh issue list --label ready-for-agent` (6: #95/#97/#98/#103/#104/#107); `gh pr view 112` (OPEN); `git log` (HEAD `bef32fd`); `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–34; AST views 91 top-level defs recomputed identical; migrations head still 0029; `schemas/` still flat; `check_migrations.py` OK (re-run this pass); 42 test files; `git diff --stat` identical (+209/−716); status shape identical to iteration 34 modulo the now-present untracked `supervisor-iteration-0034.md`. No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no hash wiring, no head advance, no settings hardening, no new service module. Fifteenth consecutive no-drift pass (21–35).
2. **Acceptance net A1–A9 present by file existence, green-ness unproven here (observed).** Matrix files all exist: `test_t15_curriculum_import.py`, `test_t16_activity_generation.py`, `test_t19_wait_and_progress.py`, `test_t20_subtopic_review.py`, `test_t22_context_consolidation_checkboxes.py`, `test_t24_database_contracts.py`, `test_t54_staging_contracts.py` (127 lines, 5 tests: valid-pass, empty-pass, invalid-paths, hash-stability, overlap-report). `pytest` cannot run in this environment (no `.venv`), so "must stay green" remains a ticket-level gate condition, not a verified fact this pass. No test file changed (byte counts identical).
3. **A5a/A5b split re-pinned, both halves still OPEN (observed, direct re-read).** A5a convert-identity: `views.py:2301` `_activity_id(entry, fallback_index)` exists, remove resolves via `_activity_id` (`:2317`), grouped rows carry `{"id": _activity_id(entry, index), ...}` (`:2428`), but convert path still positional (grouped `index` rendered as checkbox `value="{{ item.index }}"` at `tutor_import_detail.html:148` while stable `item.id` sits in a hidden field at `:157`). A5b template switch (`item.index→item.id` + one focused test in `test_t15`) unwired. Ordering R1→R2(A5a+A5b)→R3 stands.
4. **P1/P2 proving-test rows still pending, now precisely placeable (observed, spec impact — new datum at 35).** P1 (join-agreement): `group_by_subtopic` exact-`==` (`staging_validation.py:76-77`, declared intentional `:56-62`) vs `by_title` `_norm` triples (`:232`) vs hash `_norm` topic/subtopic (`:201-202`) with raw-serialized proposal (`:203-205`) — the boundary test belongs in `test_t54` beside `test_find_duplicates_reports_without_merging` (`:119-127`), asserting the exact-vs-`_norm` disagreement is pinned, not silently fixed. P2 (same-title-separation): same `:119-127` fixture already pins overlap (`exact == [[0,1]]` AND `same_title_diff_content == [[0,1,2]]`); the missing row is the guard-order assertion (exact-membership checked before ambiguous presentation). Both green BEFORE any of the three wiring touchpoints (post-generate guard, pre-topup count, pre-convert list at `views.py:2343,2346/:2423,2426`). Neither P1 nor P2 exists on disk — names only.
5. **N+1 stays FIXED, cursor stays OPEN, secrets stay dev-default (observed, direct re-read).** `models.py:1130` `PublishedPackageSnapshot.objects.in_bulk(...)` with the `# Un solo query (evita N+1…)` comment — prompt's `models.py:1125-1127` cite is stale pre-shrink. Cursor: `views.py:1068` direct `group_progress.current_activity_id` (inside `tutor_session_active :1046-1070`, re-read this pass) vs 7 `_roadmap_cursor.current_activity_id(group)` service sites (`:2505…:2866`, by grep) — the 50-line `:1046-1094` read is now DONE for the first 25 lines; verdict still needs the remainder (`:1070-1094`, position/next-step computation) to rule alias-vs-duplicate. Secrets: `settings.py:11-14` dev-default SECRET, `:14-17` DEBUG default True, `:19-21` `*` hosts, `:107` empty validators — hardening checklist owner still open (Q11).
6. **C1–C5 carry OPEN unchanged (observed by re-read of the pinned lines).** C1 three-way (ADR-0010 §Decisión-2 == docstring `:192` ≠ code `:201-205`); C2 `DATABASE.md:103-105` stale future-ADR pointer; C3 `models.py:1875` `schemas/v1` path vs flat `*.schema.json`; C4 `implementation-current.md:3-6` header (`main`/`d4fcb99`) vs HEAD `bef32fd`; C5 ADR-0006 `:29` three states vs `teacher-flow.md:107-120` four (+`BLOQUEADA`). No wording fix landed.
7. **Gate and issue set unmoved (observed, not edited).** `IMPLEMENTATION-GATE.md` still `STATUS: HOLD` (2.5/6); `gh` returns exactly #95/#97/#98/#103/#104/#107 — same six as iterations 19–34. Only #98 sits on the staging critical path (0/7 re-grade at 29 carries; body not re-read this pass). PR 112 OPEN, unmerged. The parallel coding lane does nothing while the gate is `HOLD` or absent.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate: HOLD observed at iteration 35** (no edit — checkpoint-only file per loop rules). Next gate review due at iteration 40.
- Matrix verdict: the A1–A9 net is file-present but run-unverified in this environment; the next ticket draft must name the seven matrix files + `test_t54` explicitly, carry the A5a/A5b split, and require P1+P2 green-before-wiring. The new precision datum is P1/P2 placement: both live in `test_t54` next to `:119-127`, P1 pins the join boundary, P2 pins guard order.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→35.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? (Carry-over 11→35.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→35.)
4. Agent-ready (C1, three-way framing at 34, re-verified at 35): confirm `_norm`-join + outer-keys-only hash, or keep exact reads with P1 pinning the exact-vs-`_norm` disagreement? (Carry-over 3→35.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list (with explicit overlap rendering per `:119-127`), `llm_log` audit copy. (Carry-over 5→35.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→35.)
7. Agent-ready (C3, re-verified at 27/34/35): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→35.)
8. Evidence debt (narrowed at 35): `views.py:1068` vs `_roadmap_cursor` — first 25 lines of `:1046-1094` read (`:1046-1070`); remaining `:1070-1094` still needed for the alias-vs-duplicate verdict. (Carry-over 11→35, actionable, halved.)
9. Seam-spec: keep S-numbers with the iteration-28 span pins, or retire them post-shrink? Recommend keeping with 28 spans as the pin table. (Carry-over 18→35.)
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
11. Security (from 26): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie/SECURE flags, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.
12. Branch anomaly: supervisor passes run on `supervisor/aulalista-docs`, not `updated-tech` per the prompt's "Work starts on" line (carry-over 9→35). Confirm whether future passes should switch branches or amend the prompt — switching with a dirty Phase A–E tree is unsafe, so the anomaly persists until a human directs otherwise.
13. Matrix execution (new at 35): where does the A1–A9 + P1/P2 green run execute before wiring, given `pytest` is unrunnable in this supervisor environment (no `.venv`)? Name the runner (coding-lane env or CI) in the #98 upgrade so "green" is verifiable, not aspirational.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Human reviews/commits the Phase A–E tree first — it is the load-bearing blocker for every downstream step (clean base ref, C1–C5 landing, R1→R4 queue).
3. Land the five R1 doc-precision patches (C1 three-site + draft pick with the `:56-62` declared-intent quote, three-way ADR==docstring≠code framing, and the `:119-127` overlap rule; C2–C5) plus the P1/P2 pending-row names as the first committed work once a base ref exists; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface.
4. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23, reframed at 32/33/34) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface (with overlap rendering) + iteration-25 P1/P2 rows (now placed: `test_t54` beside `:119-127`, P1 boundary + P2 guard-order) + iteration-28 S-span pins and `:1068` cursor verdict (half-read at 35) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order. Per Q8 (settled at 30), the upgrade rides as handoff Markdown in the docs-only PR, never as a created issue.
5. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
6. Refresh the loop prompt with the qualified #98 sentence, current line cites (six-issue set with #98 sole on-path at 0/7; join `staging_validation.py:76-77` + declared-intent `:56-62` + three-way C1 framing (ADR-0010 §Decisión-2 == docstring `:192` ≠ code `:201-205`) + overlap rule `test_t54:119-127` + P1/P2 placement + writes `views.py:2221-2222,2383-2384` + call sites `:2343,2346/:2423,2426`; cursor `:1068` (half-read `:1046-1070`) vs `:2505…:2866`; `curriculum_import.py:23`; template `item.index :148` vs `item.id :157`; head 0029; 42 test files; `check_migrations.py` OK; AST views 91 top-level), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, the 7-slot draft rubric, and settled Q8.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: matrix files t15/t16/t19/t20/t22/t24 + `test_t54` 127 lines/5 tests + overlap rule `:119-127` + P1/P2 placement; hash `:189-208` + dedup `:211-238` + `_norm` `:25-26` vs `:201-202` vs `:232` + join `:76-77` with declared-intent `:56-62`; join writes `views.py:2218-2225,2380-2387` + call sites `views.py:2343,2346/:2423,2426`; `views.py` 2950 / AST 91 top-level defs; cursor `views.py:1068` (read `:1046-1070`, remainder `:1070-1094` pending) vs 7 service sites; `roadmap_cursor.py` 27/1-def; `results.py` 552; `models.py` 2038, `CurriculumImportJob :1760` (no Topic/Subtopic/ActivityProposal tables), `ClassroomSession :762-1230` + `:1233/:1253`, `PublishedPackageSnapshot :376`, `EditorialReviewer` `:36/:308/:1961`, DemoPackage `:121/:137`; `models.py:1130` `in_bulk`, `:1875` C3 path caveat; `curriculum_import.py:23` timeout; template `item.index :148` vs `item.id :157`; `_activity_id :2301/:2317/:2428`; `schemas/` flat; migrations head 0029; 42 test files; `check_migrations.py` OK; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; six-issue `ready-for-agent` set with #98 sole on-path at 0/7), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; named matrix run (runner per Q13 new at 35: coding-lane env or CI — supervisor env has no `.venv`) green including P1+P2 BEFORE wiring; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; ambiguous groups may overlap exact pairs (`test_t54:119-127`) and the surface must render overlap with exact-membership checked first (P2 pins guard order); named surface + P1 (join-agreement, pinning the exact-vs-`_norm` boundary per the `:56-62` refinement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only, M2 re-runnable with C1 scope stated, M3 flagged read, M4 separate ticket with named export artifact + restore runbook); seam slices (S5→S4→S2, S1-LAST-fused-with-M3) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 36): continue the rotating phase loop (suggested: security, deployment, operational constraints, following the 21→28 cycle order). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, `:1070-1094` cursor remainder read, settings hardened) and whether the gate moved. Checkpoint duties next due at iteration 40 (cumulative deltas 31–40 + gate review + docs-only PR push packaging handoffs 0031–0040); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push. This handoff (`supervisor-iteration-0035.md`) remains untracked in the working tree for packaging at the iteration-40 checkpoint into PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged — https://github.com/eliancanul/AulaLista/pull/112), never merged.
