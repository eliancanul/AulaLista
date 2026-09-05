# Supervisor iteration 0038 — god-files, service seams, and maintainability

Iteration: 38 | Phase focus: god-files, service seams, maintainability specs
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–37)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

(`git diff --cached --name-only` → empty at pass start. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 OPEN, unmerged.)

Prior memory: `supervisor-iteration-0037.md` (schemas/migration/rollback + per-step rollback pins) + `supervisor-iteration-0036.md` (security envelope + `urls.py:228-229` DEBUG-block datum) + `supervisor-cumulative.md` (spine 2→30, deltas 21–30) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6).

## Scope

Non-checkpoint rotating-phase pass (god-files/service-seams/maintainability, per the 21→28 cycle order and the iteration-37 §Next move). Spec only — nothing implemented, no issue created/edited/labeled, no gate edit, no cumulative edit, no PR push (checkpoint duties next due at iteration 40). This pass re-verifies the god-file footprint, the `services/` seam state, and the S1-LAST-fused-with-M3 ordering against current lines, and closes the Q8 cursor-remainder read (`views.py:1070-1094`).

## Files inspected

`supervisor-iteration-0037.md` (full) + `supervisor-cumulative.md` (spine + deltas 21–30 headers) + `IMPLEMENTATION-GATE.md` (status + scorecard lines only, no edit); `docs/adr/0010-staging-relacional-idempotente.md` (full re-read, 58 lines); `curriculum/services/roadmap_cursor.py` (full re-read, 27 lines); `CONTEXT.md` + `DESIGN.md` + `AGENTS.md` + `docs/DATABASE.md` + `docs/implementation-current.md` + `docs/teacher-flow.md` (full re-reads per loop rules, no spine contradictions beyond standing R1 items C2/C4); live greps: title-keyed staging writes (`views.py:2221-2222,2383-2384`), service import (`views.py:74-75`), `_roadmap_cursor` call sites (`:2505…:2866`, 7 sites), `_grouped_activities :2420` + `_import_action_*` defs; direct reads `views.py:2215-2230`, `:2380-2390`, `:1046-1070` (re-read) + `:1070-1094` (NEW — closes the Q8 remainder); `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127 — byte-identical to iterations 2–37); AST views 91 top-level defs + 21 classes / models 5 top-level defs + 21 classes incl. `Meta` (recomputed this pass); `ls curriculum/schemas/` (README + 3 `.schema.json`, flat, no `v2/`); `ls curriculum/services/` (`__init__.py` + `results.py` + `roadmap_cursor.py` + `__pycache__`); migrations tail (head still 0029); `python3 scripts/check_migrations.py` → OK (re-run this pass); `ls tests/test_*.py | wc -l` → 42; `gh` issue set not re-queried this pass (six-issue set #95/#97/#98/#103/#104/#107 carries from 19–37, no change alleged). `pytest` unrunnable here (no `.venv`); seam/maintainability claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–37; AST 91/21 recomputed identical; models 5/21 identical; head still 0029; `schemas/` still flat; `services/` still two modules; `check_migrations.py` OK; 42 test files; `git diff --stat` identical (+209/−716); status shape identical modulo the now-present untracked `supervisor-iteration-0037.md`. No M1 commit, no backfill, no read-cutover, no JSON-drop, no `v2/`, no hash wiring, no head advance, no seam extraction. Eighteenth consecutive no-drift pass (21–38).
2. **God-file footprint unchanged, seam map intact (observed, direct re-read).** `views.py` 2950 lines / 91 top-level defs (`grep -c` 95 raw vs AST 91 per the iteration-21 counter methodology) / 21 classes; `models.py` 2038 lines / 5 top-level defs / 21 classes (incl. `Meta` inners — the class count is inflated by Django `Meta`s, the def count is the load-bearing one). `services/` remains a two-module exemplar (`results.py` 552 + `roadmap_cursor.py` 27), imported at `views.py:74-75`. Extraction order S5→S4→S2 with S1-LAST-fused-with-M3 re-confirmed: `_grouped_activities :2420`, `_import_action_convert :2446`, convert call-adjacent `:2022` reuse, title-keyed staging writes `:2221-2222` + `:2383-2384` (prompt's `:2875-2876,2959-2960` still stale). No seam slice has started; the R2-before-seams ordering stands.
3. **Q8 cursor verdict CLOSED this pass (observed, NEW precision datum at 38).** The `:1070-1094` remainder read completes the iteration-35 half-read (`:1046-1070`). Full site: `tutor_session_active` reads `group_progress.current_activity_id` as a direct attribute (`:1068`), then computes position over `ordered_activities(session.roadmap_snapshot.payload)` locally (`:1069-1077`), with zero fallback. The 7 service sites (`:2505,2579,2599,2634,2770,2807,2866`) call `_roadmap_cursor.current_activity_id(group)`, which reads the same attribute first (`roadmap_cursor.py:17-19`) but adds a first-`ACTUAL`-of-`states()` fallback (`:20-27`) plus a `None`-group guard. Verdict: **alias with a missing fallback, not a duplicated resolution algorithm.** Same read source, divergent edge behavior (no-group / empty-attribute cases fall back in service sites, return `None`/misposition at `:1068` — though `:1066` guards with `if group_progress:` so the practical divergence is limited to the empty-attribute-with-states case). Spec impact: route `:1068` through the service accessor (one-line, behavior-preserving in the common case, fallback-gaining in the edge case) as part of a future S-seam slice AFTER R2 — never before, per the S1-LAST / R2-before-seams rule. The iteration-28 S-span pins carry unchanged.
4. **C1/C3 standing items untouched by this phase (observed).** No change to the C1 three-way asymmetry (ADR-0010 §Decisión-2 == `staging_validation.py:192` docstring ≠ code `:201-205` ≠ join `:76-77` with declared-intent `:56-62` ≠ `by_title :232`) or the C3 `models.py:1875` flat-path wording — both carry as R1 doc-precision items. This pass adds no new doc-precision debt: root docs re-read clean (C2 `DATABASE.md:103-105` + C4 `implementation-current.md:3-6` staleness already R1 items, unchanged).
5. **Gate and issue set unmoved (observed, not edited).** `IMPLEMENTATION-GATE.md` still `STATUS: HOLD` (2.5/6); six-issue `ready-for-agent` set carries (#95/#97/#98/#103/#104/#107, #98 sole on-path at 0/7 per iteration 29 — body not re-read this pass, no change alleged). PR 112 OPEN, unmerged. The parallel coding lane does nothing while the gate is `HOLD` or absent.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate: HOLD observed at iteration 38** (no edit — checkpoint-only file per loop rules). Next gate review due at iteration 40.
- Q8 closed: `:1068` is an alias-with-missing-fallback of the `roadmap_cursor` service; remediation is a one-line accessor routing inside a post-R2 seam slice, not a standalone ticket and not pre-R2 work.
- Maintainability verdict: no new seam extraction is specifiable beyond the standing S5→S4→S2 order with S1-LAST-fused-with-M3; `models.py` extraction stays behavior-only (fields are migration-pinned); S-numbers kept with iteration-28 span pins (Q9 recommendation re-affirmed).

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→38.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? (Carry-over 11→38.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→38.)
4. Agent-ready (C1, three-way framing at 34, re-verified at 35/36/37/38): confirm `_norm`-join + outer-keys-only hash, or keep exact reads with P1 pinning the exact-vs-`_norm` disagreement? (Carry-over 3→38.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list (with explicit overlap rendering per `test_t54:119-127`), `llm_log` audit copy. (Carry-over 5→38.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→38.) Load-bearing for the M4 rollback runbook.
7. Agent-ready (C3, re-verified at 27/34/35/36/37/38): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→38.)
8. ~~Evidence debt: `views.py:1068` vs `_roadmap_cursor`~~ — CLOSED at 38 (alias-with-missing-fallback; route `:1068` through the service accessor post-R2). Remaining half of the old Q8 (iteration-28 S-span re-pin table) carries as done — no further read debt on this pair.
9. Seam-spec: keep S-numbers with the iteration-28 span pins, or retire them post-shrink? Recommend keeping with 28 spans as the pin table. (Carry-over 18→38.)
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps. (`supervisor-prompt-catalog.md` also absent — checkpoint duty at 40 must create it, not this pass.)
11. Security (from 26, re-verified at 36): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie `Secure` flip on HTTPS, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.
12. Branch anomaly: supervisor passes run on `supervisor/aulalista-docs`, not `updated-tech` per the prompt's "Work starts on" line (carry-over 9→38). Confirm whether future passes should switch branches or amend the prompt — switching with a dirty Phase A–E tree is unsafe, so the anomaly persists until a human directs otherwise.
13. Matrix execution (from 35): where does the A1–A9 + P1/P2 green run execute before wiring, given `pytest` is unrunnable in this supervisor environment (no `.venv`)? Name the runner (coding-lane env or CI) in the #98 upgrade.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Human reviews/commits the Phase A–E tree first — it is the load-bearing blocker for every downstream step (clean base ref, C1–C5 landing, R1→R4 queue).
3. Land the five R1 doc-precision patches (C1 three-site + draft pick with the `:56-62` declared-intent quote, three-way ADR==docstring≠code framing, and the `:119-127` overlap rule; C2–C5) plus the P1/P2 pending-row names as the first committed work once a base ref exists; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface.
4. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23, reframed at 32/33/34) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface (with overlap rendering) + iteration-25 P1/P2 rows (placed: `test_t54` beside `:119-127`, P1 boundary + P2 guard-order) + iteration-28 S-span pins and the iteration-38 Q8 verdict (alias-with-missing-fallback at `views.py:1068` vs 7 service sites, route-through-service post-R2) + iteration-36 security pins (`views.py:125-142` gate, `:158-176` sealed cookies, `urls.py:228-229` minimal DEBUG block) + iteration-37 rollback table (M1 reverse-migrate / M2 truncate+re-run JSON-authoritative / M3 flag-off / M4 export-gated) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order. Per Q8 (settled at 30), the upgrade rides as handoff Markdown in the docs-only PR, never as a created issue.
5. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist. The Q11 hardening checklist gets a named owner + runbook location but no lane or ticket until the staging slice lands.
6. Refresh the loop prompt with the qualified #98 sentence, current line cites (six-issue set with #98 sole on-path at 0/7; join `staging_validation.py:76-77` + declared-intent `:56-62` + three-way C1 framing (ADR-0010 §Decisión-2 == docstring `:192` ≠ code `:201-205`) + overlap rule `test_t54:119-127` + P1/P2 placement + writes `views.py:2221-2222,2383-2384` + call sites `:2343,2346/:2423,2426`; cursor verdict CLOSED at 38 (`views.py:1068` alias-with-missing-fallback vs 7 service sites `:2505…:2866`, `roadmap_cursor.py:17-27`); `curriculum_import.py:23`; template `item.index :148` vs `item.id :157`; schemas flat + `$id` v1 + `models.py:1875` C3 + head 0029 additive-nullable + `check_migrations.py` OK; 42 test files; AST views 91 top-level / models 5 top-level, services two-module exemplar `views.py:74-75`; 7-slot draft rubric; settled Q8), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, the M4 artifact question, and the missing-`prompt-catalog` creation duty at the iteration-40 checkpoint.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / AST 91 top-level defs / 21 classes + `models.py` 2038 / 5 top-level defs + service import `:74-75` + `_grouped_activities :2420` + convert `:2446` + writes `:2221-2222,:2383-2384` + Q8 verdict `:1066-1094` full-read vs `roadmap_cursor.py:17-27` fallback; schemas flat README + 3 `.schema.json` + `$id` v1 + `SCHEMA_VERSION v1 :16` + `models.py:1875` C3 path caveat + `clean()` non-empty-only + no `save()` override; 0029 additive-nullable head + 0028 dependency; zero Topic/Subtopic/ActivityProposal tables; `check_migrations.py` OK; hash + dedup + `_norm` + join `:76-77` with declared-intent `:56-62`; matrix files t15/t16/t19/t20/t22/t24 + `test_t54` 127 lines/5 tests + overlap rule `:119-127` + P1/P2 placement; `models.py:1130` `in_bulk`; `curriculum_import.py:23` timeout; template `item.index :148` vs `item.id :157`; 42 test files; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; six-issue `ready-for-agent` set with #98 sole on-path at 0/7), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + Ollama-only egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; named matrix run (runner per Q13: coding-lane env or CI — supervisor env has no `.venv`) green including P1+P2 BEFORE wiring; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; ambiguous groups may overlap exact pairs (`test_t54:119-127`) and the surface must render overlap with exact-membership checked first (P2 pins guard order); named surface + P1 (join-agreement, pinning the exact-vs-`_norm` boundary per the `:56-62` refinement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only reverse-migratable, M2 re-runnable truncate+re-run with JSON still authoritative and C1 scope stated, M3 flagged read with flag-off rollback, M4 separate ticket with named export artifact + restore runbook answering Q6); seam slices (S5→S4→S2, S1-LAST-fused-with-M3, plus the `:1068`-through-service routing post-R2) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- Security non-regression per ticket: no new egress beyond Ollama localhost, no CDN/remote fetch, no `Secure`-breaking cookie change, no auth-gate weakening, no `*` hosts / DEBUG-True / dev-SECRET promotion beyond local; the Q11 institutional checklist stays out of staging tickets.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 39): continue the rotating phase loop (suggested: ready-for-agent ranking and issue draft quality, following the 21→28 cycle order — re-grade #98 against the 7-slot rubric only if its body changed, otherwise carry 0/7). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, `:1068` routed through service, settings hardened, `Secure`/validator flags added, `check --deploy` run recorded) and whether the gate moved. Checkpoint duties next due at iteration 40 (cumulative deltas 31–40 + gate review + `supervisor-prompt-catalog.md` creation + docs-only PR push packaging handoffs 0031–0040); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push. This handoff (`supervisor-iteration-0038.md`) remains untracked in the working tree for packaging at the iteration-40 checkpoint into PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged — https://github.com/eliancanul/AulaLista/pull/112), never merged.
