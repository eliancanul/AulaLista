# Supervisor iteration 0027 — schemas, migration sequence, and rollback safety

Iteration: 27 | Phase focus: schemas, migration sequence, and rollback safety
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–26)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `cc95426` (iteration-20 PR-record append); gate log tip still `606aa64` for `IMPLEMENTATION-GATE.md` (iteration-20 HOLD revert) — no third flip observed. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) stands — no PR duty until iteration 30.

Prior memory: `supervisor-iteration-0026.md` (security envelope re-verification) + `-0025.md` (A1–A9 + P1/P2 pending rows, R1 packaging for 30) + `-0024.md` (C1–C5 three-site sharpening) + `-0023.md` (idempotency/dedup, C1 draft pick) + `-0017.md` (last schemas/migration pass; C3 not re-read there) + `supervisor-cumulative.md` (spine 2→20) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`).

## Scope

Phase-focus: re-verify the iteration-7 migration spine (M0→M4 + per-step rollback, rule #58, #57 gate) and the schema findings (C1/C3, v1 freeze, `$id` consistency) against current code, not against prior handoffs. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 30). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`supervisor-iteration-0026.md` (full) + `-0017.md` (full, phase baseline) + `supervisor-cumulative.md` + `IMPLEMENTATION-GATE.md` (carried, not edited); full re-read `curriculum/staging_validation.py` (238); `curriculum/schemas/README.md` (14, full); `$id` of all three `curriculum/schemas/*.schema.json` (read via JSON parse this pass); `curriculum/models.py:1760-1913` (CurriculumImportJob fields + `clean()`, re-read); `scripts/check_migrations.py` (53, re-run → OK); `curriculum/migrations/` tail (head still 0029) + full text of `0029_curriculumimportjob_progress_finished_at.py` (re-read); `tests/test_t54_staging_contracts.py` head (127 lines, header re-read); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `ls -R curriculum/schemas/` (flat: README + 3 `.schema.json`, no `v2/`); `ls tests/test_*.py | wc -l` → 42; `git log --oneline -3 -- IMPLEMENTATION-GATE.md`, `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–26; migrations head still 0029; `schemas/` still flat; `check_migrations.py` OK; 42 test files; `git diff --stat` identical (+209/−716); status differs from iteration 26 only by the addition of untracked `supervisor-iteration-0026.md` (the expected own-handoff delta, now `supervisor-iteration-0027.md` pending). No Phase A–E commit, no C1–C5 wording fix, no `v2/`, no new model, no hash wiring, no backfill command, no flagged read.
2. **Schemas v1 frozen, `$id` consistent (observed — new check this pass).** `SCHEMA_VERSION = "v1"` (`staging_validation.py:16`); all three on-disk `$id` URIs verified `https://aulalista.local/schemas/v1/<name>.schema.json` — no `v2/` reference, no drift between `SCHEMA_VERSION`, README version rule (`schemas/README.md:7-10`), and file identities. Correct frozen state: no breaking shape change specified or implemented, so no `v2/` should exist. `ACTIVITY_KEYS` (`staging_validation.py:20`) still omits `added_by_topup`; validator `:139` subset-check only — the iteration-14/17 non-contradiction verdict (optional top-up flag consistent across DATABASE/schemas/validator/views) re-verified unchanged.
3. **C3 confirmed open by direct re-read (observed — closes the iteration-17 gap).** Iteration 17 carried C3 without re-reading the site. This pass re-read `models.py:1874-1880`: docstring says "Valida los JSONField contra `curriculum/schemas/v1` (#54)" but on-disk layout is flat (`*.schema.json` in `curriculum/schemas/`, no `v1/` subdirectory; README itself says "`v1/` plano en esta carpeta"). Wording fix remains R1 docs-only (flat-path wording now, `v2/` reserved). No code behavior depends on the path string — doc-precision only.
4. **C1 still open, byte-identical (observed, carry-over 3→27).** Docstring `:189-197` still says "Normaliza (NFKC + casefold + trim) topic, subtema y proposal canónico" but code applies `_norm` (`:25-26`) only to outer `topic`/`subtopic` (`:201-202`); proposal blob is ordered `json.dumps` (`:203-205`) with no recursive `_norm` on inner strings, while the ambiguous key DOES `_norm(proposal.title)` (`:232`). ADR-0010 §Decisión-2 carries the same overstatement (`schemas/README.md:13-14` same sentence). Any M2-backfill ticket hashing historical rows without the scope pick stated will silently pick a semantics. R1 docs-only fix (iteration-23 draft pick, three-site extension at 24, P1/P2 rows at 25) still pending; backfill wording depends on it.
5. **Migration 0029 is additive-nullable, rollback trivial (observed — new precision this pass).** `0029_curriculumimportjob_progress_finished_at.py` is a single `AddField(progress_finished_at, DateTimeField null=True blank=True editable=False)` depending on `0028_grouproadmapprogress`. Backward rollback (`migrate curriculum 0028`) drops an all-nullable observability column with zero data-loss surface; forward risk is nil. This confirms the iteration-7 spine claim "rollback today = revert working tree" from the migration side too: the only recent migrations on this lineage are additive observability/progress fields, and the M0→M4 relational spine (M1 additive tables → M2 re-runnable backfill → M3 flagged new-read → M4 drop-JSON as separate human-confirmed ticket with named export + restore runbook, never bundled; per-step rollback; rule #58; #57 gate green before each step) still has zero implementation footprint — no new models, no dual-write, no backfill command, no flagged read. Safe state holds.
6. **`clean()` gating unchanged (observed).** `models.py:1874-1896` still validates only non-empty payloads and is not called from `save()` (pipeline writes partials; `full_clean()` explicit in human review) — matches ADR-0010's "Paso 1" description. No `Topic/Subtopic/ActivityProposal` model exists (grep: no matches); relational tables remain future-migration, not this branch.
7. **M4-export and report-surface picks still unstated (observed, carry-over 7→27).** No per-job-dump vs snapshot-table-export decision; `_grouped_activities` still emits no dedup badges (iteration-15 cite `views.py:2420-2444` carries; not re-read this pass — phase was schemas/migration, not seams). Both must be answered before any R3/M ticket, after C1. P1 (join-agreement) + P2 (same-title-separation) pending rows from iteration 25 carry as the acceptance precondition for any hash-wiring slice.
8. **Gate: no edit, HOLD carries (decision by rule).** No third flip (log tip `606aa64`); iteration-20 2.5/6 scorecard and HOLD stand. Gate review + cumulative deltas (21–30) + docs-only PR push next due at iteration 30, not now.
9. **Fused-decision spine unchanged (observed + carry).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite (green again this pass), #58 stale, #55/#56/#65 peripheral. #98 stays the sole staging-path `ready-for-agent` candidate at 0/7 (iteration-19 rubric, carried — issue bodies not re-read, tree unchanged so no re-grade possible).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **No gate edit, no cumulative edit, no PR this pass** — non-checkpoint iteration per loop rules.
- **Migration contribution (this pass, no code):** sequence health green (linear, head 0029 additive-nullable, v1 frozen with `$id` consistency verified); rollback posture trivially safe (nothing relational migrated; 0029 backward-rollback lossless). The only migration-sequence risks remain documentary: C1 scope pick + C3 path string must land as R1 before any backfill slice is drafted. Iteration-17's C3 "not re-read" gap is now closed by direct re-read — C3 confirmed open, no longer carried blind.
- **Cite discipline re-affirmed:** current lines only (`staging_validation.py:16` version, `:20` keys, `:25-26` `_norm`, `:55-80` join exact `:76-77`, `:139` id-optionality, `:189-208` hash with C1 caveat, `:211-238` report with title key `:232`; `schemas/` flat with v1 `$id`s, no `v2/`; `models.py:1760-1896` job fields + `clean()` with C3 caveat at `:1875`; migration `0029` additive-nullable; `check_migrations.py` OK; head 0029; 42 test files); prompt's stale pre-shrink numbers remain superseded.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→27.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? Two unamended flips is a pattern. (Carry-over 11→27.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→27.)
4. Agent-ready (C1, draft pick at 23, three-site at 24, P1/P2 rows at 25): confirm `_norm`-join + outer-keys-only hash, or take the exact-join-intentional alternative with inverted P1? Precedes backfill AND staging-adjacent seams. (Carry-over 3→27.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list, `llm_log` audit copy. Enforcement gap until picked; P2 has nowhere to render without it. (Carry-over 5→27.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→27.)
7. Agent-ready (C3, now directly re-verified at 27): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→27.)
8. Draft-quality: should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→27.)
9. Evidence debt: name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (Carry-over 11→27.)
10. Seam-spec: pin S5/S4/S2 to current `views.py` def spans or retire S-numbers and re-derive post-shrink? (Carry-over 18→27.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
12. Security (from 26): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie/SECURE flags, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Land the five R1 doc-precision patches (C1 three-site + draft pick, C2–C5) plus the P1/P2 pending-row names as docs-only PR content at iteration 30; the #98 upgrade depends on C1, the `models.py` docstring on C3 (now directly confirmed, not carried blind), wiring on P1/P2 + report surface. This pass adds no new R1 item — the `$id`-consistency check confirms R1 stays docs-only with no code touch, and 0029's additive-nullable shape confirms no migration repair is owed.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23) + iteration-15 A5a/A5b split + corrected timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface + iteration-25 P1/P2 rows before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist. Institutional hardening (iteration 26 finding 2 + question 12) is an explicit non-goal of the staging lane.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (schemas: `staging_validation.py:16,:20,:25-26,:76-77,:139,:189-208,:232`; `models.py:1760-1896` with C3 at `:1875`; migration `0029` additive-nullable; head 0029; `check_migrations.py` OK; `$id` v1 URIs), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / `models.py` 2038 / `settings.py` 135; `staging_validation.py` 238 with `_norm` `:25-26`, join `:55-80` exact `:76-77`, hash `:189-208` with keys `:201-202` + verbatim proposal `:203-205`, dedup `:211-238` with title key `:232`, zero `views.py` call sites; `models.py:1760-1896` job fields + `clean()` with C3 flat-path caveat at `:1875`; `schemas/` flat with v1 `$id`s, no `v2/`; migration `0029` single additive-nullable `AddField`; `check_migrations.py` OK; head 0029; 42 test files; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; convert `views.py:2446-2475` positional `:2456`; template `item.index :148` vs `item.id :157`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; named surface + P1 (join-agreement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only, M2 re-runnable with C1 scope stated, M3 flagged read, M4 separate ticket with named export artifact + restore runbook); 0029-class additive-nullable steps roll back by reverse-migrate with no data loss.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 28): resume the rotating phase loop (suggested: god-files/service-seams re-check, or idempotency/dedup re-verification). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired into the pipeline, P1/P2 tests added, settings hardened) and whether the gate moved a third time. Checkpoint duties next due at iteration 30 (cumulative deltas 21–30 + gate review + docs-only PR push packaging handoffs 0021–0030); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push, no new PR. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) untouched this pass.
- This handoff (`supervisor-iteration-0027.md`) remains untracked until the iteration-30 checkpoint packages it with 21–30 per the docs-only PR rule.
