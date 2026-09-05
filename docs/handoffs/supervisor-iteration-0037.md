# Supervisor iteration 0037 — schemas, migration sequence, and rollback safety

Iteration: 37 | Phase focus: schemas, migration sequence, and rollback safety
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–36)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

(`git diff --cached --name-only` → empty at pass start. HEAD `bef32fd`. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 OPEN, unmerged.)

Prior memory: `supervisor-iteration-0036.md` (security envelope + `urls.py:228-229` DEBUG-block datum) + `supervisor-iteration-0035.md` (matrix net + P1/P2 placement in `test_t54` beside `:119-127`) + `supervisor-cumulative.md` (spine 2→30, deltas 21–30) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6).

## Scope

Non-checkpoint rotating-phase pass (schemas/migration/rollback, per the 21→28 cycle order and the iteration-36 §Next move). Spec only — nothing implemented, no issue created/edited/labeled, no gate edit, no cumulative edit, no PR push (checkpoint duties next due at iteration 40). This pass re-verifies the ADR-0010 M0→M4 spine, the `schemas/` v1 contract, and per-step rollback safety against current lines, and sharpens C1/C3 wording without touching code.

## Files inspected

`supervisor-iteration-0036.md` (full) + `supervisor-iteration-0035.md` (§Findings only) + `supervisor-cumulative.md` (spine + deltas 21–30 headers) + `IMPLEMENTATION-GATE.md` (status + scorecard lines only, no edit); `docs/adr/0010-staging-relacional-idempotente.md` (full re-read, 58 lines); `curriculum/staging_validation.py` (full re-read, 238 lines); `curriculum/schemas/README.md` (full re-read, 14 lines); `curriculum/models.py:1860-1894` (`clean()` + `:1875` path, direct re-read); `curriculum/migrations/0029_curriculumimportjob_progress_finished_at.py` (full head read, additive-nullable); live greps: `class Topic|class Subtopic|class ActivityProposal` (0 matches — no relational tables yet), `SCHEMA_VERSION|schemas/v1|full_clean|def clean` in `models.py`, `"$id"` in `schemas/*.schema.json`; `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127 — byte-identical to iterations 2–36); AST views 91 top-level defs (recomputed this pass, `grep -c` 95 raw vs AST 91 per the iteration-21 counter methodology); `ls curriculum/schemas/` (README + 3 `.schema.json`, flat, no `v2/`); migrations tail (head still 0029); `python3 scripts/check_migrations.py` → OK (re-run this pass); `ls tests/test_*.py | wc -l` → 42; `gh` issue set not re-queried this pass (six-issue set #95/#97/#98/#103/#104/#107 carries from 19–36, no change alleged). `pytest` unrunnable here (no `.venv`); schema/migration claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–36; AST 91 recomputed identical; head still 0029; `schemas/` still flat; `check_migrations.py` OK; 42 test files; `git diff --stat` identical (+209/−716); status shape identical modulo the now-present untracked `supervisor-iteration-0036.md`. No M1 commit, no backfill, no read-cutover, no JSON-drop, no `v2/`, no hash wiring, no head advance. Seventeenth consecutive no-drift pass (21–37).
2. **Schemas v1 contract intact, C3 wording still OPEN (observed, direct re-read).** `schemas/README.md:3-6` declares flat `v1/` + runtime validator + version rule (`:7-10`: compatible change stays v1, accept/reject change creates `v2/` + bumps `SCHEMA_VERSION`); `SCHEMA_VERSION = "v1"` (`staging_validation.py:16`); all three `$id` values consistently `https://aulalista.local/schemas/v1/*.schema.json`; `models.py:1875` docstring says `curriculum/schemas/v1` while the tree is flat `*.schema.json` (no `v1/` directory) — the C3 R1 patch (flat-path wording) still unlanded. Runtime semantics confirmed: `clean()` validates only non-empty payloads (`:1886-1894` via `validate_*` returning `[]` for `None/[]/""`), `save()` does not call `clean()` (no override on `CurriculumImportJob`; explicit `full_clean()` at human review per docstring `:1877-1879`), partial pipeline writes unaffected. No `v2/` trigger condition met (no accept/reject shape change observed).
3. **C1 three-way asymmetry re-verified unchanged (observed, direct re-read).** ADR-0010 §Decisión-2 == `staging_validation.py:192` docstring (both claim `(topic, subtema, proposal)` normalized) ≠ code `:201-205` (topic/subtopic `_norm`ed at `:201-202`, proposal only key-sorted/serialized raw at `:203-205`, values not `_norm`ed) ≠ join `group_by_subtopic` exact-`==` at `:76-77` (declared intentional `:56-62`) ≠ `by_title` `_norm` triple at `:232`. The M2 backfill scope therefore still depends on the unanswered C1 pick (`_norm`-join + outer-keys-only hash vs exact-join documented as intentional with P1 pinning the boundary). No code change resolves or worsens it.
4. **Migration sequence M0→M4 spine intact, head 0029 rollback-trivial (observed).** Head `0029_curriculumimportjob_progress_finished_at` is `AddField(progress_finished_at, null=True, blank=True, editable=False)` depending on `0028_grouproadmapprogress` — purely additive-nullable, backward rollback = `migrate curriculum 0028` with zero data loss. No `Topic`/`Subtopic`/`ActivityProposal` tables exist (grep 0 matches) — M1 not started, M2/M3/M4 not started. `check_migrations.py` green confirms the #57 prerequisite holds for the next slice. The only migration-sequence risks remain documentary (C1 pick for M2 scope + C3 path for M0 precision), exactly as at iteration 27.
5. **Per-step rollback safety restated with current pins (observed, spec impact — new precision datum at 37).** M1 (additive tables + nullable FKs, no data move): rollback = reverse-migrate, no export needed. M2 (re-runnable backfill recalculating `content_hash`, reporting ambiguous via `find_duplicate_groups`, never touching `selected`/editorial state): rollback = truncate relational rows + re-run, JSONFields remain the read source so no production read regresses. M3 (flagged new-read in `_import_action_*`, `_grouped_activities`, remove/topup): rollback = flip flag off, behavior-only. M4 (drop-JSON, separate human-confirmed ticket): rollback requires the named export artifact + restore runbook (still OPEN as Q6: per-job dump vs snapshot-table export). Rule #58 (`docs/DATABASE.md` in the same PR on any model/pipeline step) and #57 gate (`check_migrations.py` + `makemigrations --check`) attach to every step.
6. **Gate and issue set unmoved (observed, not edited).** `IMPLEMENTATION-GATE.md` still `STATUS: HOLD` (2.5/6); six-issue `ready-for-agent` set carries (#95/#97/#98/#103/#104/#107, #98 sole on-path at 0/7 per iteration 29 — body not re-read this pass, no change alleged). PR 112 OPEN, unmerged. The parallel coding lane does nothing while the gate is `HOLD` or absent.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate: HOLD observed at iteration 37** (no edit — checkpoint-only file per loop rules). Next gate review due at iteration 40.
- Migration verdict: the M0→M4 spine plus per-step rollback table above is the implementable form of the iteration-7/17/27 spine; the only new content this pass is the per-step rollback pins (M1 reverse-migrate / M2 truncate+re-run with JSON still authoritative / M3 flag-off / M4 export+runbook-gated). M4 stays a separate ticket; no slice is authorized.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→37.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? (Carry-over 11→37.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→37.)
4. Agent-ready (C1, three-way framing at 34, re-verified at 35/36/37): confirm `_norm`-join + outer-keys-only hash, or keep exact reads with P1 pinning the exact-vs-`_norm` disagreement? (Carry-over 3→37.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list (with explicit overlap rendering per `test_t54:119-127`), `llm_log` audit copy. (Carry-over 5→37.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→37.) Now load-bearing for the M4 rollback runbook.
7. Agent-ready (C3, re-verified at 27/34/35/36/37): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→37.)
8. Evidence debt (narrowed at 35): `views.py:1068` vs `_roadmap_cursor` — first 25 lines of `:1046-1094` read (`:1046-1070`); remaining `:1070-1094` still needed for the alias-vs-duplicate verdict. (Carry-over 11→37, actionable, halved.)
9. Seam-spec: keep S-numbers with the iteration-28 span pins, or retire them post-shrink? Recommend keeping with 28 spans as the pin table. (Carry-over 18→37.)
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
11. Security (from 26, re-verified at 36): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie `Secure` flip on HTTPS, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.
12. Branch anomaly: supervisor passes run on `supervisor/aulalista-docs`, not `updated-tech` per the prompt's "Work starts on" line (carry-over 9→37). Confirm whether future passes should switch branches or amend the prompt — switching with a dirty Phase A–E tree is unsafe, so the anomaly persists until a human directs otherwise.
13. Matrix execution (from 35): where does the A1–A9 + P1/P2 green run execute before wiring, given `pytest` is unrunnable in this supervisor environment (no `.venv`)? Name the runner (coding-lane env or CI) in the #98 upgrade.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Human reviews/commits the Phase A–E tree first — it is the load-bearing blocker for every downstream step (clean base ref, C1–C5 landing, R1→R4 queue).
3. Land the five R1 doc-precision patches (C1 three-site + draft pick with the `:56-62` declared-intent quote, three-way ADR==docstring≠code framing, and the `:119-127` overlap rule; C2–C5) plus the P1/P2 pending-row names as the first committed work once a base ref exists; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface.
4. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23, reframed at 32/33/34) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface (with overlap rendering) + iteration-25 P1/P2 rows (placed: `test_t54` beside `:119-127`, P1 boundary + P2 guard-order) + iteration-28 S-span pins and `:1068` cursor verdict (half-read at 35) + iteration-36 security pins (`views.py:125-142` gate, `:158-176` sealed cookies, `urls.py:228-229` minimal DEBUG block) + iteration-37 rollback table (M1 reverse-migrate / M2 truncate+re-run JSON-authoritative / M3 flag-off / M4 export-gated) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order. Per Q8 (settled at 30), the upgrade rides as handoff Markdown in the docs-only PR, never as a created issue.
5. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist. The Q11 hardening checklist gets a named owner + runbook location but no lane or ticket until the staging slice lands.
6. Refresh the loop prompt with the qualified #98 sentence, current line cites (six-issue set with #98 sole on-path at 0/7; join `staging_validation.py:76-77` + declared-intent `:56-62` + three-way C1 framing (ADR-0010 §Decisión-2 == docstring `:192` ≠ code `:201-205`) + overlap rule `test_t54:119-127` + P1/P2 placement + writes `views.py:2221-2222,2383-2384` + call sites `:2343,2346/:2423,2426`; cursor `:1068` (half-read `:1046-1070`) vs `:2505…:2866`; `curriculum_import.py:23`; template `item.index :148` vs `item.id :157`; schemas flat + `$id` v1 + `models.py:1875` C3 + head 0029 additive-nullable + `check_migrations.py` OK; 42 test files; AST views 91 top-level), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, the M4 artifact question, the 7-slot draft rubric, and settled Q8.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: schemas flat README + 3 `.schema.json` + `$id` v1 + `SCHEMA_VERSION v1 :16` + `models.py:1875` C3 path caveat + `clean()` non-empty-only `:1886-1894` + no `save()` override; 0029 additive-nullable head + 0028 dependency; zero Topic/Subtopic/ActivityProposal tables; `check_migrations.py` OK; hash `:189-208` + dedup `:211-238` + `_norm` `:25-26` vs `:201-202` vs `:232` + join `:76-77` with declared-intent `:56-62`; join writes `views.py:2218-2225,2380-2387` + call sites `views.py:2343,2346/:2423,2426`; `views.py` 2950 / AST 91 top-level defs; matrix files t15/t16/t19/t20/t22/t24 + `test_t54` 127 lines/5 tests + overlap rule `:119-127` + P1/P2 placement; cursor `views.py:1068` (read `:1046-1070`, remainder `:1070-1094` pending) vs 7 service sites; `models.py:1130` `in_bulk`; `curriculum_import.py:23` timeout; template `item.index :148` vs `item.id :157`; `_activity_id :2301/:2317/:2428`; 42 test files; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; six-issue `ready-for-agent` set with #98 sole on-path at 0/7), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + Ollama-only egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; named matrix run (runner per Q13: coding-lane env or CI — supervisor env has no `.venv`) green including P1+P2 BEFORE wiring; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; ambiguous groups may overlap exact pairs (`test_t54:119-127`) and the surface must render overlap with exact-membership checked first (P2 pins guard order); named surface + P1 (join-agreement, pinning the exact-vs-`_norm` boundary per the `:56-62` refinement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only reverse-migratable, M2 re-runnable truncate+re-run with JSON still authoritative and C1 scope stated, M3 flagged read with flag-off rollback, M4 separate ticket with named export artifact + restore runbook answering Q6); seam slices (S5→S4→S2, S1-LAST-fused-with-M3) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- Security non-regression per ticket: no new egress beyond Ollama localhost, no CDN/remote fetch, no `Secure`-breaking cookie change, no auth-gate weakening, no `*` hosts / DEBUG-True / dev-SECRET promotion beyond local; the Q11 institutional checklist stays out of staging tickets.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 38): continue the rotating phase loop (suggested: god-files, service seams, maintainability, following the 21→28 cycle order — finish the `:1070-1094` cursor remainder read if still unclaimed). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, settings hardened, `Secure`/validator flags added, `check --deploy` run recorded) and whether the gate moved. Checkpoint duties next due at iteration 40 (cumulative deltas 31–40 + gate review + docs-only PR push packaging handoffs 0031–0040); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push. This handoff (`supervisor-iteration-0037.md`) remains untracked in the working tree for packaging at the iteration-40 checkpoint into PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged — https://github.com/eliancanul/AulaLista/pull/112), never merged.
