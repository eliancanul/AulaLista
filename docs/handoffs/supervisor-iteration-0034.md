# Supervisor iteration 0034 — ADR and documentation contradiction reconciliation

Iteration: 34 | Phase focus: ADR and documentation contradiction reconciliation
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–33)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

(`git diff --cached --name-only` → empty at pass start. HEAD `bef32fd`. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 OPEN, unmerged.)

Prior memory: `supervisor-iteration-0033.md` (idempotency/dedup/ambiguity, `:119-127` overlap rule) + `supervisor-iteration-0032.md` (staging join, `:56-62` declared-intent refinement) + `supervisor-iteration-0031.md` (baseline re-verification) + `supervisor-cumulative.md` (spine 2→30, deltas 21–30) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6).

## Scope

Non-checkpoint rotating-phase pass (ADR/documentation contradiction reconciliation, per the 21→28 cycle order and the iteration-33 §Next move). Spec only — nothing implemented, no issue created/edited/labeled, no gate edit, no cumulative edit, no PR push (checkpoint duties next due at iteration 40). This pass directly re-reads all five R1 doc-precision contradictions (C1–C5) against current lines and confirms each is still OPEN without touching code.

## Files inspected

`supervisor-iteration-0033.md` (full) + `supervisor-iteration-0032.md` (§Findings/§Decisions only) + `supervisor-cumulative.md` (spine + deltas 21–30 headers) + `IMPLEMENTATION-GATE.md` (status + scorecard lines only, no edit); `docs/adr/0010-staging-relacional-idempotente.md` (full re-read, 58 lines); `docs/adr/0006-teacher-workflow-and-human-curriculum-progress.md` (full re-read, 35 lines); `curriculum/staging_validation.py` (full re-read, 238 lines); `curriculum/models.py:1860-1889` (`clean()` + `:1875` docstring path, direct read); `docs/DATABASE.md:100-114` (§Deuda-1, direct read); `docs/implementation-current.md:1-15` (header, direct read); `docs/teacher-flow.md:107-120` (roadmap-state mapping, by prior cite — not re-read this pass, no change alleged); `tests/test_t54_staging_contracts.py:108-127` (hash + dedup tests, direct read); live greps: `activity_content_hash|find_duplicate_groups|group_by_subtopic` across `curriculum/` + `tests/`; `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127 — all byte-identical to iterations 2–33); `ls curriculum/schemas/` (README + 3 `.schema.json`, flat, no `v2/`); migrations tail (head still 0029); `python3 scripts/check_migrations.py` → OK; `ls tests/` 44 entries (≈42 `test_*.py` + helpers + `__pycache__`, consistent with prior "42 test files" count); `gh issue list --label ready-for-agent` (6: #95/#97/#98/#103/#104/#107); `gh pr view 112` (OPEN); `git log` (HEAD `bef32fd`); `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–33; migrations head still 0029; `schemas/` still flat; `check_migrations.py` OK (re-run this pass); `git diff --stat` identical (+209/−716); status shape identical to iteration 33 modulo the now-present untracked `supervisor-iteration-0033.md`. No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no hash wiring, no head advance, no settings hardening, no new service module. Fourteenth consecutive no-drift pass (21–34).
2. **C1 still OPEN, now a three-way contradiction (observed, direct re-read).** ADR-0010 §Decisión-2 states the hash is "SHA256 canónico de `(topic, subtema, proposal)` normalizados (NFKC+casefold+trim)". The `activity_content_hash` docstring (`staging_validation.py:190-196`) repeats the claim: "Normaliza (NFKC + casefold + trim) topic, subtema y proposal canónico." The code does not do this: `_norm` applies only to `topic`/`subtopic` (`:201-202`); `proposal` is serialized with `sort_keys` only (`:203-205`, no `_norm` recursion into proposal strings). So ADR text == docstring text ≠ code behavior. The iteration-32 `:56-62` declared-intent note covers only the read-path join (exact `==` at `:76-77` intentional), not the hash's proposal scope — question-a half untouched. Question-b half untouched: join exact (`:76-77`) vs `by_title` on `_norm` triples (`:232`) vs hash on `_norm` topic/subtopic. The iteration-23 draft pick (`_norm`-join + outer-keys-only hash) stands; the R1 patch must fix THREE sites (ADR §Decisión-2 + docstring `:192` + `schemas/README.md`) plus the P1 boundary test.
3. **C2 still OPEN (observed, direct re-read).** `docs/DATABASE.md:103-105` says hierarchy-in-JSON is a "Decisión consciente para el prototipo; revisar antes de escalar (nuevo ADR)." ADR-0010 already IS that new ADR (accepted, design; fuses #53/#98/#54, relational target at §Decisión-1). The pointer is stale: it invites a future ADR that exists. R1 fix is one sentence — cite ADR-0010 as the scaling decision and mark the debt item superseded-pending-migration. No code change.
4. **C3 still OPEN (observed, direct re-read).** `models.py:1875` docstring says "Valida los JSONField contra `curriculum/schemas/v1`". On-disk layout is flat (`topics.schema.json`, `activities.schema.json`, `llm_trace.schema.json` + README, no `v1/` directory, verified by `ls` this pass). Path wording is wrong whether read as directory or version tag. R1 fix is a docstring-only wording patch to the flat `*.schema.json` form. No behavior change.
5. **C4 still OPEN (observed, direct re-read).** `docs/implementation-current.md:3-6` header pins `Rama: main`, `Último commit: d4fcb99`, `Fecha: 22 de agosto de 2026`. Observed HEAD here is `bef32fd` on `supervisor/aulalista-docs`; the prompt mandates work starts on `updated-tech`. The header describes neither branch. R1 fix is a header-only refresh (branch-agnostic wording or current ref + date). No code change.
6. **C5 still OPEN, minor (observed by prior cite, not re-read this pass).** ADR-0006 `:29` names three roadmap states (`ACTUAL`, `DISPONIBLE`, `COMPLETADA`) shown as text. `teacher-flow.md:107-120` names four runtime states (+ `BLOQUEADA`) plus the DESIGN/viewport mapping (`actual/disponible/completado/bloqueado` + manual `visto`). ADR omits `BLOQUEADA`; no contradiction on authority (both agree human confirms, AI never advances), only a state-enumeration gap. R1 fix is adding the `BLOQUEADA` line to ADR-0006 `:29` (or an explicit "see teacher-flow for the fourth state" pointer). No code change.
7. **Gate and issue set unmoved (observed, not edited).** `IMPLEMENTATION-GATE.md` still `STATUS: HOLD` (2.5/6); `gh` returns exactly #95/#97/#98/#103/#104/#107 — same six as iterations 19/29/30/31/32/33. Only #98 sits on the staging critical path (0/7 re-grade at 29 carries; body not re-read this pass — no tree/issue change alleged). PR 112 OPEN, unmerged. The parallel coding lane does nothing while the gate is `HOLD` or absent.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate: HOLD observed at iteration 34** (no edit — checkpoint-only file per loop rules). Next gate review due at iteration 40.
- C1–C5 reconciliation verdict: all five R1 doc-precision patches remain OPEN and still correctly scoped as docs-only (C1 three-site wording + draft pick + P1 boundary test name; C2 one-sentence ADR pointer; C3 docstring path wording; C4 header refresh; C5 one-line state addition). None requires a model, migration, view, template, or settings change. This pass adds one new precision datum to the C1 package: the contradiction is three-way (ADR == docstring ≠ code), not two-way — the R1 patch must touch all three wording sites to close it.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→34.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? (Carry-over 11→34.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→34.)
4. Agent-ready (C1, three-way framing new at 34): confirm `_norm`-join + outer-keys-only hash, or keep exact reads with a P1 boundary test pinning the exact-vs-`_norm` disagreement? (Carry-over 3→34, sharpened.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list (with explicit overlap rendering per the iteration-33 `:119-127` observation), `llm_log` audit copy. (Carry-over 5→34.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→34.)
7. Agent-ready (C3, directly re-verified at 27 and 34): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→34.)
8. Evidence debt: is `views.py:1068` direct `group_progress.current_activity_id` a true duplicate of `_roadmap_cursor.current_activity_id(group)` (`:2505…:2866`), or a legitimate pre-normalization alias? Needs one 50-line read of `:1046-1094`. (Carry-over 11→34, actionable.)
9. Seam-spec: keep S-numbers with the iteration-28 span pins, or retire them post-shrink? Recommend keeping with 28 spans as the pin table. (Carry-over 18→34.)
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
11. Security (from 26): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie/SECURE flags, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.
12. Branch anomaly: supervisor passes run on `supervisor/aulalista-docs`, not `updated-tech` per the prompt's "Work starts on" line (carry-over 9→34). Confirm whether future passes should switch branches or amend the prompt — switching with a dirty Phase A–E tree is unsafe, so the anomaly persists until a human directs otherwise.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Human reviews/commits the Phase A–E tree first — it is the load-bearing blocker for every downstream step (clean base ref, C1–C5 landing, R1→R4 queue).
3. Land the five R1 doc-precision patches (C1 three-site + draft pick updated with the `:56-62` declared-intent quote, the three-way ADR==docstring≠code framing new at 34, and the `:119-127` overlap rule; C2–C5) plus the P1/P2 pending-row names as the first committed work once a base ref exists; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface.
4. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23, reframed at 32/33/34) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface (with overlap rendering) + iteration-25 P1/P2 rows + iteration-28 S-span pins and `:1068` cursor verdict before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order. Per Q8 (settled at 30), the upgrade rides as handoff Markdown in the docs-only PR, never as a created issue.
5. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
6. Refresh the loop prompt with the qualified #98 sentence, current line cites (six-issue set with #98 sole on-path at 0/7; join `staging_validation.py:76-77` + declared-intent `:56-62` + three-way C1 framing (ADR-0010 §Decisión-2 == docstring `:192` ≠ code `:201-205`) + overlap rule `test_t54:119-127` + writes `views.py:2221-2222,2383-2384` + call sites `:2343,2346/:2423,2426`; cursor `:1068` vs `:2505…:2866`; `curriculum_import.py:23`; template `item.index` vs `item.id`; head 0029; 42 test files; `check_migrations.py` OK; AST views 91 top-level), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, the 7-slot draft rubric, and settled Q8.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: C1 three-way — ADR-0010 §Decisión-2 + docstring `:190-196` vs code `_norm` `:25-26` vs `:201-202` vs serialization `:203-205` vs `by_title` `:232` + declared-intent `:56-62` + join `:76-77` + overlap rule `test_t54:119-127`; join writes `views.py:2221-2222,2383-2384` + call sites `views.py:2343,2346/:2423,2426`; C2 `DATABASE.md:103-105`; C3 `models.py:1875` vs flat `schemas/`; C4 `implementation-current.md:3-6` vs HEAD `bef32fd`; C5 ADR-0006 `:29` vs `teacher-flow.md:107-120`; `views.py` 2950 / AST 91 top-level defs; cursor `views.py:1068` vs 7 service sites; `roadmap_cursor.py` 27/1-def; `results.py` 552; `models.py` 2038, `CurriculumImportJob :1760` (no Topic/Subtopic/ActivityProposal tables), `ClassroomSession :762-1230` + `:1233/:1253`, `PublishedPackageSnapshot :376`, `EditorialReviewer` `:36/:308/:1961`, DemoPackage `:121/:137`; `models.py:1130` `in_bulk`, `curriculum_import.py:23` timeout; template `item.index` vs `item.id`; `schemas/` flat; migrations head 0029; 42 test files; `check_migrations.py` OK; six-issue `ready-for-agent` set with #98 sole on-path at 0/7), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; ambiguous groups may overlap exact pairs (`test_t54:119-127`) and the surface must render overlap with exact-membership checked first; named surface + P1 (join-agreement, pinning the exact-vs-`_norm` boundary per the `:56-62` refinement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only, M2 re-runnable with C1 scope stated, M3 flagged read, M4 separate ticket with named export artifact + restore runbook); seam slices (S5→S4→S2, S1-LAST-fused-with-M3) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 35): continue the rotating phase loop (suggested: tests, evidence, acceptance matrix, following the 21→28 cycle order). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, `:1068` resolved, settings hardened) and whether the gate moved. Checkpoint duties next due at iteration 40 (cumulative deltas 31–40 + gate review + docs-only PR push packaging handoffs 0031–0040); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push. This handoff (`supervisor-iteration-0034.md`) remains untracked in the working tree for packaging at the iteration-40 checkpoint into PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged — https://github.com/eliancanul/AulaLista/pull/112), never merged.
