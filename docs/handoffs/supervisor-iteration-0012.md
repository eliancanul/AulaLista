# Supervisor iteration 0012 — curriculum staging join and relational model

Iteration: 12 | Phase focus: curriculum staging join and relational model
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–11)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `498a4df` (docs: gate stable activity identity slice) on top of `3848d49` (PR 112 record) on top of `2889fa9` (iteration-10 checkpoint). PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) already exists — no new PR duty until iteration 20.

Prior memory: `supervisor-iteration-0011.md` (gate off-cycle assessment 2/6, domain contracts, cite corrections) + `supervisor-cumulative.md` (spine 2→10) are the working memory; `-0010.md` (§PR record: PR 112 + HOLD gate) is the checkpoint record.

## Scope

Phase-focus: re-verify the curriculum staging join (title-keyed writes, reads, grouped view) and the ADR-0010 relational target against current code, not against prior handoffs. Spec only — nothing implemented. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 20).

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `docs/handoffs/IMPLEMENTATION-GATE.md`, `supervisor-iteration-0010.md`, `-0011.md`, `supervisor-cumulative.md`; `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127) / `roadmap.py` (242); `curriculum/migrations/` inventory (0001–0029, no 003x); `ls curriculum/schemas/` (4 files: README + activities/llm_trace/topics, no `v2/`); `python3 scripts/check_migrations.py` → OK; `rg` for `topic_title|subtopic_title`, `_activity_id|job.activities[int(index)]`, `activity_content_hash|find_duplicate_groups`, `select_related|in_bulk`, `roadmap_cursor|current_activity_id`, `DEBUG|SECRET_KEY|ALLOWED_HOSTS`; read `views.py:2217-2228` (generate writes), `views.py:2380-2391` (topup writes), `views.py:2301-2325` (identity + remove), `views.py:2420-2444` (`_grouped_activities`), `views.py:2446-2475` (convert), `staging_validation.py:29-80` (`requested_count` + `group_by_subtopic`), `staging_validation.py:189-238` (hash + dedup), `models.py:1110-1139` (snapshot resolution), `settings.py:8-21` (dev defaults); `git log --oneline -5 -- IMPLEMENTATION-GATE.md` (tip still `498a4df`, no second flip). `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** All line counts byte-identical to iterations 2–11; migrations head still 0029; `check_migrations.py` green; `schemas/` still flat; hash/dedup still unwired (zero pipeline call sites in `views.py`); convert still positional (`views.py:2456`); gate file untouched since `498a4df` — no second off-cycle flip this pass, so the iteration-11 pattern warning stays a single event, not yet a confirmed pattern.
2. **Staging join fully pinned to three current sites (observed — the phase deliverable).** Writes: `views.py:2221-2222` (generate) and `views.py:2383-2384` (topup) stamp `"topic_title": topic["titulo"]`, `"subtopic_title": sub["titulo"]`. Read: `staging_validation.py:55-80` (`group_by_subtopic`) matches with exact `==` on both titles (`entry.get("topic_title") == topic.get("titulo") and entry.get("subtopic_title") == sub.get("titulo")`), and its own docstring names this "la clave actual: título exacto" with "el hash de idempotencia (#98) y las tablas relacionales (#53)" as the future replacement — the code itself points at ADR-0010. Consumer: `views.py:2426` (`_grouped_activities` calls `group_by_subtopic(job.topics, job.activities)`), emitting `{"id": _activity_id(entry, index), "index": index, "entry": entry}` at `views.py:2428`. The prompt's `views.py:2875-2876,2959-2960` remain stale pre-shrink numbers — never cite them; the triple above is the citable join.
3. **Relational target unchanged and still future-only (observed).** ADR-0010 §Decisión-1 shape (`Topic(job_fk, titulo, pagina_inicio, pagina_fin, orden)`, `Subtopic(topic_fk, titulo, actividades_sugeridas, orden)`, `ActivityProposal(subtopic_fk, id_estable hex8, content_hash, …)`, JSON kept as output serialization during transition) has zero model/migration presence: no 003x migration, `schemas/` has no relational artifact. Backfill constraints (recalculate `content_hash`, report ambiguous, never touch human decisions or editorial state) remain spec-only.
4. **Adjacent cites re-confirmed, no drift (observed).** `_activity_id` `views.py:2301-2304`; remove resolves via `_activity_id(entry, index) == target` (`views.py:2317`); grouped view preserves both `id` and `index` (`views.py:2428`) so the R2 convert-to-`activity_id` switch has a ready read-side convention; snapshot N+1 site fixed (`models.py:1116` `select_related`, `models.py:1130` `in_bulk` with "Un solo query" comment); dev defaults `settings.py:8-21`; god-file sizes 2950/2038 (prompt's `views.py:3504`/`models.py:1998` stale); cursor reads all via `_roadmap_cursor.current_activity_id` (`views.py:2505,2579,2599,2634,2770,2807,2866` → 27-line service).
5. **Fused-decision spine unchanged (observed).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite (green again this pass), #58 stale epic body, #55/#56/#65 peripheral — no tracker re-pull this pass (that was iteration 9/10's read-only `gh` job; the qualified "sole `ready-for-agent` issue **on the staging critical path**" sentence stands).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, Steps 0–4 per iteration 8, queue R1–R5 per iteration 9, HOLD + cumulative per iteration 10, 2/6 gate scorecard per iteration 11).
- **Gate: no edit this pass (10th-iteration duty).** The on-disk `READY` slice (`498a4df`) is assessed, not countermanded: still 2/6 against iteration-10's flip conditions (narrowed paths + mandatory convert present; clean base ref, human-reviewed tree, open picks, zero blockers still open). The absence of a second flip is noted as weak positive evidence but changes nothing until iteration 20 resolves adopt-vs-revert.
- **Join-spec precision upgrade (this pass's contribution, no code):** any future R3/M1→M3 ticket must name all three join sites (two writes + `group_by_subtopic` read + `_grouped_activities` consumer), state the exact→FK cutover rule (new writes go to FKs; `group_by_subtopic` becomes a compatibility view over FK-joined rows during double-write, deleted only at M4), and require the exact-vs-normalized transition test (legacy `==` rows vs `_norm` hash rows must not silently merge — `same_title_diff_content` goes side-by-side to human). This closes the "where is the join?" vagueness without touching implementation.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→12.) Blocks any future supervisor `READY`.
2. Gate provenance: was `498a4df` (off-cycle READY after HOLD) deliberate override or accident? If deliberate, the loop rule reserving gate changes for 10th iterations needs a human-signed amendment. (Carry-over 11→12; one quiet pass does not answer it.)
3. Agent-ready (carry-over 3→12): recursive `_norm` on inner proposal text vs documented byte-comparison noise? Must precede any backfill slice — now sharpened: the backfill ticket must state which `_norm` scope it assumes.
4. Agent-ready (carry-over 5→12): duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? Assumed review-screen + pre-convert list until confirmed.
5. Agent-ready (carry-over 7→12): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? Needed before any M4 ticket exists.
6. Evidence debt (carry-over 11→12): name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (No pair observed again this pass — all cursor reads go through the 27-line service.)
7. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. At iteration 20, resolve the gate cleanly: adopt the narrowed `498a4df` slice verbatim WITH a clean `updated-tech` base ref + answered picks, or revert to `HOLD` with the 2/6 scorecard. Do not let a third state accumulate.
2. Consume staging work strictly R1 (docs-only M0 precision) → R2 (mandatory convert switch `views.py:2446-2475` positional `:2456` → `_activity_id` `:2301-2304`, tested) → R3 (M1→M3 slice naming all three join sites per §Decisions, M4 excluded, JSON writes stay) → R4 (seams S5→S4→S2; S1 fused with M3). Acceptance: iteration-5 rows A2+A3+A4+A5+A8.
3. Upgrade #98 with the iteration-9 §Draft body plus the iteration-12 triple-join cite before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order (#57 prerequisite → fused #53/#98/#54 → periphery).
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the triple-join cite table (`views.py:2221-2222,2383-2384` writes; `staging_validation.py:55-80` exact-`==` read; `views.py:2426,2428` consumer) plus the qualified #98 sentence so future passes stop re-deriving them.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: join writes `views.py:2221-2222,2383-2384`; join read `staging_validation.py:55-80`; consumer `views.py:2420-2444`; convert `views.py:2446-2475`, positional `:2456`; remove `views.py:2307-2325`, resolve `:2317`; `_activity_id` `views.py:2301-2304`; fixed N+1 site `models.py:1110-1139`; dev defaults `settings.py:8-21`; `staging_validation.py:189-238`; `test_t54:55-127`; `scripts/check_migrations.py`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iterations 5 (A1–A9), 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress), 7 (M0→M4 + per-step rollback), 8 (Steps 0–4, S1 fused with M3).
- Queue discipline R1→R2→R3(M4 excluded)→R4; `scripts/check_migrations.py` + `makemigrations --check` clean at every step; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58).
- Dedup/schema rules unchanged (report + human confirm; `exact` only with confirm; `same_title_diff_content` side-by-side; one merged section per title-key with badges; v1-keep vs `v2/`-bump with `.schema.json` + Python validator updated together).
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 13): re-check whether the working tree changed (Phase A–E committed, R1 wording fixed, convert switched, report wired, head past 0029) and whether the gate file moved again (a second off-cycle flip would confirm the pattern flagged in iteration 11). If moved, verify the touched R/M/S step against the cumulative synthesis + iteration-5 matrix; if unchanged, record "no new evidence" and advance the rotating phase (suggested: idempotency wiring touchpoints or M4-export shape, the two least-specified areas after this pass pinned the join). Checkpoint duties next due at iteration 20 (cumulative deltas + gate review + docs-only PR); final synthesis at iteration 100 — neither is due now.
