# Supervisor iteration 0014 — ADR and documentation contradiction reconciliation

Iteration: 14 | Phase focus: ADR and documentation contradiction reconciliation
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–13)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `498a4df` (docs: gate stable activity identity slice). PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) already exists — no PR duty until iteration 20.

Prior memory: `supervisor-iteration-0013.md` (idempotency `_norm`-scope asymmetry) + `-0012.md` (triple-join cite) + `-0011.md` (2/6 gate scorecard) + `supervisor-cumulative.md` (spine 2→10) are the working memory.

## Scope

Phase-focus: reconcile ADR text against documentation and current code, distinguishing real contradictions (spec must pick a reading) from already-reconciled vocabulary. Spec only — nothing implemented. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 20). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md` (+ `git diff` of its uncommitted delta), `docs/implementation-current.md` (+ diff), `docs/teacher-flow.md` (+ diff), `docs/adr/0001,0002,0004,0005,0006,0008,0009,0010`, `docs/handoffs/IMPLEMENTATION-GATE.md`, `supervisor-iteration-0010/0011/0012/0013.md`, `supervisor-cumulative.md`; `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` inventory (0001–0029, no 003x); `ls -R curriculum/schemas/` (flat: README + activities/llm_trace/topics `.schema.json`, no `v2/`); `python3 scripts/check_migrations.py` → OK; `rg` for `activity_content_hash|find_duplicate_groups` (zero hits in `views.py`/`models.py`), `_activity_id|int(index)` (convert `:2456` vs remove `:2317`), `added_by_topup` (validator/schema/DATABASE/views); full read `staging_validation.py:20` (`ACTIVITY_KEYS`), `:25-26` (`_norm`), `:55-80` (`group_by_subtopic`), `:189-238` (hash + dedup); `models.py:1874-1896` (`clean()` docstring); `git log --oneline -5 -- IMPLEMENTATION-GATE.md` (tip still `498a4df`, no second flip). `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** All line counts byte-identical to iterations 2–13; migrations head still 0029; `check_migrations.py` green; `schemas/` still flat; hash/dedup still unwired; convert still positional (`views.py:2456`); gate file untouched since `498a4df` — the iteration-11 single-event warning stands, still not a confirmed pattern.
2. **C1 — ADR-0010 overstates hash normalization (observed, REAL contradiction).** ADR-0010 §Decisión-2: "`activity_content_hash()` — SHA256 canónico de `(topic, subtema, proposal)` normalizados (NFKC+casefold+trim)". Code: `_norm` (`staging_validation.py:25-26`, NFKC+casefold+trim) is applied ONLY to `topic`/`subtopic` (`:201-202`); the proposal blob is `json.dumps(proposal, sort_keys=True, ensure_ascii=False, default=str)` (`:203-205`) with NO `_norm` on inner strings — while the ambiguous key DOES `_norm(proposal.title)` (`:232`). The module docstring `:192` repeats the overstated "topic, subtema y proposal canónico" phrasing. Reconciliation: the ADR sentence must be read narrowly as outer-keys-only until an R1 docs-only patch corrects it to "`topic/subtema` normalizados; `proposal` byte-canónico ordenado, sin `_norm` recursivo" + states the scope pick. This is the citable form of open question 3.
3. **C2 — `DATABASE.md` Deuda-1 predates ADR-0010 (observed, REAL contradiction).** `docs/DATABASE.md:103-105` says JSON-hierarchy is a "decisión consciente para el prototipo; revisar antes de escalar (nuevo ADR)" — but ADR-0010 already IS that new ADR (accepted, fused #53/#98/#54) and the Deuda item never cites it; the entities table (`:10-23`) lists no future Topic/Subtopic/ActivityProposal rows. The uncommitted `git diff` on `DATABASE.md` adds only test/migration conventions, not the ADR-0010 pointer. Reconciliation: Deuda-1 must cite ADR-0010 as the accepted future + transition rule (JSON kept as output serialization); entities table gains a "futuro ADR-0010" note. Docs-only R1.
4. **C3 — `models.py:1875` cites a `schemas/v1` path that does not exist (observed, REAL contradiction).** `clean()` docstring: "Valida los JSONField contra `curriculum/schemas/v1` (#54)" — but `ls -R curriculum/schemas/` shows flat `*.schema.json` files, no `v1/` directory. ADR-0010 §Consecuencias reserves `schemas/v2/` for breaking changes, which is consistent as future, but the current-path half of the sentence is wrong. Reconciliation: docstring path must read `curriculum/schemas/*.schema.json` (current) with `v2/` reserved for bumps. Docs-only R1. Verified non-contradiction alongside: `clean()` validates only non-empty payloads + `save()` does not call `clean()` (`models.py:1874-1879`) matches ADR-0010 §Contexto exactly.
5. **C4 — `implementation-current.md` header is a main-snapshot, not a working-tree record (observed, SCOPE contradiction).** Header: Rama `main`, Fecha 22-ago-2026, commit `d4fcb99`, "Suite actual: 238 pruebas". Current reality: branch `supervisor/aulalista-docs`, HEAD `498a4df`, uncommitted Phase A–E tree (`views.py` −808-line-dominant diffstat per `git diff --stat`). The uncommitted diff ADDS the Ollama-pipeline paragraph + teacher-ownership fix + migration-convention lines — genuine precision upgrades, but the header was not bumped. Also "no usa … LLM" was corrected in-diff to "sí usa LLM local (Ollama `qwen2.5:14b`) solo para staging" — the old sentence contradicted `curriculum/prompts/` + `settings.py` LLM keys. Reconciliation: declare doc scope explicitly — `implementation-current.md` = last-reviewed `main` snapshot; the working tree is recorded ONLY in `docs/handoffs/`. R1 patch: bump header (branch/commit/date/suite) or add a scope banner. Never cite this file for line numbers.
6. **C5 — roadmap-state vocabulary: reconciled EXCEPT one ADR-0006 omission (observed, MINOR).** `teacher-flow.md:116-120` already maps `ACTUAL`=`actual`, `DISPONIBLE`=`disponible`, `COMPLETADA`=`completado`, `BLOQUEADA`=`bloqueado`, `visto` manual-only, MAYÚSCULAS runtime vs minúsculas visual — consistent with `DESIGN.md:72-78` and `CONTEXT.md`. BUT ADR-0006 §Consecuencias lists only "`ACTUAL`, `DISPONIBLE` y `COMPLETADA` … como texto" — omits `BLOQUEADA`/`visto`. Reconciliation: ADR-0006 bullet is incomplete, not wrong; R1 appends the missing two states with the teacher-flow cite. No ticket may claim a terminology contradiction beyond this.
7. **Verified NON-contradictions (observed, close the loop on re-derivation).** Session-snapshot freeze: `teacher-flow.md:45,93` + `CONTEXT.md:93` + ADR-0006:10,18 agree (base + per-activity refs, later corrections never rewrite active sessions). Authority: human-EditorialReviewer-publishes / teacher-activates / AI-proposes-only consistent across `CONTEXT.md`, `DESIGN.md:9`, `teacher-flow.md:47-59`, ADR-0002, ADR-0006:20. `added_by_topup` optionality: `DATABASE.md:87` (optional) + `schemas/activities.schema.json:29` (boolean, non-required) + `staging_validation.py:20` (`ACTIVITY_KEYS` omits it) + validator `:139` (subset-check on missing only, extras pass) + `views.py` writes (topup stamps it, generate does not) — all consistent; NOT a contradiction. ADR-0001/0004/0005/0008/0009 show no text contradicting current docs.
8. **Fused-decision spine unchanged (observed).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite (green again this pass), #58 stale epic body, #55/#56/#65 peripheral — no tracker re-pull this pass (that was iteration 9/10's read-only `gh` job; the qualified "sole `ready-for-agent` issue **on the staging critical path**" sentence stands).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, Steps 0–4 per iteration 8, queue R1–R5 per iteration 9, HOLD + cumulative per iteration 10, 2/6 gate scorecard per iteration 11, triple-join cite per iteration 12, `_norm`-scope asymmetry per iteration 13).
- **Gate: no edit this pass (10th-iteration duty).** On-disk `READY` slice (`498a4df`) assessed, not countermanded: still 2/6 against iteration-10's flip conditions. Three quiet passes, no second flip.
- **Contradiction-reconciliation contribution (this pass, no code):** C1–C5 above convert five recurring re-derivation costs into citable R1 docs-only patches: (a) ADR-0010 §Decisión-2 + module docstring `:192` narrowed to outer-keys-only with the scope pick stated; (b) `DATABASE.md` Deuda-1 + entities table cite ADR-0010; (c) `models.py:1875` docstring path corrected to flat `*.schema.json`; (d) `implementation-current.md` header/scope banner bumped; (e) ADR-0006 consequences bullet completed with `BLOQUEADA`/`visto`. All five are R1 (docs-only, no migration, no behavior) and must land BEFORE any R3/M-backfill ticket, since backfill wording depends on (a).

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→14.) Blocks any future supervisor `READY`.
2. Gate provenance: was `498a4df` (off-cycle READY after HOLD) deliberate override or accident? If deliberate, the loop rule reserving gate changes for 10th iterations needs a human-signed amendment. (Carry-over 11→14; three quiet passes do not answer it.)
3. Agent-ready (carry-over 3→14, now citable as C1): recursive `_norm` on inner proposal text vs current outer-keys-only (`staging_validation.py:25-26` vs `:203-205` vs `:232` vs ADR-0010 §Decisión-2)? Must precede any backfill slice.
4. Agent-ready (carry-over 5→14): duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? Assumed review-screen + pre-convert list until confirmed. `_grouped_activities` (`views.py:2420-2443`) emits no badges.
5. Agent-ready (carry-over 7→14): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? Needed before any M4 ticket exists.
6. Evidence debt (carry-over 11→14): name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (No pair observed again — all cursor reads via the 27-line service: `views.py:2505,2579,2599,2634,2770,2807,2866`.)
7. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. At iteration 20, resolve the gate cleanly: adopt the narrowed `498a4df` slice verbatim WITH a clean `updated-tech` base ref + answered picks, or revert to `HOLD` with the 2/6 scorecard. Do not let a third state accumulate.
2. Land the five R1 doc-precision patches (C1–C5) as the next docs-only PR content: ADR-0010 normalization sentence, `DATABASE.md` Deuda-1 pointer, `models.py:1875` docstring path (docstring-only edit, still R1), `implementation-current.md` scope banner, ADR-0006 states bullet. Then consume staging work strictly R1 → R2 (mandatory convert switch `views.py:2446-2475` positional `:2456` → `_activity_id` `:2301-2304`, tested) → R3 (M1→M3 slice, M4 excluded) → R4 (seams S5→S4→S2; S1 fused with M3). Acceptance: iteration-5 rows A2+A3+A4+A5+A8.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + iteration-13/14 `_norm`-scope asymmetry (C1) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order (#57 prerequisite → fused #53/#98/#54 → periphery).
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the triple-join cite table (`views.py:2221-2222,2383-2384` writes; `staging_validation.py:55-80` exact-`==` read; `views.py:2426,2428` consumer) + the idempotency cite table (`staging_validation.py:189-208` hash, `:211-238` report, zero pipeline call sites, touchpoints `views.py:2218-2251/2343-2362/2446-2475`) + the C1–C5 reconciliation table so future passes stop re-deriving them.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: hash `staging_validation.py:189-208`, `_norm` `:25-26`, proposal blob `:203-205`, ambiguous key `:232`, report `:211-238`, join read `:55-80` exact-`==` `:76-77`; join writes `views.py:2221-2222,2383-2384`; generate persist `:2238-2251`; topup pending `:2343-2362`; consumer `views.py:2420-2444`; convert `views.py:2446-2475`, positional `:2456`; remove `views.py:2307-2325`, resolve `:2317`; `_activity_id` `views.py:2301-2304`; fixed N+1 site `models.py:1110-1139`; `clean()` `models.py:1874-1896` with path caveat C3; dev defaults `settings.py:8-21`; `test_t54:55-127`; `scripts/check_migrations.py`; migrations head 0029; ADR-0010 §Decisión-2 with C1 caveat; `DATABASE.md:103-105` with C2 caveat), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iterations 5 (A1–A9), 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress), 7 (M0→M4 + per-step rollback), 8 (Steps 0–4, S1 fused with M3).
- Queue discipline R1→R2→R3(M4 excluded)→R4; `scripts/check_migrations.py` + `makemigrations --check` clean at every step; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58).
- Dedup/schema rules unchanged (report + human confirm; `exact` only with confirm; `same_title_diff_content` side-by-side; `_norm`-scope pick stated per C1; one merged section per title-key with badges; v1-keep vs `v2/`-bump with `.schema.json` + Python validator updated together).
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 15): re-check whether the working tree changed (Phase A–E committed, C1–C5 wording fixed, convert switched, report wired, head past 0029) and whether the gate file moved again (a second off-cycle flip would confirm the pattern flagged in iteration 11). If moved, verify the touched R/M/S step against the cumulative synthesis + iteration-5 matrix; if unchanged, record "no new evidence" and advance the rotating phase (suggested: M4-export shape or report-surface pick, the two least-specified open questions after this pass reconciled ADR/docs). Checkpoint duties next due at iteration 20 (cumulative deltas + gate review + docs-only PR); final synthesis at iteration 100 — neither is due now.
