# Supervisor iteration 0029 — ready-for-agent ranking and issue draft quality

Iteration: 29 | Phase focus: ready-for-agent ranking and issue draft quality
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–28)

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
?? docs/handoffs/supervisor-iteration-0028.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `cc95426` (iteration-20 PR-record append); gate log tip still `606aa64` for `IMPLEMENTATION-GATE.md` (iteration-20 HOLD revert) — no third flip observed. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) stands — checkpoint duties (cumulative deltas 21–30 + gate review + docs-only PR push) next due at iteration 30, not now.

Prior memory: `supervisor-iteration-0028.md` (seams; `:1068` cursor candidate named, S-spans re-pinned) + `-0027.md` (schemas/migration, C3 closed by direct re-read, `$id` consistency) + `-0019.md` (last ranking/draft-quality pass; 7-slot rubric, 0/7 grade) + `supervisor-cumulative.md` (spine 2→20) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`).

## Scope

Phase-focus: re-grade the `ready-for-agent` set and #98 draft quality against live issue bodies and current code, not against prior handoffs. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 30). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`supervisor-iteration-0028.md` (full) + `-0019.md` (full, phase baseline) + `IMPLEMENTATION-GATE.md` + `supervisor-cumulative.md` (carried, not edited); `gh issue list --label ready-for-agent` (6) + full `gh issue list` (labels/state of #53/#54/#57/#58); `gh issue view 98` (full body, re-read); `gh issue view 53/54/57/58 --json` (labels/state); `rg CHAT_TIMEOUT_SECONDS` (`curriculum_import.py:23,:280`); `rg item.index|item.id` (template `:148`/`:157`); `rg current_activity_id` (`views.py` 8 hits: `:1068` direct + 7 service); `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127); `ls curriculum/schemas/` (flat, no `v2/`); migrations tail (head still 0029); 42 test files; `git diff --stat`, `git diff --cached --name-only`, gate log. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–28; migrations head still 0029; `schemas/` still flat; 42 test files; `git diff --stat` identical (+209/−716); status differs from iteration 28 only by the addition of untracked `supervisor-iteration-0028.md` (the expected own-handoff delta, now `supervisor-iteration-0029.md` pending). No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no hash wiring, no head advance.
2. **`ready-for-agent` set unchanged at six (observed — live re-grade, not carried blind).** Label filter returns exactly #95, #97, #98, #103, #104, #107 — same six as iteration 19. Only #98 sits on the staging critical path; #95/#103/#104/#107 are Dirección A/B institutional work, #97 is teacher-UI assist-cancel. The cumulative correction stands: "sole ready-for-agent path" is true only as "sole `ready-for-agent` issue **on the staging critical path**."
3. **#98 body unchanged, still 0/7 (observed — full body re-read).** Title/body byte-identical to iteration 19's description: 2 sections, ~6 criteria lines (idempotent retry, documented key/rules, preserve sources/editorial/human decisions, ambiguous conflicts reported not merged, retry/partial/same-title-different-source tests, #47 antecedent + editorial-workflow check). Zero ADRs, zero file:line cites, zero allowed/out-of-scope paths, zero named test files, zero migration/rollback plan, zero base ref, zero invariant list. The generic "(e) pruebas de reintento…" line implies acceptance tests without naming files; "(d) estado editorial y decisiones humanas" partially implies invariants without the full contract list. Grade 0/7 carries on fresh evidence.
4. **Fused-decision labels correctly unchanged (observed).** #53 (`enhancement+tech-debt`), #54 (`tech-debt`), #57 (`tech-debt`), #58 (`tech-debt`) — none bears `ready-for-agent`. Correct: promoting any one alone would invite doing one third of the fused #53/#98/#54 decision without the others; #57 stays prerequisite tooling; #58 stays stale epic.
5. **Draft-precision cites re-verified to current lines (observed — new precision this pass, advances the #98 upgrade spec).** `CHAT_TIMEOUT_SECONDS = 180` at `curriculum/curriculum_import.py:23` (used `:280`) — confirms the iteration-20 timeout-cite correction. Template split confirmed: `item.index` as checkbox value at `templates/curriculum/tutor_import_detail.html:148` vs `item.id` as hidden `activity_id` at `:157` — the A5b slice cite is live. Cursor census re-confirmed: 7 service call sites (`:2505,:2579,:2599,:2634,:2770,:2807,:2866`) + 1 direct read (`:1068`), matching iteration 28's Q9 pair; the `:1046-1094` full-read verdict is still pending and stays a pre-seam (not pre-R1) step.
6. **R1→R4 queue unchanged; iteration-30 packaging is the next draft-quality event (decision by rule).** R1 (M0 precision docs-only: C1 three-site + draft pick, C2–C5, P1/P2 rows) → R2 (A5a convert + A5b template, tested) → R3 (M1→M3, M4 excluded) → R4 (S5→S4→S2, S1-LAST-fused-with-M3) → R5 (periphery out). The #98 upgrade (iteration-9 §Draft + iteration-12 triple-join + C1 pick + A5a/A5b + timeout cite + seam guard + ambiguity surface + P1/P2 rows + iteration-28 S-spans + `:1068` verdict) remains drafted-but-uncreated; question 8 (ride inside the docs-only PR vs separate ticket text) must be settled at iteration 30.
7. **Gate: no edit, HOLD carries (decision by rule).** No third flip (log tip `606aa64`); iteration-20 2.5/6 scorecard and HOLD stand. Gate review + cumulative deltas (21–30) + docs-only PR push packaging handoffs 0021–0030 next due at iteration 30, not now.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **No gate edit, no cumulative edit, no PR this pass** — non-checkpoint iteration per loop rules.
- **Ranking contribution (this pass, on fresh evidence):** six-issue set re-graded live (not carried); #98 re-read full-body and re-graded 0/7; fused labels verified correctly absent; A5b template cite (`:148` vs `:157`) and timeout cite (`curriculum_import.py:23`) re-pinned to current lines for the iteration-30 #98-upgrade packaging.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→29.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? Two unamended flips is a pattern. (Carry-over 11→29.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→29.)
4. Agent-ready (C1, draft pick at 23, three-site at 24, P1/P2 rows at 25): confirm `_norm`-join + outer-keys-only hash, or take the exact-join-intentional alternative with inverted P1? Precedes backfill AND staging-adjacent seams. (Carry-over 3→29.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list, `llm_log` audit copy. Enforcement gap until picked; P2 has nowhere to render without it. (Carry-over 5→29.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→29.)
7. Agent-ready (C3, directly re-verified at 27): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→29.)
8. Draft-quality (due at 30): should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→29.)
9. Evidence debt (named at 28): is `views.py:1068` direct `group_progress.current_activity_id` a true duplicate of `_roadmap_cursor.current_activity_id(group)` (`:2505…:2866`), or a legitimate pre-normalization alias? Needs one 50-line read of `:1046-1094`. (Carry-over 11→29, actionable.)
10. Seam-spec (re-pinned at 28): keep S-numbers with the 28 span pins, or retire them post-shrink? (Carry-over 18→29.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
12. Security (from 26): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie/SECURE flags, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. At iteration 30, land the five R1 doc-precision patches (C1 three-site + draft pick, C2–C5) plus the P1/P2 pending-row names as docs-only PR content packaging handoffs 0021–0030; settle question 8 there. The #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface. This pass adds the live A5b (`template :148/:157`) and timeout (`curriculum_import.py:23`) pins to that package.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`, re-verified this pass) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface + iteration-25 P1/P2 rows + iteration-28 S-span pins and `:1068` cursor verdict before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist. Institutional hardening (iteration 26 finding 2 + question 12) is an explicit non-goal of the staging lane.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (ranking: six-issue set #95/#97/#98/#103/#104/#107 with #98 sole on-path at 0/7; A5b `tutor_import_detail.html:148/:157`; `curriculum_import.py:23`; cursor `:1068` vs `:2505…:2866`; head 0029; 42 test files), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: six-issue set with #98 sole staging-path at 0/7 on live re-read; A5b `tutor_import_detail.html:148` (`item.index`) vs `:157` (`item.id`); `curriculum_import.py:23` timeout; cursor `views.py:1068` vs 7 service sites; `views.py` 2950 / 91 top-level defs; `models.py` 2038, `ClassroomSession :762-1230`; `models.py:1130` `in_bulk`, `:1875` C3 path caveat; `staging_validation.py` hash `:189-208`, dedup `:211-238`, join `:76-77`; `schemas/` flat; migrations head 0029; 42 test files; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; named surface + P1 (join-agreement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only, M2 re-runnable with C1 scope stated, M3 flagged read, M4 separate ticket with named export artifact + restore runbook); seam slices (S5→S4→S2, S1-LAST-fused-with-M3) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 30): CHECKPOINT — update `supervisor-cumulative.md` with deltas only (21–30), review `IMPLEMENTATION-GATE.md` (flip only if all six conditions hold simultaneously, else re-affirm HOLD with scorecard), and package only staged `docs/handoffs/` + `docs/adr/` Markdown on `supervisor/aulalista-docs` into a pushed, non-merged PR when safe (verify `git diff --cached --name-only` first; never `git add -A`, never stage code, never merge). Pre-checks: whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, `:1068` resolved, settings hardened) and whether the gate moved a third time. Final synthesis at iteration 100 — not due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push, no new PR. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) untouched this pass.
- This handoff (`supervisor-iteration-0029.md`) remains untracked until the iteration-30 checkpoint packages it with 21–30 per the docs-only PR rule.
