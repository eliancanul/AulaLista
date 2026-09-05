# Supervisor iteration 0024 — ADR and documentation contradiction reconciliation

Iteration: 24 | Phase focus: ADR and documentation contradiction reconciliation
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–23)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `cc95426` (iteration-20 PR-record append); gate log tip still `606aa64` for `IMPLEMENTATION-GATE.md` (iteration-20 HOLD revert) — no third flip observed. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) stands — no PR duty until iteration 30.

Prior memory: `supervisor-iteration-0023.md` (idempotency/dedup/ambiguity, C1 draft pick + report-surface enforcement framing) + `-0022.md` (staging-join re-verification, join-vs-hash sharpening) + `-0021.md` (baseline, counter-methodology note) + `-0014.md` (C1–C5 phase origin) + `supervisor-cumulative.md` (spine 2→20) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`).

## Scope

Phase-focus: re-verify the five ADR/documentation contradictions (C1–C5 from iteration 14) against current code, not against prior handoffs, and sharpen the R1 packaging so iteration 30 can land them without re-derivation. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 30). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`docs/adr/0010-staging-relacional-idempotente.md` (full, 58 lines); `docs/adr/0006-teacher-workflow-and-human-curriculum-progress.md` (full, 35 lines); `curriculum/staging_validation.py:20-26,55-80,189-238` (read in full this pass); `curriculum/models.py:1874-1896` (`clean()` docstring); `docs/DATABASE.md:101-110` (Deuda block); `docs/implementation-current.md:1-17` (header + LLM sentence); `docs/teacher-flow.md:110-120` (roadmap-state mapping); `curriculum/schemas/README.md` (full, 14 lines); `supervisor-iteration-0014.md` (full, C-origin) + `-0022.md` + `-0023.md` (§-scoped) + `supervisor-cumulative.md` + `IMPLEMENTATION-GATE.md` (carried, not edited); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `ls -R curriculum/schemas/` (flat); `curriculum/migrations/` tail (head still 0029); `git log --oneline -3 -- IMPLEMENTATION-GATE.md`, `git log --oneline -3`, `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–23; migrations head still 0029; `schemas/` still flat (README + 3 `.schema.json`, no `v2/`); `git diff --stat` identical (+209/−716); status differs from iteration 23 only by the absence of untracked `supervisor-iteration-0020.md`-style delta now being `supervisor-iteration-0024.md` pending (iterations 21–23 handoffs still untracked). No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no `v2/`, no new service module, no new model, no hash wiring.
2. **C1 — hash-normalization overstatement confirmed in THREE sites, not two (observed, precision sharpening).** Iteration 14 named two sites (ADR-0010 §Decisión-2 + module docstring `:192`); this pass confirms a third with identical wording: `curriculum/schemas/README.md` idempotency bullet ("SHA256 canónico de `(topic, subtema, proposal)` normalizados; nunca el título visible solo"). Code is unchanged: `_norm` (`:25-26`, NFKC + casefold + trim) applies ONLY to topic/subtopic (`:201-202`); proposal blob is ordered `json.dumps` (`:203-205`) with NO recursive `_norm`; ambiguous key DOES `_norm(proposal.title)` (`:232`). The iteration-23 draft pick (normalize join with `_norm` on both sides + outer-keys-only hash, two proving tests) is carried unmodified — this pass only extends the patch target list from two files to three. Still a REAL contradiction, still R1 docs-only.
3. **C2 — `DATABASE.md` Deuda-1 still predates ADR-0010 (observed).** `docs/DATABASE.md:103-105` still reads "Decisión consciente para el prototipo; revisar antes de escalar (nuevo ADR)" with no ADR-0010 cite; entities table still lists no future Topic/Subtopic/ActivityProposal rows. The uncommitted `DATABASE.md` diff (+7 lines) still adds only test/migration conventions, not the ADR-0010 pointer. Still REAL, still R1 docs-only.
4. **C3 — `models.py:1875` path still wrong (observed).** `clean()` docstring still cites ``curriculum/schemas/v1``; disk is still flat (`*.schema.json`, no `v1/`). Adjacent non-contradiction re-confirmed: `clean()` validates only non-empty payloads + `save()` does not call `clean()` (`:1874-1879`) still matches ADR-0010 §Contexto exactly. Still REAL, still R1 (docstring-only edit).
5. **C4 — `implementation-current.md` header still a main-snapshot (observed).** Header still Rama `main`, Fecha 22-ago-2026, commit `d4fcb99` (`:3-6`); reality is branch `supervisor/aulalista-docs`, HEAD `cc95426`, uncommitted Phase A–E tree. The working-tree diff's LLM-sentence correction ("sí usa LLM local (Ollama `qwen2.5:14b`) solo para staging", `:13-15`) is present and accurate against `curriculum/prompts/` + settings keys — so the file is now half-fixed (body) and half-stale (header). R1 patch is therefore the scope banner or header bump only, never line-number cites from this file. Still SCOPE contradiction.
6. **C5 — ADR-0006 omission confirmed byte-identical (observed, MINOR).** ADR-0006 `:29` still lists only `ACTUAL`, `DISPONIBLE`, `COMPLETADA` "como texto"; `teacher-flow.md:110-120` still maps all four (`ACTUAL`/`DISPONIBLE`/`COMPLETADA`/`BLOQUEADA`) plus `visto` manual-only with the DESIGN.md mayúsculas-runtime vs minúsculas-visual correspondence. The ADR bullet is incomplete, not wrong. Still R1 (one-bullet append with the teacher-flow cite).
7. **Gate: no edit, HOLD carries (decision by rule).** No third flip (gate log tip `606aa64`); iteration-20 2.5/6 scorecard and HOLD stand. Gate review + cumulative deltas + docs-only PR push next due at iteration 30, not now.
8. **Fused-decision spine unchanged (observed + carry).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. #98 stays the sole staging-path `ready-for-agent` candidate at 0/7 (iteration-19 rubric, carried — issue bodies not re-read, tree unchanged so no re-grade possible).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **No gate edit, no cumulative edit, no PR this pass** — non-checkpoint iteration per loop rules.
- **R1 packaging sharpened for iteration 30 (this pass's contribution):** five docs-only patches with exact targets — (a) C1: narrow the normalization sentence in THREE files (`docs/adr/0010-…md` §Decisión-2, `staging_validation.py:192` docstring, `curriculum/schemas/README.md` idempotency bullet) to outer-keys-only + state the iteration-23 draft pick with its two proving tests; (b) C2: `docs/DATABASE.md:103-105` cites ADR-0010 + entities-table future note; (c) C3: `models.py:1875` docstring to flat `*.schema.json`; (d) C4: `docs/implementation-current.md:3-6` header bump or scope banner; (e) C5: ADR-0006 `:29` appends `BLOQUEADA`/`visto` with the `teacher-flow.md:110-120` cite. All five must land BEFORE any R3/M-backfill ticket, since backfill wording depends on (a).
- **Cite discipline re-affirmed:** current lines only (ADR-0010 §Decisión-2/§Consecuencias/§Contexto; `staging_validation.py:25-26` `_norm`, `:55-80` join, `:76-77` exact equality, `:189-208` hash, `:201-202` normalized keys, `:203-205` verbatim proposal, `:211-238` dedup, `:232` title key; `views.py:2221-2222/:2383-2384` writers, `:2346/:2426` callers, `:2301` `_activity_id`, `:2317` remove, `:2456` positional convert; `models.py:1874-1896` `clean()` + `:1875` path caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; `schemas/README.md` C1 third site); prompt's stale pre-shrink numbers remain superseded.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→24.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? Two unamended flips is a pattern. (Carry-over 11→24.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→24.)
4. Agent-ready (C1, draft pick recorded at 23, patch targets extended to three sites this pass): confirm `_norm`-join + outer-keys-only hash normalization, or take the exact-join-intentional alternative? Precedes backfill AND staging-adjacent seams. (Carry-over 3→24.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list, `llm_log` audit copy. Enforcement gap until picked. (Carry-over 5→24.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→24.)
7. Agent-ready (C3): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→24.)
8. Draft-quality: should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→24.)
9. Evidence debt: name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (Carry-over 11→24.)
10. Seam-spec: pin S5/S4/S2 to current `views.py` def spans or retire S-numbers and re-derive post-shrink? (Carry-over 18→24.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Land the five R1 doc-precision patches (§Decisions, C1 now three-site) as docs-only PR content at iteration 30; the #98 upgrade depends on C1, the `models.py` docstring on C3, backfill wording on C1's scope pick.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23) + iteration-15 A5a/A5b split + corrected timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (join `:76-77`, writers `:2221-2222/:2383-2384`, hash `:189-208`, zero-wiring count, title key `:232`, C1 three-site list, C3 `:1875`, C4 header, ADR-0006 `:29`), the N+1-fixed note (`models.py:1130` `in_bulk`), and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / `models.py` 2038; `staging_validation.py` 238 with `_norm` `:25-26`, join `:55-80` exact `:76-77`, hash `:189-208` with keys `:201-202` + verbatim proposal `:203-205`, dedup `:211-238` with title key `:232`, zero `views.py` call sites; writers `views.py:2221-2222/:2383-2384`; callers `:2346/:2426`; `_activity_id` `:2301`, remove `:2317`, convert positional `:2456`; `models.py:36` reviewer group, `:48-55` sha256, `:289-308` publish gate, `:384` immutable hash, `:762` session, `:1130` `in_bulk`, `:1875` C3 path caveat; `services/results.py` 552, `roadmap_cursor.py` 27; `schemas/` flat (README + 3 `.schema.json`, no `v2/`); migrations head 0029; ADR-0010 with C1 caveat (three sites); `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; named surface + two proving tests (join-agreement + same-title-separation) required before wiring.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 25): resume the rotating phase loop (suggested: tests/evidence matrix A1–A9 with the two proving tests from the iteration-23 draft pick sketched as pending rows, or schemas/migration M0→M4 rollback re-verification). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired into the pipeline) and whether the gate moved a third time. Checkpoint duties next due at iteration 30 (cumulative deltas 21–30 + gate review + docs-only PR push packaging handoffs 0021–0030); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push, no new PR. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) untouched this pass.
- This handoff (`supervisor-iteration-0024.md`) remains untracked until the iteration-30 checkpoint packages it with 21–30 per the docs-only PR rule.
