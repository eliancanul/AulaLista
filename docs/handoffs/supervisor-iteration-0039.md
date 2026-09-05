# Supervisor iteration 0039 — ready-for-agent ranking and issue draft quality

Iteration: 39 | Phase focus: ready-for-agent ranking and issue draft quality
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–38)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

(`git diff --cached --name-only` → empty at pass start. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 OPEN, unmerged.)

Prior memory: `supervisor-iteration-0038.md` (Q8 CLOSED: `views.py:1068` alias-with-missing-fallback) + `supervisor-cumulative.md` (spine 2→30, deltas 21–30) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6).

## Scope

Non-checkpoint rotating-phase pass (ready-for-agent ranking / issue draft quality, per the 21→28 cycle order and the iteration-38 §Next move). Spec only — nothing implemented, no issue created/edited/labeled, no gate edit, no cumulative edit, no PR push (checkpoint duties next due at iteration 40). This pass re-grades the six-issue `ready-for-agent` set against the 7-slot rubric ONLY if a body changed, otherwise carries the iteration-29 verdict per loop discipline, and spends the pass budget on draft-quality precision for the standing #98 upgrade.

## Files inspected

`supervisor-iteration-0038.md` (full) + `supervisor-cumulative.md` (spine + deltas 21–30 headers) + `IMPLEMENTATION-GATE.md` (status + scorecard lines only, no edit); `docs/adr/0010-staging-relacional-idempotente.md` (full re-read, 58 lines); `CONTEXT.md` + `DESIGN.md` + `AGENTS.md` + `docs/DATABASE.md` + `docs/implementation-current.md` + `docs/teacher-flow.md` (full re-reads per loop rules, no spine contradictions beyond standing R1 items C2/C4); live evidence: `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127 — byte-identical to iterations 2–38); `gh issue list --label ready-for-agent` + `gh issue view 98` (updatedAt check, no body re-read — see Finding 2); greps: title-keyed staging writes (re-pinned at `views.py:2221-2222,2383-2384` via `sed` re-read this pass), service import `views.py:74`, `_roadmap_cursor` 7 sites, `_grouped_activities :2420` + `_import_action_*` defs; direct `sed` reads `:2218-2225`, `:2380-2390`, `:1066-1070` (Q8 re-confirmation); `in_bulk` at `models.py:1130` (N+1-fixed note re-confirmed); `SCHEMA_VERSION v1` (`staging_validation.py:16` + `schemas/README.md:10`); `ls curriculum/schemas/` (flat, README + 3 `.schema.json`, no `v2/`); `ls curriculum/services/` (two modules + `__init__`); migrations tail (head still 0029); `python3 scripts/check_migrations.py` → OK (re-run this pass); `ls tests/test_*.py | wc -l` → 42; `gh pr list --head supervisor/aulalista-docs` → PR 112 OPEN. `pytest` unrunnable here (no `.venv`); ranking claims are by reading + timestamp evidence.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–38; head still 0029; `schemas/` still flat; `services/` still two modules; `check_migrations.py` OK; 42 test files; `git diff --stat` identical (+209/−716); status shape identical modulo the now-present untracked `supervisor-iteration-0038.md`. No M1 commit, no backfill, no read-cutover, no JSON-drop, no `v2/`, no hash wiring, no head advance, no seam extraction, no `:1068` service routing. Nineteenth consecutive no-drift pass (21–39).
2. **Issue bodies unchanged → no re-grade due (observed, NEW timestamp datum at 39).** `gh issue list --label ready-for-agent` returns the same six-issue set (#95/#97/#98/#103/#104/#107); every `updatedAt` is August 2026 (`#98` at `2026-08-28T02:37:01Z`, identical to the iteration-29 full-body re-read). Per loop discipline ("do not repeat a conclusion without checking whether the code/docs changed"), the iteration-29 verdict carries without a body re-read: **#98 remains sole on-path at 0/7** under the 7-slot rubric (governing ADR/spec, exact allowed paths, explicit out-of-scope, invariants preserved, named acceptance tests, migration/rollback plan, concrete base ref). No slot flipped because no body, tree line, or gate condition moved. The other five remain off-path (Dirección A/B #95/#103/#104/#107, cancel-help #97) with unchanged titles.
3. **Title-join + C1/C3 standing items re-pinned, untouched by this phase (observed, direct re-read).** Staging writes re-read at `views.py:2221-2222` (`topic_title`/`subtopic_title` from `topic["titulo"]`/`sub["titulo"]`) and `:2383-2384` (top-up variant with `added_by_topup: True`); join predicate `staging_validation.py:76-77` (exact `==`) with declared-intent `:56-62` and `by_title :226-235` unchanged. C1 three-way asymmetry (ADR-0010 §Decisión-2 == docstring `:192` ≠ code `:201-205`) and C3 `models.py:1875` flat-path wording carry as R1 doc-precision items. N+1-fixed note re-confirmed (`models.py:1130` `in_bulk`). Root docs re-read clean (C2 `DATABASE.md:103-105` + C4 `implementation-current.md:3-6` staleness already R1 items, unchanged).
4. **Q8 closure feeds the draft, not a re-grade (observed, re-confirmation).** `:1066-1070` re-read: `if group_progress:` guard + direct `group_progress.current_activity_id` (`:1068`) + local `ordered_activities` position (`:1069-1070`), vs 7 service sites (`:2505…:2866`) via `roadmap_cursor.py:17-27` (same read + first-`ACTUAL`-of-`states()` fallback + `None`-group guard). Iteration-38 verdict stands: alias-with-missing-fallback, remediation is one-line accessor routing post-R2. Draft-quality impact only: the #98 upgrade must cite the Q8 verdict so a future seam slice does not route `:1068` pre-R2.
5. **Gate and PR unmoved (observed, not edited).** `IMPLEMENTATION-GATE.md` still `STATUS: HOLD` (2.5/6). PR 112 OPEN, unmerged. The parallel coding lane does nothing while the gate is `HOLD` or absent.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate: HOLD observed at iteration 39** (no edit — checkpoint-only file per loop rules). Next gate review due at iteration 40.
- **Ranking carried, not recomputed:** #98 sole on-path at 0/7 (bodies timestamp-unchanged since the iteration-29 full re-read). Re-grading without a body change would be re-derivation cost with zero information gain.
- Draft-quality precision added instead (see §Ranked recommendations items 3–4 and the sharpened acceptance criteria): the #98 upgrade checklist now explicitly requires the Q8 citation, the P1/P2 placement pins, and the M4-artifact + runner-name blanks to be filled before any coding lane starts.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→39.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? (Carry-over 11→39.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→39.)
4. Agent-ready (C1, three-way framing at 34, re-verified at 35/36/37/38/39): confirm `_norm`-join + outer-keys-only hash, or keep exact reads with P1 pinning the exact-vs-`_norm` disagreement? (Carry-over 3→39.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list (with explicit overlap rendering per `test_t54:119-127`), `llm_log` audit copy. (Carry-over 5→39.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→39.) Load-bearing for the M4 rollback runbook.
7. Agent-ready (C3, re-verified at 27/34/35/36/37/38/39): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→39.)
8. ~~Evidence debt Q8~~ — CLOSED at 38 (alias-with-missing-fallback; route `:1068` through the service accessor post-R2). Draft must cite it; no further read debt on this pair.
9. Seam-spec: keep S-numbers with the iteration-28 span pins, or retire them post-shrink? Recommend keeping with 28 spans as the pin table. (Carry-over 18→39.)
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps. (`supervisor-prompt-catalog.md` also absent — checkpoint duty at 40 must create it, not this pass.)
11. Security (from 26, re-verified at 36): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie `Secure` flip on HTTPS, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.
12. Branch anomaly: supervisor passes run on `supervisor/aulalista-docs`, not `updated-tech` per the prompt's "Work starts on" line (carry-over 9→39). Confirm whether future passes should switch branches or amend the prompt — switching with a dirty Phase A–E tree is unsafe, so the anomaly persists until a human directs otherwise.
13. Matrix execution (from 35): where does the A1–A9 + P1/P2 green run execute before wiring, given `pytest` is unrunnable in this supervisor environment (no `.venv`)? Name the runner (coding-lane env or CI) in the #98 upgrade.
14. Draft-quality (NEW at 39, for the iteration-40 checkpoint): does the #98 upgrade draft require the M4-artifact pick (Q6) and the runner name (Q13) filled BEFORE the R1 precision slice lands, or may R1 land docs-only while those two blanks stay open? Recommend R1-may-land (docs-only, no wiring risk) with Q6/Q13 marked as pre-R2 blockers.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Human reviews/commits the Phase A–E tree first — it is the load-bearing blocker for every downstream step (clean base ref, C1–C5 landing, R1→R4 queue).
3. Land the five R1 doc-precision patches (C1 three-site + draft pick with the `:56-62` declared-intent quote, three-way ADR==docstring≠code framing, and the `:119-127` overlap rule; C2–C5) plus the P1/P2 pending-row names as the first committed work once a base ref exists; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface. R1 may land with Q6/Q13 still open (docs-only); Q6/Q13 become pre-R2 blockers, not pre-R1.
4. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23, reframed at 32/33/34) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface (with overlap rendering) + iteration-25 P1/P2 rows (placed: `test_t54` beside `:119-127`, P1 boundary + P2 guard-order) + iteration-28 S-span pins and the iteration-38 Q8 verdict (alias-with-missing-fallback at `views.py:1068` vs 7 service sites, route-through-service post-R2) + iteration-36 security pins (`views.py:125-142` gate, `:158-176` sealed cookies, `urls.py:228-229` minimal DEBUG block) + iteration-37 rollback table (M1 reverse-migrate / M2 truncate+re-run JSON-authoritative / M3 flag-off / M4 export-gated) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order. Per Q8 (settled at 30), the upgrade rides as handoff Markdown in the docs-only PR, never as a created issue. Draft-quality bar: every one of the 7 slots must cite a current line or be marked BLANK-with-owner (M4 artifact → Q6 owner; runner → Q13 owner) — a draft with an unmarked blank is not rankable above 0/7.
5. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist. The Q11 hardening checklist gets a named owner + runbook location but no lane or ticket until the staging slice lands.
6. Refresh the loop prompt with the qualified #98 sentence, current line cites (six-issue set with #98 sole on-path at 0/7 with `updatedAt 2026-08-28T02:37:01Z` carry-rule; join `staging_validation.py:76-77` + declared-intent `:56-62` + three-way C1 framing (ADR-0010 §Decisión-2 == docstring `:192` ≠ code `:201-205`) + overlap rule `test_t54:119-127` + P1/P2 placement + writes `views.py:2221-2222,2383-2384` + call sites `:2343,2346/:2423,2426`; cursor verdict CLOSED at 38 (`views.py:1068` alias-with-missing-fallback vs 7 service sites `:2505…:2866`, `roadmap_cursor.py:17-27`); `curriculum_import.py:23`; template `item.index :148` vs `item.id :157`; schemas flat + `$id` v1 + `models.py:1875` C3 + head 0029 additive-nullable + `check_migrations.py` OK; 42 test files; AST views 91 top-level / models 5 top-level, services two-module exemplar `views.py:74-75`; 7-slot draft rubric with carry-rule (re-grade only on body/tree/gate change) + blank-with-owner bar; settled Q8), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, the M4 artifact question, and the missing-`prompt-catalog` creation duty at the iteration-40 checkpoint.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / AST 91 top-level defs / 21 classes + `models.py` 2038 / 5 top-level defs + service import `:74-75` + `_grouped_activities :2420` + convert `:2446` + writes `:2221-2222,:2383-2384` + join `staging_validation.py:76-77` with declared-intent `:56-62` + Q8 `:1066-1070` vs `roadmap_cursor.py:17-27`; schemas flat README + 3 `.schema.json` + `$id` v1 + `SCHEMA_VERSION v1 :16` + `models.py:1875` C3 path caveat + `clean()` non-empty-only + no `save()` override; 0029 additive-nullable head + 0028 dependency; zero Topic/Subtopic/ActivityProposal tables; `check_migrations.py` OK; hash + dedup + `_norm` + `by_title :226-235`; matrix files t15/t16/t19/t20/t22/t24 + `test_t54` 127 lines/5 tests + overlap rule `:119-127` + P1/P2 placement; `models.py:1130` `in_bulk`; `curriculum_import.py:23` timeout; template `item.index :148` vs `item.id :157`; 42 test files; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; six-issue `ready-for-agent` set with #98 sole on-path at 0/7 with `updatedAt` carry-rule datum `2026-08-28T02:37:01Z`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + Ollama-only egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness with blank-with-owner bar (unmarked blank = 0/7 ceiling); named matrix run (runner per Q13: coding-lane env or CI — supervisor env has no `.venv`) green including P1+P2 BEFORE wiring; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; ambiguous groups may overlap exact pairs (`test_t54:119-127`) and the surface must render overlap with exact-membership checked first (P2 pins guard order); named surface + P1 (join-agreement, pinning the exact-vs-`_norm` boundary per the `:56-62` refinement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only reverse-migratable, M2 re-runnable truncate+re-run with JSON still authoritative and C1 scope stated, M3 flagged read with flag-off rollback, M4 separate ticket with named export artifact + restore runbook answering Q6); seam slices (S5→S4→S2, S1-LAST-fused-with-M3, plus the `:1068`-through-service routing post-R2) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- Security non-regression per ticket: no new egress beyond Ollama localhost, no CDN/remote fetch, no `Secure`-breaking cookie change, no auth-gate weakening, no `*` hosts / DEBUG-True / dev-SECRET promotion beyond local; the Q11 institutional checklist stays out of staging tickets.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 40): CHECKPOINT — (a) cumulative deltas 31–40 in `supervisor-cumulative.md` (deltas only), (b) gate review in `IMPLEMENTATION-GATE.md` (expected HOLD with cause unless the Phase A–E tree was human-committed), (c) create `supervisor-prompt-catalog.md` with the ten rotating phase prompts, iteration references, and evidence-based outcomes, (d) package only the Markdown docs on `supervisor/aulalista-docs` into a pushed, non-merged PR when safe (verify `git diff --cached --name-only` shows docs-only before commit; never `git add -A`, never stage code, never merge/approve/close), and record the PR URL/number in the cumulative handoff. Final synthesis at iteration 100 — not due now. Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, `:1068` routed through service, settings hardened, `Secure`/validator flags added, `check --deploy` run recorded) and whether the gate moved.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push. This handoff (`supervisor-iteration-0039.md`) remains untracked in the working tree for packaging at the iteration-40 checkpoint into PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged — https://github.com/eliancanul/AulaLista/pull/112), never merged.
