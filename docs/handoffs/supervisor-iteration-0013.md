# Supervisor iteration 0013 — idempotency, deduplication, and ambiguity policy

Iteration: 13 | Phase focus: idempotency, deduplication, and ambiguity policy
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–12)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `498a4df` (docs: gate stable activity identity slice) on top of `3848d49` (PR 112 record) on top of `2889fa9` (iteration-10 checkpoint). PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) already exists — no new PR duty until iteration 20.

Prior memory: `supervisor-iteration-0012.md` (triple-join cite) + `supervisor-iteration-0011.md` (2/6 gate scorecard) + `supervisor-cumulative.md` (spine 2→10) are the working memory.

## Scope

Phase-focus: re-verify the idempotency key, the duplicate-report function, and the ambiguity policy against current code, not against prior handoffs. Spec only — nothing implemented. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 20).

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `docs/handoffs/IMPLEMENTATION-GATE.md`, `supervisor-iteration-0011.md`, `-0012.md`, `supervisor-cumulative.md`; `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` inventory (0001–0029, no 003x); `ls curriculum/schemas/` (4 files: README + activities/llm_trace/topics, no `v2/`); `python3 scripts/check_migrations.py` → OK; `rg` for `activity_content_hash|find_duplicate_groups|_activity_id|group_by_subtopic|topic_title|int(index)` across `curriculum/views.py` + `staging_validation.py` + `test_t54`; full read of `staging_validation.py:25-26` (`_norm`), `:55-80` (`group_by_subtopic`), `:189-238` (hash + dedup), `test_t54:108-127` (hash/dedup tests), `views.py:2217-2257` (generate writes + incremental persist), `views.py:2301-2325` (identity + remove), `views.py:2343-2362` (topup pending count), `views.py:2380-2412` (topup writes), `views.py:2420-2444` (`_grouped_activities`), `views.py:2446-2475` (convert); `git log --oneline -5 -- IMPLEMENTATION-GATE.md` (tip still `498a4df`, no second flip). `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** All line counts byte-identical to iterations 2–12; migrations head still 0029; `check_migrations.py` green; `schemas/` still flat; gate file untouched since `498a4df` — the iteration-11 pattern warning stays a single off-cycle event, not yet a confirmed pattern.
2. **Hash spec pinned to current lines, with one normalization asymmetry sharpened (observed — the phase deliverable).** `activity_content_hash` (`staging_validation.py:189-208`): SHA256 over canonical `{"topic": _norm(topic_title), "subtopic": _norm(subtopic_title), "proposal": <json-sorted blob>}`; excludes `id/selected/added_by_topup/is_valid/issues` per docstring `:190-196`. `_norm` (`:25-26`) is NFKC + casefold + trim — but it is applied ONLY to the two outer staging keys, NOT recursively to inner proposal strings: the proposal blob is `json.dumps(proposal, sort_keys=True, ensure_ascii=False, default=str)` (`:203-205`) with no `_norm` on `title/objective/micro_lesson/questions` values. So two retries differing only by case/whitespace inside proposal text hash DIFFERENTLY (byte-comparison noise), while two rows differing only by case in `topic_title` hash the SAME. This is the concrete form of open question 2 — now citable instead of abstract.
3. **Dedup report pinned, still unwired, key-scope mismatch recorded (observed).** `find_duplicate_groups` (`staging_validation.py:211-238`) returns `{"exact": [[indices]], "same_title_diff_content": [...]}` without merging anything (`:211-212` docstring "sin fusionar nada (reporte para humana, #98)"). `exact` groups by full `activity_content_hash` (`:224`); `same_title_diff_content` groups by `_norm` triple `(topic_title, subtopic_title, proposal.title)` with >1 distinct hash (`:232,236`). `rg` confirms ZERO call sites in `curriculum/views.py` or anywhere under `curriculum/` outside the definition + `test_t54:120-127` imports — the three legal wiring touchpoints (post-generate append guard, pre-topup count, pre-convert list) remain spec-only. Mismatch: the ambiguous key normalizes `proposal.title` (`:232`) but the hash does not normalize any proposal string (`:203-205`), so a case-only proposal-title variant lands in `same_title_diff_content` rather than `exact` — policy-correct (human sees it) but the ticket must state which bucket it expects.
4. **Ambiguity policy holds in spec, has no read-side surface (observed).** ADR-0010 §Decisión-2 (AMBIGUO → human review, never silent merge) + `validate_activities` rule "inválida nunca seleccionada para convertir" (`staging_validation.py:164-165`) + `test_t54:119-127` (report asserts `exact == [[0,1]]`, `same_title_diff_content == [[0,1,2]]`, no merge performed) are consistent. But `_grouped_activities` (`views.py:2420-2443`) emits only `{"id", "index", "entry"}` (`:2428`) with `faltantes` counts — no `exact`/`ambiguous` badges, no pre-convert list. `group_by_subtopic` (`:55-80`) matches with exact `==` (`:76-77`) while dedup keys with `_norm` (`:232`) — legacy grouping and dedup grouping disagree on case/whitespace today. Any R3/M-backfill ticket must therefore require the exact-vs-normalized transition test (legacy `==` rows vs `_norm` hash rows must not silently merge).
5. **Retry-duplication path re-confirmed (observed).** Generate (`views.py:2218-2251`) stamps fresh `uuid4().hex[:8]` per proposal (`:2220`) with title keys (`:2221-2222`) and persists incrementally (`:2240-2251`); topup (`:2380-2412`) appends with fresh id (`:2382`) + title keys (`:2383-2384`) + `added_by_topup` (`:2389`). Neither path calls `activity_content_hash`/`find_duplicate_groups` before append; topup pending-count (`views.py:2346-2362`) counts via `group_by_subtopic` length (`:2348-2349`), so a duplicated retry inflates `existing` and suppresses — or a same-title-different-content retry inflates the count while hiding the ambiguity. Convert (`views.py:2446-2475`, positional `:2456`) has no pre-convert duplicate list. All three touchpoints stay unwired.
6. **Fused-decision spine unchanged (observed).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite (green again this pass), #58 stale epic body, #55/#56/#65 peripheral — no tracker re-pull this pass (that was iteration 9/10's read-only `gh` job; the qualified "sole `ready-for-agent` issue **on the staging critical path**" sentence stands).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, Steps 0–4 per iteration 8, queue R1–R5 per iteration 9, HOLD + cumulative per iteration 10, 2/6 gate scorecard per iteration 11, triple-join cite per iteration 12).
- **Gate: no edit this pass (10th-iteration duty).** The on-disk `READY` slice (`498a4df`) is assessed, not countermanded: still 2/6 against iteration-10's flip conditions. The absence of a second flip is noted as weak positive evidence but changes nothing until iteration 20 resolves adopt-vs-revert.
- **Idempotency-spec precision upgrade (this pass's contribution, no code):** any future R3/M-backfill ticket must (a) state the `_norm` scope pick explicitly — outer-keys-only (current `:189-208`) vs recursive-`_norm` on inner proposal text — because the pick decides which retries land in `exact` vs `same_title_diff_content`; (b) name all three wiring touchpoints with current lines (post-generate `views.py:2218-2251`, pre-topup `views.py:2343-2362`, pre-convert `views.py:2446-2475`) and require report-before-write at each (append guard / count adjustment / pre-convert list); (c) require the duplicate-report surface pick (review-screen section + pre-convert list assumed until confirmed) and the exact-vs-normalized transition test. This closes the "where does dedup plug in?" vagueness without touching implementation.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→13.) Blocks any future supervisor `READY`.
2. Gate provenance: was `498a4df` (off-cycle READY after HOLD) deliberate override or accident? If deliberate, the loop rule reserving gate changes for 10th iterations needs a human-signed amendment. (Carry-over 11→13; two quiet passes do not answer it.)
3. Agent-ready (carry-over 3→13, now sharpened with lines): recursive `_norm` on inner proposal text vs current outer-keys-only (`staging_validation.py:25-26` vs `:203-205`)? Must precede any backfill slice — the backfill ticket must state which scope it assumes, since case-only proposal variants change buckets.
4. Agent-ready (carry-over 5→13): duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? Assumed review-screen + pre-convert list until confirmed. `_grouped_activities` (`views.py:2420-2443`) currently emits no badges.
5. Agent-ready (carry-over 7→13): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? Needed before any M4 ticket exists.
6. Evidence debt (carry-over 11→13): name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (No pair observed again this pass — all cursor reads go through the 27-line service.)
7. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. At iteration 20, resolve the gate cleanly: adopt the narrowed `498a4df` slice verbatim WITH a clean `updated-tech` base ref + answered picks, or revert to `HOLD` with the 2/6 scorecard. Do not let a third state accumulate.
2. Consume staging work strictly R1 (docs-only M0 precision) → R2 (mandatory convert switch `views.py:2446-2475` positional `:2456` → `_activity_id` `:2301-2304`, tested) → R3 (M1→M3 slice naming all three wiring touchpoints per §Decisions with the `_norm`-scope pick stated, M4 excluded, JSON writes stay) → R4 (seams S5→S4→S2; S1 fused with M3). Acceptance: iteration-5 rows A2+A3+A4+A5+A8.
3. Upgrade #98 with the iteration-9 §Draft body plus the iteration-12 triple-join cite plus the iteration-13 `_norm`-scope asymmetry (`:25-26` vs `:203-205` vs `:232`) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order (#57 prerequisite → fused #53/#98/#54 → periphery).
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the triple-join cite table (`views.py:2221-2222,2383-2384` writes; `staging_validation.py:55-80` exact-`==` read; `views.py:2426,2428` consumer) plus the idempotency cite table (`staging_validation.py:189-208` hash, `:211-238` report, zero pipeline call sites, touchpoints `views.py:2218-2251/2343-2362/2446-2475`) plus the qualified #98 sentence so future passes stop re-deriving them.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: hash `staging_validation.py:189-208`, `_norm` `:25-26`, report `:211-238`, join read `:55-80` exact-`==` `:76-77`, ambiguous key `:232`; join writes `views.py:2221-2222,2383-2384`; generate persist `:2238-2251`; topup pending `:2343-2362`; consumer `views.py:2420-2444`; convert `views.py:2446-2475`, positional `:2456`; remove `views.py:2307-2325`, resolve `:2317`; `_activity_id` `views.py:2301-2304`; fixed N+1 site `models.py:1110-1139`; dev defaults `settings.py:8-21`; `test_t54:55-127`; `scripts/check_migrations.py`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iterations 5 (A1–A9), 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress), 7 (M0→M4 + per-step rollback), 8 (Steps 0–4, S1 fused with M3).
- Queue discipline R1→R2→R3(M4 excluded)→R4; `scripts/check_migrations.py` + `makemigrations --check` clean at every step; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58).
- Dedup/schema rules unchanged (report + human confirm; `exact` only with confirm; `same_title_diff_content` side-by-side; `_norm`-scope pick stated; one merged section per title-key with badges; v1-keep vs `v2/`-bump with `.schema.json` + Python validator updated together).
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 14): re-check whether the working tree changed (Phase A–E committed, R1 wording fixed, convert switched, report wired, head past 0029) and whether the gate file moved again (a second off-cycle flip would confirm the pattern flagged in iteration 11). If moved, verify the touched R/M/S step against the cumulative synthesis + iteration-5 matrix; if unchanged, record "no new evidence" and advance the rotating phase (suggested: M4-export shape or report-surface pick, the two least-specified open questions after this pass pinned idempotency). Checkpoint duties next due at iteration 20 (cumulative deltas + gate review + docs-only PR); final synthesis at iteration 100 — neither is due now.
