# Supervisor iteration 0010 — checkpoint: synthesis, gate review, cumulative

Iteration: 10 | Phase focus: synthesis, gap analysis, and next-loop handoff
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iteration 9)

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
?? docs/handoffs/supervisor-iteration-0009.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `675eadb` (docs gate + handoffs 0002/0003/0005–0008) on top of `82d4a9d` (`updated-tech` tip). Iteration 0009 exists on disk but is still uncommitted. No `supervisor-cumulative.md` on disk before this pass. No open PR with head `supervisor/aulalista-docs` (verified via `gh pr list`; all listed PRs are merged `codex/*`).

Prior memory: `supervisor-iteration-0009.md` (ready-for-agent queue R1–R5 + draft ticket + gate contradiction Finding 6), `-0008.md` (seams S1–S5, Steps 0–4), `-0007.md` (M0→M4 + rollback), `-0006.md` (security/deployment envelope), `-0005.md` (evidence matrix A1–A9), `-0003.md` (idempotency/ambiguity), `-0002.md` (staging join + relational model). No `-0001.md` / `-0004.md` exist; numbering arrives externally.

## Scope

Checkpoint duties per loop rules: (1) re-verify whether the tree changed; (2) write `supervisor-cumulative.md` (deltas-only synthesis); (3) review `IMPLEMENTATION-GATE.md` — revert to `HOLD` or narrow; (4) package docs-only Markdown into a pushed, non-merged PR when safe. Spec only — nothing implemented.

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `docs/handoffs/IMPLEMENTATION-GATE.md`, `supervisor-iteration-0008.md`, `supervisor-iteration-0009.md`; `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` inventory (0001–0029, no 003x); `rg` for `_import_action_convert|_activity_id|find_duplicate_groups|activity_content_hash`; re-read `views.py:2301-2325` (remove) + `views.py:2446-2475` (convert); `models.py:1870-1880` (`clean()` docstring); `python3 scripts/check_migrations.py` → OK; read-only `gh` inspection (open issues, `ready-for-agent` set). `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** All line counts byte-identical to iterations 2/3/5/6/7/8/9; migrations head still 0029; `check_migrations.py` green; `schemas/` still flat (4 files, no `v2/`). This pass therefore synthesizes and gates; it does not repeat a conclusion.
2. **Convert positional hazard re-verified, cite sharpened (observed).** `_import_action_convert` still reads `entry = job.activities[int(index)]` (`views.py:2456`, inside `2446-2475`); `_import_action_remove_activity` still resolves via `_activity_id(entry, index) == target` (`views.py:2317`, inside `2307-2325`); `_activity_id` defined at `views.py:2301-2304`. Iteration 9 cited the remove range for both; the convert cite is corrected here. The mandatory convert-to-`activity_id` switch (R2) stands.
3. **Hash/dedup still unwired (observed).** `activity_content_hash` / `find_duplicate_groups` live only in `staging_validation.py:189-238`; zero call sites in `views.py`. The three legal wiring touchpoints (post-generate append guard, pre-topup count, pre-convert list) are unchanged.
4. **`ready-for-agent` set re-verified (observed).** Open `ready-for-agent` issues today: #95, #97, #98, #103, #104, #107 (six). Only #98 is on the staging critical path. The prompt's "sole ready-for-agent path" sentence still needs the qualifier from iteration 9.
5. **Gate contradiction resolved by this pass (observed → decision).** The committed `IMPLEMENTATION-GATE.md` says `STATUS: READY_FOR_IMPLEMENTATION`, but it was committed off-cycle (gate changes are 10th-iteration duty), names a self-referential base ref (its own branch), spans broader-than-one-change allowed paths (models + new 0030 migration + `curriculum_import.py` + `views.py` + `staging_validation.py` + three test files), and leaves the convert switch conditional while iterations 3/5/7/8/9 spec it as mandatory. This pass rewrites the gate to `STATUS: HOLD` with the narrowed flip conditions (§Decisions).
6. **Stale-number hazard persists (observed).** The loop prompt's cites (`views.py:2875-2876,2959-2960`, `views.py:3504`, `models.py:1998`, `models.py:1125-1127`) remain pre-shrink numbers. Current cites are §Files-inspected + Finding 2. Ticket drafts must cite current lines only.
7. **Uncommitted Phase A–E tree still pending human review (observed).** The `M`/`??` tree shape is unchanged since iteration 2. Supervisor cannot commit code; the human decision (review/commit/discard) is still open and is itself a HOLD reason.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, seam Steps 0–4 per iteration 8, ready-for-agent queue R1–R5 per iteration 9).
- **Gate set to `HOLD`** (see updated `IMPLEMENTATION-GATE.md`). Flip conditions to `READY_FOR_IMPLEMENTATION` at a future 10th iteration, all required together: (a) uncommitted Phase A–E tree human-reviewed/committed so the base ref is a clean commit hash; (b) allowed paths narrowed to the iteration-9 §Draft slice (convert block + three touchpoints + `staging_validation.py` iff canonicalization pick requires + `test_t54` + one new focused test + `docs/DATABASE.md` same-PR); (c) convert-to-`activity_id` switch mandatory with named reorder test; (d) non-self-referential base ref (`updated-tech` tip hash, verified); (e) open questions 2–4 answered (norm pick, report surface, M4 artifact shape); (f) zero blockers observed. Any single gap keeps `HOLD`.
- Ready-for-agent queue R1→R2→R3(M1→M3, M4 excluded)→R4 and label-hygiene proposals from iteration 9 stand without amendment; this pass does not re-grade drafts (no new evidence).
- PR packaging: stage and commit ONLY `docs/handoffs/` Markdown (`supervisor-iteration-0009.md`, `supervisor-iteration-0010.md`, `supervisor-cumulative.md`, updated `IMPLEMENTATION-GATE.md`); verify `git diff --cached --name-only` before commit; push `supervisor/aulalista-docs`; create one PR targeting `main` iff none exists; never merge/approve/close. If the cached diff shows any non-Markdown or non-`docs/handoffs/`/`docs/adr/` path, abort the commit and record why here (see §PR record).

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→10.) Blocks any future `READY_FOR_IMPLEMENTATION`.
2. Agent-ready (carry-over 3→10): recursive `_norm` on inner proposal text vs documented byte-comparison noise? Must be decided before any backfill slice.
3. Agent-ready (carry-over 5→10): duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? Assumed review-screen + pre-convert list until confirmed.
4. Agent-ready (carry-over 7→10): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? Needed before any M4 ticket exists.
5. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps (proposal; confirm counter source whenever convenient).
6. Prompt hygiene: qualify "sole ready-for-agent path" as "sole `ready-for-agent` issue **on the staging critical path**" and refresh stale pre-shrink line cites.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions in §Decisions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Consume staging work strictly in queue order R1 (docs-only M0 precision) → R2 (mandatory convert switch, tested) → R3 (M1→M3 slice, M4 excluded, JSON writes stay) → R4 (seams S5→S4→S2; S1 fused with M3). Acceptance: iteration-5 rows A2+A3+A4+A5+A8.
3. Upgrade #98 with the iteration-9 §Draft body before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order (#57 prerequisite → fused #53/#98/#54 → periphery).
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Next prompt refresh: carry the qualified #98 sentence and current line cites into the loop prompt so future passes stop re-deriving them.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: convert `views.py:2446-2475`, positional line `:2456`; remove `views.py:2307-2325`, resolve line `:2317`; `_activity_id` `views.py:2301-2304`; `staging_validation.py:189-238`; `models.py:1874-1896` incl. `clean()` `:1874-1880`; `test_t54:55-127`; `scripts/check_migrations.py`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iterations 5 (A1–A9), 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress), 7 (M0→M4 + per-step rollback), 8 (Steps 0–4, S1 fused with M3).
- Queue discipline R1→R2→R3(M4 excluded)→R4; `scripts/check_migrations.py` + `makemigrations --check` clean at every step; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58).
- Dedup/schema rules unchanged (report + human confirm; `exact` only with confirm; `same_title_diff_content` side-by-side; one merged section per title-key with badges; v1-keep vs `v2/`-bump with `.schema.json` + Python validator updated together).
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 11): re-check whether the working tree changed (Phase A–E committed, R1 wording fixed, convert switched, report wired, head past 0029). If moved, verify the touched R/M/S step against the cumulative synthesis + iteration-5 matrix; if unchanged, record "no new evidence" and advance the rotating phase (suggested: M4-export shape or report-surface pick, the two least-specified open questions). Checkpoint duties next due at iteration 20 (cumulative deltas + gate review + docs-only PR); final synthesis at iteration 100 — not due.

## PR record

- Staged set verified (`git diff --cached --name-only`): `docs/handoffs/IMPLEMENTATION-GATE.md`, `docs/handoffs/supervisor-cumulative.md`, `docs/handoffs/supervisor-iteration-0009.md`, `docs/handoffs/supervisor-iteration-0010.md` — Markdown under `docs/handoffs/` only, no code.
- Committed as `2889fa9` on `supervisor/aulalista-docs`, pushed to origin.
- PR: https://github.com/eliancanul/AulaLista/pull/112 (head `supervisor/aulalista-docs` → base `main`, docs-only, not merged — never merge per loop rules).
- Follow-up: this §PR record was filled after the push; recorded in a second append-only docs commit (no history rewrite).
