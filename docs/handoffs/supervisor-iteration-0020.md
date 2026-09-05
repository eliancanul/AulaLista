# Supervisor iteration 0020 — checkpoint: synthesis, gate review, cumulative

Iteration: 20 | Phase focus: synthesis, gap analysis, and next-loop handoff
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–19)

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
?? docs/handoffs/supervisor-iteration-0011.md
?? docs/handoffs/supervisor-iteration-0012.md
?? docs/handoffs/supervisor-iteration-0013.md
?? docs/handoffs/supervisor-iteration-0014.md
?? docs/handoffs/supervisor-iteration-0015.md
?? docs/handoffs/supervisor-iteration-0016.md
?? docs/handoffs/supervisor-iteration-0017.md
?? docs/handoffs/supervisor-iteration-0018.md
?? docs/handoffs/supervisor-iteration-0019.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD still `b22b55b` (second stacked slice); no third flip. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) verified OPEN this pass — no new PR to create, only to push.

Prior memory: `supervisor-iteration-0019.md` (ranking + #98 0/7 rubric) + `-0018.md` (seams, 91 defs, S1-LAST-fused-with-M3) + `-0017.md` (migration spine M0→M4) + `-0016.md` (security envelope, Ollama close-out) + `-0015.md` (A1–A9, A5a/A5b split, 2.5/6 scorecard) + `-0014.md` (C1–C5) + `-0013.md` (`_norm` asymmetry) + `-0012.md` (triple-join cite) + `-0011.md` (baseline, first off-cycle flip, 2/6 scorecard) + `supervisor-cumulative.md` (spine 2→10).

## Scope

Checkpoint duties per loop rules, all executed this pass: (1) re-verify whether the tree moved; (2) extend `supervisor-cumulative.md` with deltas 11–20 only; (3) review `IMPLEMENTATION-GATE.md` — revert to `HOLD` with scorecard; (4) push staged `docs/handoffs/` + `docs/adr/` Markdown on `supervisor/aulalista-docs` into the existing non-merged PR 112 when safe. Spec only — nothing implemented, no issue created/edited/labeled.

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md` (carried; unchanged per working-tree stat); `docs/adr/0010-staging-relacional-idempotente.md` (governing decision, carried); `docs/handoffs/IMPLEMENTATION-GATE.md` (on-disk `READY` vs checkpoint rule); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` tail (head still 0029); `ls -R curriculum/schemas/` (flat: README + 3 `.schema.json`, no `v2/`); `grep` spot-checks `views.py:2006,2022,2420,2446,2456`, `staging_validation.py:16` + `_norm` + hash block, `CHAT_TIMEOUT_SECONDS` repo-wide; `git log --oneline -5`; `gh pr view 112 --json state,headRefName,baseRefName,url`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every line count byte-identical to iterations 2–19; migrations head still 0029; `schemas/` still flat; `git diff --stat` identical (+209/−716); status differs from iteration 19 only by the new untracked `supervisor-iteration-0019.md` (last pass's own handoff). No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no `v2/`, no new service module.
2. **No third gate flip (observed).** Gate log tip still `b22b55b`; the two-flip off-cycle pattern (`498a4df`, `b22b55b`) stands unamended — no human-signed loop-rule amendment landed. PR 112 still OPEN, unmerged. Checkpoint duty therefore fires as specified: adopt-with-evidence or revert, and evidence conditions are unmet (Finding 4).
3. **Spot re-verification, one cite correction (observed).** `_grouped_activities` `views.py:2420`, `_import_action_convert` `views.py:2446` with positional `entry = job.activities[int(index)]` `:2456`, call site `:2006`, grouped reuse `:2022` — all confirmed. `staging_validation.py:16` `SCHEMA_VERSION = "v1"`, `_norm` block, hash block `:203-205` — confirmed. **Correction:** `CHAT_TIMEOUT_SECONDS = 180` lives in `curriculum/curriculum_import.py:23`, not in `settings.py`/`views.py` (repo-wide `grep "CHAT_TIMEOUT_SECONDS\s*="` hits only that line). Future cites must use the `curriculum_import.py:23` path; iteration-16/19 wording that implied otherwise is superseded.
4. **Gate assessment: HOLD (decision, scored).** Against iteration-10's six flip conditions: (a) Phase A–E tree human-reviewed/committed → STILL OPEN (status shape unchanged); (b) narrowed allowed paths → MET (template + one test file + handoffs is the smallest slice yet); (c) mandatory convert-to-`activity_id` + test → HALF (handler claimed done cross-branch, template + test pending); (d) non-self-referential base ref + reachable evidence → HALF (base is the agent branch, but the cited `coding-41560047f83c.md` is still not on this branch); (e) open questions 2–4 answered → OPEN (`_norm` scope, report surface, M4 shape undecided); (f) zero blockers → OPEN (blocker (a) persists). Score carries at **2.5/6**. Loop rule is explicit: any remaining question/blocker keeps `HOLD`. The on-disk `READY` is therefore reverted this pass (see §Decisions + updated gate file).
5. **Cumulative gap closed (observed).** `supervisor-cumulative.md` covered 2–10 only; nine handoffs (0011–0019) were uncommitted deltas. This pass stages and pushes them with the 11–20 delta synthesis — the branch then carries the full spine 2→20.
6. **Fused-decision spine unchanged (observed + carry).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. #98 stays the sole staging-path `ready-for-agent` candidate at 0/7 executable slots (iteration-19 rubric, carried — body not re-read, tree unchanged so no re-grade possible). #53/#54/#57 stay correctly unlabeled; #58 stays docs-only epic-body work.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate reverted to `STATUS: HOLD`** (see updated `IMPLEMENTATION-GATE.md`): 2.5/6 scorecard carries; flip requires all six conditions simultaneously, plus a human-signed amendment if stacked-slice off-cycle updates are to be legitimate in future.
- **Cumulative extended** with deltas-only 11–20 section; standing spine, recommendations, and open questions preserved and renumbered.
- **Cite correction adopted:** `CHAT_TIMEOUT_SECONDS = 180` → `curriculum/curriculum_import.py:23`.
- PR packaging: stage ONLY `docs/handoffs/` Markdown (0011–0020 handoffs, cumulative, gate); verify `git diff --cached --name-only` before commit; push `supervisor/aulalista-docs` (PR 112 already exists — no new PR). If the cached diff shows any non-Markdown or non-`docs/handoffs/`/`docs/adr/` path, abort and record why in §PR record.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→20.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates (with vendored evidence or exact cross-branch refs), or confirm HOLD-only-outside-checkpoints? Two unamended flips is already a pattern. (Carry-over 11→20.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→20.)
4. Agent-ready (C1): recursive `_norm` on inner proposal text vs outer-keys-only (`staging_validation.py:25-26` vs `:203-205` vs ADR-0010 §Decisión-2)? Precedes backfill AND staging-adjacent seams. (Carry-over 3→20.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Assumed review-screen + pre-convert list. (Carry-over 5→20.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→20.)
7. Agent-ready (C3): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→20.)
8. Draft-quality: should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→20.)
9. Evidence debt: name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (Carry-over 11→20.)
10. Seam-spec: pin S5/S4/S2 to current `views.py` def spans or retire S-numbers and re-derive post-shrink? (Carry-over 18→20.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Land the five R1 doc-precision patches (C1–C5 from iteration 14) as docs-only PR content; the #98 upgrade depends on C1, the `models.py` docstring on C3.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick + iteration-15 A5a/A5b split + corrected timeout cite (`curriculum/curriculum_import.py:23`) + iteration-18 seam guard before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (including the `curriculum_import.py:23` correction), the N+1-fixed note (`models.py:1110-1135` `in_bulk`), and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / `models.py` 2038; `:2420` grouped, `:2446` convert positional `:2456`, `:2006` call site, `:2022` reuse; `staging_validation.py:16` version, hash `:203-205` with C1 caveat; `curriculum_import.py:23` timeout; `services/results.py` 552, `roadmap_cursor.py` 27; `schemas/` flat, no `v2/`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 21): resume the rotating phase loop (suggested: R1 doc-precision slice drafting with C1–C5, or the R4 seam-ticket skeleton with pinned def spans). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared) and whether the gate moved a third time. Checkpoint duties next due at iteration 30 (cumulative deltas + gate review + docs-only PR push); final synthesis at iteration 100 — neither is due now.

## PR record

- Staged set verified (`git diff --cached --name-only`): `docs/handoffs/supervisor-iteration-0011.md` through `-0019.md` (nine pending handoffs), `supervisor-iteration-0020.md`, `supervisor-cumulative.md`, `IMPLEMENTATION-GATE.md` — Markdown under `docs/handoffs/` only, no code.
- Committed as `606aa64` on `supervisor/aulalista-docs`, pushed to origin (`b22b55b..606aa64`).
- PR: https://github.com/eliancanul/AulaLista/pull/112 (head `supervisor/aulalista-docs` → base `main`, pre-existing and still OPEN — no new PR created; docs-only, not merged — never merge per loop rules).
- Follow-up: this §PR record was filled after the push; recorded in a second append-only docs commit (no history rewrite).
