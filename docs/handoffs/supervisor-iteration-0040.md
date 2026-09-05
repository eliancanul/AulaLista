# Supervisor iteration 0040 — CHECKPOINT: synthesis, gap analysis, next-loop handoff

Iteration: 40 | Phase focus: synthesis, gap analysis, and next-loop handoff
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–39)

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
?? docs/handoffs/supervisor-iteration-0035.md
?? docs/handoffs/supervisor-iteration-0036.md
?? docs/handoffs/supervisor-iteration-0037.md
?? docs/handoffs/supervisor-iteration-0038.md
?? docs/handoffs/supervisor-iteration-0039.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

(`git diff --cached --name-only` → empty at pass start. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 OPEN, unmerged.)

Prior memory: `supervisor-iteration-0031…0039.md` (rotating-phase re-verifications + ranking) + `supervisor-iteration-0030.md` (prior checkpoint, deltas 21–30) + `supervisor-cumulative.md` (spine 2→30) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6).

## Scope

CHECKPOINT iteration per loop rules: (a) synthesis handoff with gap analysis, (b) `supervisor-cumulative.md` extended with deltas only (31–40), (c) `supervisor-prompt-catalog.md` created with the ten rotating phase prompts, iteration references, and evidence-based outcomes, (d) `IMPLEMENTATION-GATE.md` reviewed (flip only if all six conditions hold simultaneously, else re-affirm HOLD), (e) only staged `docs/handoffs/` + `docs/adr/` Markdown packaged on `supervisor/aulalista-docs` into a pushed, non-merged PR when safe. Spec only — nothing implemented, no issue created/edited/labeled. Final synthesis at iteration 100 — not due now.

## Files inspected

