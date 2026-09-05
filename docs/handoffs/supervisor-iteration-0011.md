# Supervisor iteration 0011 — baseline architecture and domain contracts

Iteration: 11 | Phase focus: baseline architecture and domain contracts
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–10)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `498a4df` (docs: gate stable activity identity slice) on top of `3848d49` (PR 112 record) on top of `2889fa9` (iteration-10 checkpoint). PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) already exists — no new PR duty until iteration 20.

Prior memory: `supervisor-iteration-0010.md` (§PR record: PR 112 + HOLD gate) + `supervisor-cumulative.md` (spine 2→10) are the working memory; `-0009.md` (queue R1–R5 + draft), `-0008.md` (seams S1–S5, Steps 0–4), `-0007.md` (M0→M4 + rollback), `-0006.md` (envelope), `-0005.md` (matrix A1–A9), `-0003.md` (idempotency), `-0002.md` (staging join). No `-0001.md` / `-0004.md` exist; gaps accepted.

## Scope

Phase-focus: re-verify the baseline architecture and domain contracts against current code (not against prior handoffs), and extend/correct the iteration-10 checkpoint where the tree or the gate moved. Spec only — nothing implemented. Gate edits are 10th-iteration duty; this pass does NOT edit `IMPLEMENTATION-GATE.md` even though it changed off-cycle (see Finding 1).

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `docs/handoffs/IMPLEMENTATION-GATE.md` (current on-disk `READY` vs `2889fa9` `HOLD` parent), `supervisor-iteration-0009.md`, `-0010.md`, `supervisor-cumulative.md`; `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` inventory (0001–0029, no 003x); `ls curriculum/schemas/` (4 files, no `v2/`); `python3 scripts/check_migrations.py` → OK; `rg` for `_activity_id|job.activities[int(index)]|activity_content_hash|find_duplicate_groups` (views + staging_validation), `topic_title|subtopic_title` (views), `select_related|in_bulk` (models), `DEBUG|SECRET_KEY|ALLOWED_HOSTS` (settings); read `views.py:2301-2305,2315-2319,2454-2458` (identity/convert), `views.py:2221-2222,2383-2384` (title-keyed staging writes), `models.py:1110-1135` (snapshot resolution), `settings.py:8-21` (dev defaults); `git log --oneline -8 -- IMPLEMENTATION-GATE.md` + `git show 498a4df --stat`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **Gate flipped off-cycle after the HOLD checkpoint (observed, the one thing that moved).** `2889fa9` (iteration 10) set `STATUS: HOLD` with six flip conditions; `498a4df` (human, ~2 min later, "docs: gate stable activity identity slice") rewrote it to `STATUS: READY_FOR_IMPLEMENTATION` with a deliberately narrower slice (`curriculum/views.py` + `tests/test_t15_curriculum_import.py` + `docs/handoffs/` only; out-of-scope: models/migrations/schemas/staging-validation-redesign). This repeats the exact off-cycle pattern iteration 9 Finding 6 flagged. Supervisor position: the HOLD reasoning from iteration 10 is NOT re-litigated here (gate duty returns at iteration 20); the narrowed slice is assessed against the six flip conditions in §Decisions without editing the gate file.
2. **No new tree evidence (observed).** All line counts byte-identical to iterations 2/3/5/6/7/8/9/10; migrations head still 0029; `check_migrations.py` green; `schemas/` still flat; hash/dedup still unwired (`activity_content_hash`/`find_duplicate_groups` defined `staging_validation.py:189-238`, zero pipeline call sites in `views.py`); convert still positional (`entry = job.activities[int(index)]`, `views.py:2456`, inside `2446-2475`); remove still resolves via `_activity_id(entry, index) == target` (`views.py:2317`, def `views.py:2301-2304`). The uncommitted Phase A–E tree shape is unchanged since iteration 2.
3. **Domain contracts hold on current code (observed, the phase deliverable).** `CONTEXT.md` vocabulary maps cleanly: human-only EditorialReviewer publication, teacher-only ClassroomSession activation, AI-proposes-only staging (`ai_assisted=True`, never auto-publish per `docs/DATABASE.md`), immutable SHA256 snapshots (`PublishedPackageSnapshot`/`PublishedRoadmapSnapshot`; sessions freeze base + per-activity snapshot refs per `teacher-flow.md:45,93`), synthetic DemoPackage with zero pedagogical claims (`DESIGN.md:7`, `implementation-current.md:19-21`). No contradicting code path observed this pass; no contract text changed.
4. **Prompt's core-finding cites corrected against current lines (observed).**
   - Title-keyed staging: CONFIRMED as writes at `views.py:2221-2222` and `views.py:2383-2384` (`"topic_title": topic["titulo"]`, `"subtopic_title": sub["titulo"]`). The prompt's `views.py:2875-2876,2959-2960` remain stale pre-shrink numbers — never cite them.
   - God-files: CONFIRMED as size facts (`views.py` 2950 / `models.py` 2038; largest functions/classes per iteration 8 Finding 1). The prompt's `views.py:3504` / `models.py:1998` are stale — the files are shorter than those numbers.
   - N+1 around prompt's `models.py:1125-1127`: SUPERSEDED. Current `models.py:1110-1135` shows `select_related("assignment")` plus a deliberate single-query `PublishedPackageSnapshot.objects.in_bulk(...)` with the comment "Un solo query (evita N+1 del get por actividad)". The N+1 at that site is FIXED, not open. Any future N+1 claim must name a new unbatched loop with lines, not the prompt's cite.
   - Duplicated cursor logic: NOT CONFIRMED on current tree. Cursor reads go through `_roadmap_cursor.current_activity_id` (`views.py:2505,2579,2599,2634` → `services/roadmap_cursor.py`, 27 lines, 1 fn). Either name the duplicated pair with current lines or retire the claim — it must not ride as an uncited bullet.
   - Secrets/debug: CONFIRMED as dev-defaults (`settings.py:8-21`: `SECRET_KEY` falls back to `aulalista-t01-local-development-only`, `DEBUG` defaults `True`, `ALLOWED_HOSTS` defaults `*`, with a header comment requiring explicit `AULALISTA_SECRET_KEY` + `AULALISTA_DEBUG=False` + explicit hosts in any deployment). Iteration-6 envelope (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress) stands; no new egress observed.
