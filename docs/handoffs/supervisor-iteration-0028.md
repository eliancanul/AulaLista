# Supervisor iteration 0028 — god-files, service seams, maintainability

Iteration: 28 | Phase focus: god-files, service seams, and maintainability specs
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–27)

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
?? docs/handoffs/supervisor-iteration-0021.md
?? docs/handoffs/supervisor-iteration-0022.md
?? docs/handoffs/supervisor-iteration-0023.md
?? docs/handoffs/supervisor-iteration-0024.md
?? docs/handoffs/supervisor-iteration-0025.md
?? docs/handoffs/supervisor-iteration-0026.md
?? docs/handoffs/supervisor-iteration-0027.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `cc95426` (iteration-20 PR-record append); gate log tip still `606aa64` for `IMPLEMENTATION-GATE.md` (iteration-20 HOLD revert) — no third flip observed. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) stands — no PR duty until iteration 30.

Prior memory: `supervisor-iteration-0027.md` (schemas/migration, C3 closed by direct re-read, `$id` consistency) + `-0026.md` (security envelope) + `-0025.md` (A1–A9 + P1/P2 pending rows) + `-0018.md` (last god-files/seams pass; S1-LAST-fused-with-M3, 91 defs) + `supervisor-cumulative.md` (spine 2→20) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`).

## Scope

Phase-focus: re-verify the iteration-8/18 god-file map and service-seam extraction order against current code, not against prior handoffs. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 30). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`supervisor-iteration-0027.md` (full) + `-0026.md` (status block + Q12) + `-0018.md` claims via cumulative §0018 (not full re-read; tree unchanged so spans re-derived directly) + `IMPLEMENTATION-GATE.md` + `supervisor-cumulative.md` (carried, not edited); `curriculum/views.py` AST map (top-level def count + session/import/result spans) + `views.py:74-90` (service imports) + `:2420-2474` (`_grouped_activities` + `_import_action_convert`, full re-read) + `:2505,:2579,:2599,:2634,:2770,:2807,:2866` (cursor call sites via grep) + `:1068` (direct cursor-attribute read, re-read in grep context); `curriculum/services/roadmap_cursor.py` (27, full) + `services/__init__.py` (empty) + `services/results.py` def count (12); `curriculum/models.py` class-size map (21 classes, `ClassroomSession` 469l); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `ls curriculum/migrations/` tail (head still 0029); `ls tests/test_*.py | wc -l` → 42; `git log --oneline -5 -- IMPLEMENTATION-GATE.md`, `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–27; migrations head still 0029; `schemas/` still flat; 42 test files; `git diff --stat` identical (+209/−716); status differs from iteration 27 only by the addition of untracked `supervisor-iteration-0027.md` (the expected own-handoff delta, now `supervisor-iteration-0028.md` pending). No Phase A–E commit, no C1–C5 wording fix, no new service module, no hash wiring, no head advance.
2. **God-file map re-verified, no growth (observed — phase deliverable).** `views.py` top-level defs = 91 via AST (total incl. nested = 95; iteration 18's "91 defs" is the top-level count — methodology confirmed, zero drift). `models.py` 21 classes / 66 total defs incl. methods. Largest units unchanged: `ClassroomSession` 469 lines (`models.py:762-1230`; iteration 18 cited 470 — 1-line counting variance, not a code change; `wc -l` total 2038 identical), `tutor_sessions` 101 lines (`views.py:774-874`), `tutor_import_detail` 89 lines (`:1946-2034`), `_import_action_add_missing_activities` 90 lines (`:2328-2417`), `_run_import_job_stage_once` 87 lines (`:1576-1662`). No new god-file; no split landed.
3. **Service-seam state unchanged: two-module exemplar, not a layer (observed).** `services/results.py` 552 lines / 12 defs + `services/roadmap_cursor.py` 27 lines / 1 def (`current_activity_id`), imported once (`views.py:74-75`, re-read `:74-90`: 1 cursor import + 11 `results` names). `services/__init__.py` empty. S3 (`roadmap_cursor`) remains the delegate-shape exemplar: read-only, never writes or advances (docstring re-read this pass). No second cursor module, no new service.
4. **Cursor call-site census with a named duplication candidate (observed — new precision this pass, advances Q9).** Seven service call sites: `views.py:2505,:2579,:2599,:2634,:2770,:2807,:2866` (grep, all `_roadmap_cursor.current_activity_id(group)`), plus ONE direct attribute read at `:1068` (`current_id = group_progress.current_activity_id` inside `tutor_session_active`). That `:1068`-vs-service pair is the concrete duplicated-cursor-resolution candidate the loop prompt's "duplicated cursor logic" claim has lacked since iteration 11. Hypothesis (not yet verified by full read of `:1046-1094`): `:1068` may be a legitimate local alias before normalization rather than a true duplicate — the S-spec must read `:1046-1094` fully before declaring it a seam violation. Recommendation: name this pair in the prompt refresh instead of dropping the claim; verification is one 50-line read.
5. **Staging-adjacent seam still index-based, hash unwired (observed).** `_grouped_activities` (`:2420-2443`, 24l) still builds entries as `{"id": _activity_id(entry, index), "index": index, ...}` (`:2428`) — stable-id helper present at render level but convert (`:2446-2474`, 29l) still resolves positionally (`job.activities[int(index)]` at `:2456`). No dedup badges emitted (`:2420-2444` carries the iteration-15/27 verdict; re-read confirms no `find_duplicate_groups` import or call). R2 (A5a convert-to-`activity_id` + A5b template `item.index→item.id`) remains the mandatory pre-seam slice; S-work that touches `_grouped_activities`/convert before R2 lands is double churn.
6. **S-number pinning refreshed to current spans (observed — advances Q10).** Current def spans this pass: S5-candidate session surface `tutor_sessions :774-874` + `tutor_session_review :996-1041` / `tutor_session_active :1046-1094`; S4-candidate import actions `_import_action_extract :2037-2080` / `confirm_topics :2083-2128` / `generate_activities :2190-2257` / `add_missing :2328-2417` + `_grouped_activities :2420-2443` + convert `:2446-2474`; S2-candidate result surface `tutor_results :1197-1258` + `_result_export_payload :1349-1367` + `tutor_session_export :1400-1455`. Extraction order S5 → S4 → S2, S1 LAST fused with M3 (never before) re-confirmed — S1 is the JSON-read cutover and cannot precede the relational backfill without rewriting both sides.
7. **Gate: no edit, HOLD carries (decision by rule).** No third flip (log tip `606aa64`); iteration-20 2.5/6 scorecard and HOLD stand. Gate review + cumulative deltas (21–30) + docs-only PR push next due at iteration 30, not now.
8. **Fused-decision spine unchanged (observed + carry).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite (green carries; not re-run this pass — phase was seams, iteration 27 re-ran it OK), #58 stale, #55/#56/#65 peripheral. #98 stays the sole staging-path `ready-for-agent` candidate at 0/7 (iteration-19 rubric, carried — issue bodies not re-read, tree unchanged so no re-grade possible). C1–C5 + P1/P2 rows carry unmodified (not re-read this pass; schemas/migration was iteration 27's job).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **No gate edit, no cumulative edit, no PR this pass** — non-checkpoint iteration per loop rules.
- **Seams contribution (this pass, no code):** god-file sizes frozen (91 top-level defs, largest units byte-identical modulo 1-line counting variance on `ClassroomSession`); services/ still a two-module exemplar with S3 read-only; cursor census 7-service-vs-1-direct names the Q9 pair (`:1068` vs `:2505…:2866`) pending a 50-line verification read; S5/S4/S2 spans re-pinned to current lines advancing Q10; R2-before-seams ordering re-affirmed with the `:2428`/`:2456` index cites.
- **Cite discipline re-affirmed:** current lines only (seams: `views.py:74-90` imports, `:774-874` sessions, `:996-1094` review/active with `:1068` candidate, `:1197-1258` results, `:1946-2034` import detail, `:2037-2417` actions, `:2420-2443` grouped, `:2446-2474` convert positional `:2456`; `roadmap_cursor.py` 27/1-def; `results.py` 552/12-defs; `models.py:762-1230` 469l session class; head 0029; 42 test files); prompt's stale pre-shrink numbers remain superseded.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→28.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? Two unamended flips is a pattern. (Carry-over 11→28.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→28.)
4. Agent-ready (C1, draft pick at 23, three-site at 24, P1/P2 rows at 25): confirm `_norm`-join + outer-keys-only hash, or take the exact-join-intentional alternative with inverted P1? Precedes backfill AND staging-adjacent seams. (Carry-over 3→28.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list, `llm_log` audit copy. Enforcement gap until picked; P2 has nowhere to render without it. (Carry-over 5→28.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→28.)
7. Agent-ready (C3, directly re-verified at 27): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→28.)
8. Draft-quality: should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→28.)
9. Evidence debt (advanced this pass): is `views.py:1068` direct `group_progress.current_activity_id` a true duplicate of `_roadmap_cursor.current_activity_id(group)` (`:2505…:2866`), or a legitimate pre-normalization alias? Needs one 50-line read of `:1046-1094`; then either file it as an S-candidate or drop the loop-prompt claim. (Carry-over 11→28, now actionable.)
10. Seam-spec (advanced this pass): S5/S4/S2 spans re-pinned at 28 (`:774-874`, `:996-1094`, `:1197-1258`/`:1400-1455`, `:2037-2474`); remaining step is retiring vs keeping S-numbers post-shrink — recommend keeping with this pass's spans as the pin table. (Carry-over 18→28.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
12. Security (from 26): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie/SECURE flags, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Land the five R1 doc-precision patches (C1 three-site + draft pick, C2–C5) plus the P1/P2 pending-row names as docs-only PR content at iteration 30; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface. This pass adds no new R1 item — the seam re-verification confirms R1 stays docs-only with no code touch, and adds the `:1068` verification read as a pre-seam (not pre-R1) step.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23) + iteration-15 A5a/A5b split + corrected timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface + iteration-25 P1/P2 rows + iteration-28 S-span pins and `:1068` cursor verdict before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist. Institutional hardening (iteration 26 finding 2 + question 12) is an explicit non-goal of the staging lane.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (seams: `views.py:74-90`, `:774-874`, `:996-1094` with `:1068` candidate, `:2420-2443`, `:2446-2474` positional `:2456`; `roadmap_cursor.py` 27/1-def with 7 call sites `:2505…:2866`; `ClassroomSession` `models.py:762-1230`; head 0029; 42 test files), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / 91 top-level defs; seams `views.py:74-90`, `:774-874`, `:996-1094` (`:1068` candidate), `:1197-1258`, `:1946-2034`, `:2037-2417`, `:2420-2443` (`:2428` id/index), `:2446-2474` (positional `:2456`); `roadmap_cursor.py` 27 lines / 1 def / 7 call sites; `results.py` 552 / 12 defs; `models.py` 2038, `ClassroomSession :762-1230`; `models.py:1130` `in_bulk`, `:1875` C3 path caveat; `staging_validation.py` hash `:189-208`, dedup `:211-238`, join `:76-77`; `schemas/` flat; migrations head 0029; 42 test files; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; template `item.index :148` vs `item.id :157`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; named surface + P1 (join-agreement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only, M2 re-runnable with C1 scope stated, M3 flagged read, M4 separate ticket with named export artifact + restore runbook); seam slices (S5→S4→S2, S1-LAST-fused-with-M3) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 29): resume the rotating phase loop (suggested: ready-for-agent ranking/draft-quality re-check, or tests/evidence A1–A9 re-verification). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired into the pipeline, P1/P2 tests added, `:1068` cursor pair resolved, settings hardened) and whether the gate moved a third time. Checkpoint duties next due at iteration 30 (cumulative deltas 21–30 + gate review + docs-only PR push packaging handoffs 0021–0030); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push, no new PR. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) untouched this pass.
- This handoff (`supervisor-iteration-0028.md`) remains untracked until the iteration-30 checkpoint packages it with 21–30 per the docs-only PR rule.