`supervisor-iteration-0031…0039.md` (Decisions sections of each + full re-read of -0038/-0039); `supervisor-iteration-0030.md` (full, prior checkpoint); `supervisor-cumulative.md` (full, edited this pass); `IMPLEMENTATION-GATE.md` (full, reviewed this pass); `CONTEXT.md` + `DESIGN.md` + `AGENTS.md` (full); `docs/DATABASE.md` + `docs/implementation-current.md` + `docs/teacher-flow.md` (headers + standing R1 sections); `docs/adr/0010-staging-relacional-idempotente.md` (full, 58 lines); `ls docs/adr/` (10 files, 0001–0010, unchanged); live evidence: `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127 — byte-identical to iterations 2–39); `ls curriculum/schemas/` (README + 3 `.schema.json`, flat, no `v2/`); `ls tests/test_*.py | wc -l` → 42; `python3 scripts/check_migrations.py` → OK (re-run this pass); `gh issue list --label ready-for-agent` (same six: #95/#97/#98/#103/#104/#107; #98 `updatedAt 2026-08-28T02:37:01Z`, unchanged — carry-rule applies, no body re-read); `gh pr list --head supervisor/aulalista-docs` → PR 112 OPEN; `git log` (HEAD `1b4088f`, gate history `bef32fd`/`606aa64` — no third flip). `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence across all ten passes 31–40 (observed).** Every `wc -l` count byte-identical to iterations 2–30; migrations head still 0029; `schemas/` still flat; `check_migrations.py` OK (re-run this pass); 42 test files; `git diff --stat` identical (+209/−716); status differs from iteration 30 only by nine untracked own-handoffs (0031–0039 pending + this file). No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no hash wiring, no head advance, no settings hardening, no new service module, no P1/P2 tests, no `:1068` routing. Twenty-nine consecutive no-drift passes (12–40 with full fingerprints; 2–11 equivalent by prior record).
2. **Gate unmoved a third time (observed).** Log shows no gate commit since `bef32fd` (iteration-30 checkpoint); 2.5/6 scorecard carries after live re-check this pass: (a) tree human-reviewed/committed → OPEN (Phase A–E tree still uncommitted); (b) narrowed paths → MET; (c) convert+test → HALF; (d) base ref + reachable evidence → HALF (`coding-41560047f83c.md` still unreachable from this branch); (e) open picks answered → OPEN (C1/report-surface/M4); (f) zero blockers → OPEN. HOLD re-affirmed with cause, not by inertia.
3. **`ready-for-agent` set unchanged at six, carry-rule applies (observed).** `gh` returns exactly #95/#97/#98/#103/#104/#107 — same six as iterations 19/29/30/39. #98 `updatedAt` identical to the iteration-29 full-body re-read, so the 0/7 verdict carries without re-derivation per loop discipline. Only #98 sits on the staging critical path.
4. **Gap analysis — what 31–40 added vs what is still missing (decision input).** Each pass 31–39 contributed one sharpening without touching code: 31 baseline (CONTEXT/DESIGN resolve to live anchors, no re-modeling needed); 32 C1 refinement (`:56-62` declared-intent baseline reframes the pick as `_norm`-join vs exact-reads-with-`_norm`-report + P1 boundary test); 33 overlap rule (`test_t54:119-127` — ambiguous groups overlap exact pairs, guard checks exact-membership first); 34 three-way C1 framing (ADR == docstring ≠ code — R1 must touch all three sites); 35 P1/P2 placement (both in `test_t54` beside `:119-127`, P1 boundary + P2 guard-order); 36 security pins (`views.py:125-142` gate, sealed cookies, `urls.py:228-229` DEBUG block) + M4 rollback table seed; 37 per-step rollback pins (M1 reverse-migrate / M2 truncate+re-run JSON-authoritative / M3 flag-off / M4 export-gated); 38 Q8 CLOSED (`views.py:1068` alias-with-missing-fallback, route-through-service post-R2); 39 draft-quality bar (7-slot rubric with blank-with-owner rule — unmarked blank = 0/7 ceiling). Still missing (all human-gated): Phase A–E review/commit, C1 pick, report-surface pick, M4 artifact pick (Q6), runner name (Q13), loop-rule amendment for off-cycle flips, gate traceability, hardening owner (Q11). The spec side is as precise as read-only work can make it; every remaining item needs a human decision or a code-touching lane.
5. **Root-doc re-read: no spine contradictions (observed).** ADR-0010 (fused #53/#98/#54, M0→M4, #57 prerequisite, rule #58) consistent with CONTEXT authority boundaries and DESIGN Dirección C + LAN-only/no-CDN. Two staleness notes carry as R1 items, not edited (root docs out of scope): `implementation-current.md:3-6` header (`main`/`d4fcb99`, C4); `DATABASE.md:103-105` relational-debt note without ADR-0010 pointer (C2).
6. **PR 112 stands OPEN (observed).** `supervisor/aulalista-docs` → `main`, docs-only, unmerged. This checkpoint pushes handoffs 0031–0040 (+ cumulative deltas + HOLD re-affirmation + prompt catalog) onto the same branch per the docs-only PR rule.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate: HOLD re-affirmed at iteration 40** after live scorecard re-check (2.5/6; blockers observed non-none; no clean base ref). The parallel coding lane does nothing while the gate is `HOLD` or absent.
- **Q14 (NEW at 39, answered at 40):** R1 doc-precision slice may land with Q6 (M4 artifact) and Q13 (runner name) still open — docs-only, no wiring risk. Q6/Q13 become pre-R2 blockers, not pre-R1. Recorded in the gate review.
- **Checkpoint packaging:** this handoff + cumulative deltas 31–40 + new prompt catalog + HOLD gate review pushed docs-only on `supervisor/aulalista-docs`; PR 112 updated, never merged.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→40.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? (Carry-over 11→40.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→40.)
4. Agent-ready (C1, three-way framing at 34, `:56-62` baseline at 32, re-verified 35–40): confirm `_norm`-join + outer-keys-only hash, or keep exact reads with P1 pinning the exact-vs-`_norm` disagreement? (Carry-over 3→40.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list (with explicit overlap rendering per `test_t54:119-127`), `llm_log` audit copy. (Carry-over 5→40.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? Pre-R2 blocker per Q14, not pre-R1. (Carry-over 7→40.)
7. Agent-ready (C3, re-verified 27/34–40): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→40.)
8. ~~Evidence debt Q8~~ — CLOSED at 38 (alias-with-missing-fallback; route `:1068` through the service accessor post-R2). Draft must cite it.
9. Seam-spec: keep S-numbers with the iteration-28 span pins, or retire them post-shrink? Recommend keeping with 28 spans as the pin table. (Carry-over 18→40.)
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps. (`supervisor-prompt-catalog.md` created at this checkpoint.)
11. Security (from 26, re-verified at 36): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie `Secure` flip on HTTPS, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.
12. Branch anomaly: supervisor passes run on `supervisor/aulalista-docs`, not `updated-tech` per the prompt's "Work starts on" line (carry-over 9→40). Confirm whether future passes should switch branches or amend the prompt — switching with a dirty Phase A–E tree is unsafe, so the anomaly persists until a human directs otherwise.
13. Matrix execution (from 35): where does the A1–A9 + P1/P2 green run execute before wiring, given `pytest` is unrunnable in this supervisor environment (no `.venv`)? Pre-R2 blocker per Q14; name the runner (coding-lane env or CI) in the #98 upgrade.
14. ~~Draft-quality Q14~~ — ANSWERED at 40: R1 may land docs-only with Q6/Q13 open; both become pre-R2 blockers.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Human reviews/commits the Phase A–E tree first — it is the load-bearing blocker for every downstream step (clean base ref, C1–C5 landing, R1→R4 queue).
3. Land the five R1 doc-precision patches (C1 three-site + draft pick with the `:56-62` declared-intent quote, three-way ADR==docstring≠code framing, and the `:119-127` overlap rule; C2–C5) plus the P1/P2 pending-row names as the first committed work once a base ref exists; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface. R1 may land with Q6/Q13 still open (docs-only); Q6/Q13 become pre-R2 blockers, not pre-R1.
4. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23, reframed at 32/34) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface (with overlap rendering) + iteration-25 P1/P2 rows (placed: `test_t54` beside `:119-127`, P1 boundary + P2 guard-order) + iteration-28 S-span pins and the iteration-38 Q8 verdict (alias-with-missing-fallback at `views.py:1068` vs 7 service sites, route-through-service post-R2) + iteration-36 security pins (`views.py:125-142` gate, `:158-176` sealed cookies, `urls.py:228-229` minimal DEBUG block) + iteration-37 rollback table (M1 reverse-migrate / M2 truncate+re-run JSON-authoritative / M3 flag-off / M4 export-gated) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order. Per Q8 (settled at 30), the upgrade rides as handoff Markdown in the docs-only PR, never as a created issue. Draft-quality bar: every one of the 7 slots must cite a current line or be marked BLANK-with-owner (M4 artifact → Q6 owner; runner → Q13 owner) — a draft with an unmarked blank is not rankable above 0/7.
5. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist. The Q11 hardening checklist gets a named owner + runbook location but no lane or ticket until the staging slice lands.
6. Refresh the loop prompt with the qualified #98 sentence, current line cites (six-issue set with #98 sole on-path at 0/7 with `updatedAt 2026-08-28T02:37:01Z` carry-rule; join `staging_validation.py:76-77` + declared-intent `:56-62` + three-way C1 framing (ADR-0010 §Decisión-2 == docstring `:192` ≠ code `:201-205`) + overlap rule `test_t54:119-127` + P1/P2 placement + writes `views.py:2221-2222,2383-2384` + call sites `:2343,2346/:2423,2426`; cursor verdict CLOSED at 38 (`views.py:1068` alias-with-missing-fallback vs 7 service sites `:2505…:2866`, `roadmap_cursor.py:17-27`); `curriculum_import.py:23`; template `item.index :148` vs `item.id :157`; schemas flat + `$id` v1 + `models.py:1875` C3 + head 0029 additive-nullable + `check_migrations.py` OK; 42 test files; AST views 91 top-level / models 5 top-level, services two-module exemplar `views.py:74-75`; 7-slot draft rubric with carry-rule (re-grade only on body/tree/gate change) + blank-with-owner bar + Q14 (R1-may-land, Q6/Q13 pre-R2); settled Q8), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, the M4 artifact question, and the `prompt-catalog` now existing (created at 40).

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / AST 91 top-level defs / 21 classes + `models.py` 2038 / 5 top-level defs + service import `:74-75` + `_grouped_activities :2420` + convert `:2446` + writes `:2221-2222,:2383-2384` + join `staging_validation.py:76-77` with declared-intent `:56-62` + Q8 `:1066-1070` vs `roadmap_cursor.py:17-27`; schemas flat README + 3 `.schema.json` + `$id` v1 + `SCHEMA_VERSION v1 :16` + `models.py:1875` C3 path caveat + `clean()` non-empty-only + no `save()` override; 0029 additive-nullable head + 0028 dependency; zero Topic/Subtopic/ActivityProposal tables; `check_migrations.py` OK; hash + dedup + `_norm` + `by_title :226-235`; matrix files t15/t16/t19/t20/t22/t24 + `test_t54` 127 lines/5 tests + overlap rule `:119-127` + P1/P2 placement; `models.py:1130` `in_bulk`; `curriculum_import.py:23` timeout; template `item.index :148` vs `item.id :157`; 42 test files; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; six-issue `ready-for-agent` set with #98 sole on-path at 0/7 with `updatedAt` carry-rule datum `2026-08-28T02:37:01Z`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + Ollama-only egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness with blank-with-owner bar (unmarked blank = 0/7 ceiling) and Q14 (R1-may-land with Q6/Q13 open; both pre-R2 blockers); named matrix run (runner per Q13: coding-lane env or CI — supervisor env has no `.venv`) green including P1+P2 BEFORE wiring; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; ambiguous groups may overlap exact pairs (`test_t54:119-127`) and the surface must render overlap with exact-membership checked first (P2 pins guard order); named surface + P1 (join-agreement, pinning the exact-vs-`_norm` boundary per the `:56-62` refinement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only reverse-migratable, M2 re-runnable truncate+re-run with JSON still authoritative and C1 scope stated, M3 flagged read with flag-off rollback, M4 separate ticket with named export artifact + restore runbook answering Q6); seam slices (S5→S4→S2, S1-LAST-fused-with-M3, plus the `:1068`-through-service routing post-R2) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- Security non-regression per ticket: no new egress beyond Ollama localhost, no CDN/remote fetch, no `Secure`-breaking cookie change, no auth-gate weakening, no `*` hosts / DEBUG-True / dev-SECRET promotion beyond local; the Q11 institutional checklist stays out of staging tickets.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 41): resume the rotating phase loop from the top (baseline architecture/domain-contracts re-verification, following the 31→38 cycle order). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, `:1068` routed through service, settings hardened, `Secure`/validator flags added, `check --deploy` run recorded) and whether the gate moved. Checkpoint duties next due at iteration 50 (cumulative deltas 41–50 + gate review + docs-only PR push packaging handoffs 0041–0050); final synthesis at iteration 100 — neither is due now.

## PR record

- Checkpoint iteration: stage ONLY `docs/handoffs/*.md` (+ `docs/adr/*.md` if any changed — none this pass); verify `git diff --cached --name-only` shows Markdown docs only; commit; push `supervisor/aulalista-docs`; PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) updated, never merged. Record URL: https://github.com/eliancanul/AulaLista/pull/112.
- This handoff (`supervisor-iteration-0040.md`) + cumulative deltas 31–40 + new `supervisor-prompt-catalog.md` + HOLD re-affirmation ride in that push per the docs-only PR rule.