5. **Fused-decision spine unchanged (observed).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite (`check_migrations.py` green again this pass), #58 stale epic body, #55/#56/#65 peripheral — no tracker evidence re-pulled this pass (read-only `gh` inspection was iteration 9/10's job; the six-`ready-for-agent` set #95/#97/#98/#103/#104/#107 with #98 sole on-path stands until a pass re-verifies it).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, seam Steps 0–4 per iteration 8, queue R1–R5 per iteration 9, HOLD + cumulative per iteration 10).
- **Gate: no edit this pass (10th-iteration duty).** Assessment only — the `498a4df` narrowed slice against iteration-10's six flip conditions: (a) Phase A–E tree human-reviewed/committed → STILL OPEN (status shape unchanged); (b) narrowed allowed paths → IMPROVED (views.py + one test file + handoffs is genuinely one bounded change, unlike the pre-10 broad list); (c) mandatory convert-to-`activity_id` + reorder test → PRESENT in the new gate's §Required behavior (matches R2); (d) non-self-referential base ref → STILL OPEN (base ref is `supervisor/aulalista-docs` at its own commit); (e) open questions 2–4 answered (`_norm` pick, report surface, M4 shape) → STILL OPEN (M4 correctly excluded, but the picks are undecided); (f) zero blockers → STILL OPEN (blocker (a) persists). Score: 2/6 satisfied. The parallel coding lane validates the gate independently; supervisor records HOLD-pending-20th-review and does not countermand the on-disk file outside checkpoint duty.
- Prompt-hygiene corrections from iteration 10 stand and gain two rows from Finding 4: cite `views.py:2221-2222,2383-2384` for title keys, `views.py:2456` / `:2317` / `:2301-2304` for identity, `models.py:1110-1135` for the fixed N+1 site, `settings.py:8-21` for dev defaults; retire-or-cite the cursor-duplication bullet.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→11.) Blocks any future supervisor `READY`.
2. Gate provenance: was `498a4df` (off-cycle READY after HOLD) a deliberate human override or an accidental commit? If deliberate, the loop rule reserving gate changes for 10th iterations needs a human-signed amendment; if accidental, iteration 20 reverts-or-adopts with reasoning. (New this pass.)
3. Agent-ready (carry-over 3→11): recursive `_norm` on inner proposal text vs documented byte-comparison noise? Must precede any backfill slice.
4. Agent-ready (carry-over 5→11): duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? Assumed review-screen + pre-convert list until confirmed.
5. Agent-ready (carry-over 7→11): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? Needed before any M4 ticket exists.
6. Evidence debt (new): name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (Finding 4.)
7. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. At iteration 20, resolve the gate cleanly: either adopt the narrowed `498a4df` slice verbatim WITH a clean `updated-tech` base ref + answered picks, or revert to `HOLD` with the 2/6 scorecard above. Do not let a third off-cycle flip accumulate.
2. Consume staging work strictly R1 (docs-only M0 precision) → R2 (mandatory convert switch, tested) → R3 (M1→M3 slice, M4 excluded, JSON writes stay) → R4 (seams S5→S4→S2; S1 fused with M3). Acceptance: iteration-5 rows A2+A3+A4+A5+A8.
3. Upgrade #98 with the iteration-9 §Draft body before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order (#57 prerequisite → fused #53/#98/#54 → periphery).
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the Finding-4 cite table plus the qualified #98 sentence ("sole `ready-for-agent` issue **on the staging critical path**") so future passes stop re-deriving them.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: convert `views.py:2446-2475`, positional `:2456`; remove `views.py:2307-2325`, resolve `:2317`; `_activity_id` `views.py:2301-2304`; title-keyed writes `views.py:2221-2222,2383-2384`; fixed N+1 site `models.py:1110-1135`; dev defaults `settings.py:8-21`; `staging_validation.py:189-238`; `test_t54:55-127`; `scripts/check_migrations.py`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iterations 5 (A1–A9), 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress), 7 (M0→M4 + per-step rollback), 8 (Steps 0–4, S1 fused with M3).
- Queue discipline R1→R2→R3(M4 excluded)→R4; `scripts/check_migrations.py` + `makemigrations --check` clean at every step; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58).
- Dedup/schema rules unchanged (report + human confirm; `exact` only with confirm; `same_title_diff_content` side-by-side; one merged section per title-key with badges; v1-keep vs `v2/`-bump with `.schema.json` + Python validator updated together).
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 12): re-check whether the working tree changed (Phase A–E committed, R1 wording fixed, convert switched, report wired, head past 0029) and whether the gate file moved again (a second off-cycle flip would confirm a pattern needing a rule amendment). If moved, verify the touched R/M/S step against the cumulative synthesis + iteration-5 matrix; if unchanged, record "no new evidence" and advance the rotating phase (suggested: M4-export shape or report-surface pick, the two least-specified open questions). Checkpoint duties next due at iteration 20 (cumulative deltas + gate review + docs-only PR); final synthesis at iteration 100 — neither is due now.
