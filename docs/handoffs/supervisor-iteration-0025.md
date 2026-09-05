# Supervisor iteration 0025 — tests, evidence, and acceptance matrix

Iteration: 25 | Phase focus: tests, evidence, and acceptance matrix
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–24)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `cc95426` (iteration-20 PR-record append); gate log tip still `606aa64` for `IMPLEMENTATION-GATE.md` (iteration-20 HOLD revert) — no third flip observed. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) stands — no PR duty until iteration 30.

Prior memory: `supervisor-iteration-0024.md` (C1–C5 three-site sharpening, R1 packaging for 30) + `-0023.md` (idempotency/dedup, C1 draft pick + report-surface enforcement framing) + `-0021.md` (baseline, counter-methodology note) + `-0015.md` (A1–A9 with A5a/A5b split, phase baseline re-verified here) + `supervisor-cumulative.md` (spine 2→20) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`).

## Scope

Phase-focus: re-verify the iteration-5/15 acceptance matrix (A1–A9 with A5a/A5b) against current code, not against prior handoffs, and sketch the two proving tests from the iteration-23 C1 draft pick as pending matrix rows. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 30). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`supervisor-iteration-0015.md` (full, A-baseline) + `-0023.md` + `-0024.md` (§-scoped) + `supervisor-cumulative.md` + `IMPLEMENTATION-GATE.md` (carried, not edited); `curriculum/staging_validation.py:189-238` (re-read this pass: hash + dedup); `docs/adr/0006-teacher-workflow-and-human-curriculum-progress.md:29` (C5 site re-read); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `ls curriculum/schemas/` (flat: README + 3 `.schema.json`, no `v2/`); `curriculum/migrations/` tail (head still 0029); `ls tests/test_*.py | wc -l` → 42; `python3 scripts/check_migrations.py` → OK (re-run this pass); `grep` for `item.index|item.id` in `templates/curriculum/tutor_import_detail.html` (`:148` index vs `:157` id); `grep` for `_import_action_convert|_activity_id|int(index)` in `views.py` (`:2301/:2317/:2428/:2446/:2456/:2006`); `grep -c activity_content_hash|find_duplicate` in `views.py` → 0; `git log --oneline -3 -- IMPLEMENTATION-GATE.md`, `git log --oneline -3`, `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–24; migrations head still 0029; `schemas/` still flat; `check_migrations.py` OK; 42 test files; `git diff --stat` identical (+209/−716); status differs from iteration 24 only by the addition of untracked `supervisor-iteration-0024.md` (the expected own-handoff delta, now `supervisor-iteration-0025.md` pending). No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no `v2/`, no new service module, no new model, no hash wiring.
2. **Matrix re-verification, row by row (observed — phase deliverable; Gap column only).** A1 title-join transitional (join exact-`==` `staging_validation.py:76-77`, writers `views.py:2221-2222,2383-2384`, consumer `:2428` with `_activity_id :2301`): no removal test, unchanged. A2 idempotency key (`:189-208`, `_norm :25-26` on outer keys `:201-202`, verbatim proposal `:203-205`): zero pipeline call sites, unchanged; C1 draft pick (iteration-23, three-site extension at 24) still uncommitted. A3 report-only dedup (`:211-238`, title key `:232`): no badges in `_grouped_activities` (`views.py:2420-2444`), unchanged. A4 schema enforcement (`test_t54` 127 lines, `models.py:1874-1896`, C3 path caveat at `:1875`): unchanged. A5 convert identity SPLIT (carries): A5a handler still positional (`views.py:2456` inside `:2446-2475`, call site `:2006`) on this branch — cross-branch fix claim only; A5b template still `item.index` (`tutor_import_detail.html:148`) with `item.id` only on remove (`:157`); `test_t15` still has no convert-identity test (gap open). A6 N+1 (`models.py:1130` `in_bulk`): still no named perf test, unchanged. A7 single cursor (27-line service, call sites `:2505,2579,2599,2634,2770,2807,2866` per iteration 15): still no named cursor test; duplicated-cursor pair still unnamed (evidence debt carries). A8 anti-collision (head 0029, script OK re-run this pass): green, unchanged. A9 design/privacy (T13 checklist empty, LAN spec-only): unchanged; no ticket may claim physical-LAN or concurrent-write support.
3. **Two proving tests sketched as pending rows (spec precision gain, this pass's contribution).** The iteration-23 draft pick (`_norm`-join + outer-keys-only hash) is untestable until named. Pending P1 (join-agreement): two entries differing only by case/whitespace in `(topic, subtopic)` join into one group AND share one `activity_content_hash`. Pending P2 (same-title-separation): two entries with identical normalized `(topic, subtopic, proposal.title)` but differing proposal bodies land in `same_title_diff_content`, never merged, and require the named report surface before wiring. Both belong in `tests/test_t54_staging_contracts.py` (or its named successor) and both must pass BEFORE any of the three wiring touchpoints (post-generate append guard, pre-topup count, pre-convert list) lands. Alternative pick (exact-join-intentional) would invert P1's expectation with its own proving test — either is spec-valid; silence is not.
4. **C1–C5 carry unmodified (observed).** C1 three-site overstatement (`staging_validation.py:192` docstring says "proposal canónico" normalized — code normalizes only outer keys; ADR-0010 §Decisión-2 + `schemas/README.md` same sentence) re-confirmed via re-read of `:189-208` vs `:232`. C2 (`DATABASE.md:103-105` no ADR-0010 cite), C3 (`models.py:1875` `v1` path vs flat disk), C4 (`implementation-current.md:3-6` main-snapshot header), C5 (ADR-0006 `:29` lists only ACTUAL/DISPONIBLE/COMPLETADA vs `teacher-flow.md:110-120` four-state + `visto` mapping) all byte-identical. Still R1 docs-only, still packaged for iteration 30.
5. **Gate: no edit, HOLD carries (decision by rule).** No third flip (log tip `606aa64`); iteration-20 2.5/6 scorecard and HOLD stand. Gate review + cumulative deltas (21–30) + docs-only PR push next due at iteration 30, not now.
6. **Fused-decision spine unchanged (observed + carry).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. #98 stays the sole staging-path `ready-for-agent` candidate at 0/7 (iteration-19 rubric, carried — issue bodies not re-read, tree unchanged so no re-grade possible).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **No gate edit, no cumulative edit, no PR this pass** — non-checkpoint iteration per loop rules.
- **Matrix contribution (this pass):** A1–A9 re-verified row-by-row with current cites; A5a/A5b split carries; P1/P2 pending rows added as the acceptance precondition for any hash-wiring slice. Backfill wording still depends on the C1 pick; wiring still depends on P1/P2 + named report surface.
- **Cite discipline re-affirmed:** current lines only (hash `:189-208` with keys `:201-202` + verbatim `:203-205`, dedup `:211-238` with title key `:232`, join `:76-77`, writers `views.py:2221-2222/:2383-2384`, callers `:2006/:2428`, `_activity_id` `:2301`, remove `:2317`, convert positional `:2456` inside `:2446-2475`, template `:148` vs `:157`, `models.py:1130` `in_bulk` + `:1875` C3 caveat, ADR-0006 `:29` C5 caveat, `implementation-current.md:3-6` C4 caveat, `DATABASE.md:103-105` C2 caveat; `schemas/` flat; migrations head 0029; 42 test files); prompt's stale pre-shrink numbers remain superseded.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→25.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? Two unamended flips is a pattern. (Carry-over 11→25.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→25.)
4. Agent-ready (C1, draft pick at 23, three-site at 24, P1/P2 rows at 25): confirm `_norm`-join + outer-keys-only hash, or take the exact-join-intentional alternative with inverted P1? Precedes backfill AND staging-adjacent seams. (Carry-over 3→25.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list, `llm_log` audit copy. Enforcement gap until picked; P2 has nowhere to render without it. (Carry-over 5→25.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→25.)
7. Agent-ready (C3): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→25.)
8. Draft-quality: should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→25.)
9. Evidence debt: name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (Carry-over 11→25.)
10. Seam-spec: pin S5/S4/S2 to current `views.py` def spans or retire S-numbers and re-derive post-shrink? (Carry-over 18→25.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Land the five R1 doc-precision patches (C1 three-site + draft pick, C2–C5) plus the P1/P2 pending-row names as docs-only PR content at iteration 30; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23) + iteration-15 A5a/A5b split + corrected timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface + this pass's P1/P2 rows before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (join `:76-77`, writers `:2221-2222/:2383-2384`, hash `:189-208`, zero-wiring count, title key `:232`, template `:148` vs `:157`, convert `:2456`, C1 three-site list, C3 `:1875`, C4 header, ADR-0006 `:29`), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / `models.py` 2038; `staging_validation.py` 238 with `_norm` `:25-26`, join `:55-80` exact `:76-77`, hash `:189-208` with keys `:201-202` + verbatim proposal `:203-205`, dedup `:211-238` with title key `:232`, zero `views.py` call sites; writers `views.py:2221-2222/:2383-2384`; callers `:2006/:2428`; `_activity_id` `:2301`, remove `:2317`, grouped `:2420-2444`, convert `:2446-2475` positional `:2456`; template `:148` `item.index` vs `:157` `item.id`; `models.py:36` reviewer group, `:48-55` sha256, `:289-308` publish gate, `:384` immutable hash, `:762` session, `:1130` `in_bulk`, `:1875` C3 path caveat; `services/results.py` 552, `roadmap_cursor.py` 27; `schemas/` flat (README + 3 `.schema.json`, no `v2/`); migrations head 0029; 42 test files; ADR-0010 with C1 caveat (three sites); `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; named surface + P1 (join-agreement) + P2 (same-title-separation) required before wiring.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 26): resume the rotating phase loop (suggested: schemas/migration M0→M4 rollback re-verification, or security/deployment envelope). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired into the pipeline, P1/P2 tests added) and whether the gate moved a third time. Checkpoint duties next due at iteration 30 (cumulative deltas 21–30 + gate review + docs-only PR push packaging handoffs 0021–0030); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push, no new PR. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) untouched this pass.
- This handoff (`supervisor-iteration-0025.md`) remains untracked until the iteration-30 checkpoint packages it with 21–30 per the docs-only PR rule.
