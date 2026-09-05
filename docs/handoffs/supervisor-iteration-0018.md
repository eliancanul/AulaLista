# Supervisor iteration 0018 — god-files, service seams, and maintainability specs

Iteration: 18 | Phase focus: god-files, service seams, and maintainability specs
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–17)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). Gate log tip still `b22b55b` (second slice); no third flip. HEAD unchanged since iteration 15. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) already exists — no PR duty until iteration 20. `git diff --stat` working-tree shape unchanged: `views.py` −808-line-dominant (7 files, +209/−716).

Prior memory: `supervisor-iteration-0017.md` (migration spine M0→M4, C1/C3 carry) + `-0016.md` (security envelope, Ollama 180s close-out) + `-0015.md` (A1–A9 re-verification, A5a/A5b split) + `-0014.md` (C1–C5 reconciliation) + `supervisor-cumulative.md` (spine 2→10).

## Scope

Phase-focus: re-verify the iteration-8 god-file/service-seam map (S1–S5, Steps 0–4, S1-LAST-fused-with-M3, S3 exemplar) against current code, not against prior handoffs. Spec only — nothing implemented. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 20). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`CONTEXT.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `docs/handoffs/IMPLEMENTATION-GATE.md` (log tip check only); `rg` def/class inventory of `curriculum/views.py` (2950) / `curriculum/models.py` (2038) / `curriculum/services/results.py` (552) / `curriculum/services/roadmap_cursor.py` (27); `ls curriculum/services/`; service-import grep in `views.py`/`models.py`; seam-target grep (`_grouped_activities`, `_import_action_convert`, `find_duplicate_groups`, `activity_content_hash`); `curriculum/migrations/` tail (head still 0029); `ls -R curriculum/schemas/` (flat, no `v2/`); `git diff --stat`, `git log --oneline -5 -- IMPLEMENTATION-GATE.md`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** All line counts byte-identical to iterations 2–17; status differs from iteration 17 only by the new untracked `supervisor-iteration-0017.md` (last pass's own handoff). Migrations head still 0029; `schemas/` still flat; gate file untouched since `b22b55b` — the two-flip pattern stands, still no third flip. C1–C5 wording unfixed.
2. **God-file shape re-verified with fresh counts (observed).** `views.py`: 2950 lines, 91 top-level `def`/`class` (tutor/student/import/session/result/survey spans `:106-2849`); `models.py`: 2038 lines, 26 top-level `def`/`class` plus ~40 methods (incl. `ClassroomSession:762`, `CurriculumImportJob:1760` with `clean():1874`). The file is a view-layer aggregate (auth cookies, session lifecycle, import pipeline actions, results/export, roadmap/student handlers), not a single concern — the iteration-8 "god-file" label still fits by def-count, not just line-count.
3. **Service-seam map holds, narrowly (observed).** `curriculum/services/` contains exactly `results.py` (552, 12 defs/classes) + `roadmap_cursor.py` (27, 1 def/class) + `__init__.py`. `views.py` imports services at exactly two sites (`:74-75`: `roadmap_cursor`, `results`). Both services are result/roadmap-path only — zero import-pipeline (staging) extraction exists. The seam direction from iteration 8 is confirmed: results/roadmap logic already demonstrates the delegate shape; staging logic has not followed.
4. **S1-LAST-fused-with-M3 re-verified (observed).** `_grouped_activities` (`views.py:2420`) and `_import_action_convert` (`views.py:2446`, call site `:2006`) still live in `views.py`; `_grouped_activities` reuse at `:2022` confirmed. `find_duplicate_groups`/`activity_content_hash` have zero call sites in `views.py`/`services/` (grep hits only the seam names themselves in views) — hash/dedup still unwired. Extracting the staging read (`_grouped_activities` + convert/remove/topup, i.e. S1) before M3's flagged new-read would be double churn: the read target changes shape under M1→M3. S1 stays LAST and fused with M3.
5. **Extraction order S5→S4→S2 carries, with one precision sharpening (observed + hypothesis labeled).** The two existing services cover the S3-exemplar neighborhood (results/roadmap delegate shape). Remaining `views.py` clusters by def-name spans are, in order: session-lifecycle helpers (`:965-1197`), import-pipeline actions (`:1558-2475`, the M-fused zone — do not touch before M3), student-activity/answer/assist handlers (`:2477-2849`). Hypothesis (not a ticket): S5/S4/S2 candidates live in the session-lifecycle and student-activity clusters, which have no migration dependency — but this pass did not pin per-function S-numbers to current lines, so iteration 8's S-labels are carried, not re-derived.
6. **Maintainability spec contribution (this pass, no code):** the next R4 (S5→S4→S2) ticket draft must (a) cite current def spans, not stale numbers; (b) keep `models.py` extraction behavior-only (fields migration-pinned per iteration 8); (c) forbid touching `_grouped_activities`/`_import_action_convert`/remove/topup until the M3 flagged-read slice; (d) require the A1–A9 matrix green plus `check_migrations.py` clean. No such ticket is created this pass.
7. **Fused-decision spine unchanged (observed).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. Gate traceability gap from iteration 15 (on-disk gate cites `coding-41560047f83c.md`, unreachable from this branch) persists — not re-verified by `ls` this pass, carried as standing finding.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, Steps 0–4 per iteration 8, queue R1–R5 per iteration 9, HOLD + cumulative per iteration 10, 2.5/6 scorecard per iterations 11–17, C1–C5 per iteration 14, envelope per iteration 16).
- **Gate: no edit this pass (10th-iteration duty).** Assessment only — no third flip observed; iteration-15 2.5/6 scorecard carries. Iteration 20 must adopt a human-signed amendment allowing stacked-slice updates (with vendored evidence or exact cross-branch refs) or revert to `HOLD`.
- **Seam contribution (this pass, no code):** S1-LAST-fused-with-M3 re-confirmed with current cites; services/ stays a two-module exemplar (results + roadmap_cursor); R4 stays queued behind R1→R2→R3(M4 excluded). No seam extraction is spec-complete until C1 (`_norm` scope) is answered, because any staging-adjacent seam touches hashed content.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→18.) Blocks any future supervisor `READY`.
2. Gate provenance: `498a4df` AND `b22b55b` both flipped the gate off-cycle. Deliberate stacked-slice strategy or accident? Loop rule needs a human-signed amendment at iteration 20. (Carry-over 11→18, confirmed pattern.)
3. Traceability (carry-over 15→18): vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate?
4. Agent-ready (carry-over 3→18, citable as C1): recursive `_norm` on inner proposal text vs outer-keys-only (`staging_validation.py:25-26` vs `:203-205` vs `:232` vs ADR-0010 §Decisión-2)? Must precede any backfill slice AND any staging-adjacent seam work.
5. Agent-ready (carry-over 5→18): duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Assumed review-screen + pre-convert list.
6. Agent-ready (carry-over 7→18): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)?
7. Agent-ready (carry-over 14→18, citable as C3): `models.py:1875` docstring path — flat `*.schema.json` wording?
8. Seam-spec (new, for iteration 20+): pin S5/S4/S2 labels to current `views.py` def spans (`:965-1197` session-lifecycle, `:2477-2849` student-activity) or retire the S-numbers and re-derive seams from the post-shrink tree?
9. Evidence debt (carry-over 11→18): name the duplicated-cursor pair with current lines or drop the claim from the loop prompt.
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. At iteration 20, resolve the gate cleanly: adopt the two stacked slices verbatim WITH vendored evidence (or exact cross-branch refs + PR 113 URL) + a clean `updated-tech` base ref + answered picks, or revert to `HOLD` with the 2.5/6 scorecard. Do not let a third off-cycle flip accumulate.
2. Land the five R1 doc-precision patches (C1–C5 from iteration 14) as docs-only PR content; backfill wording AND any staging-adjacent seam spec depend on C1, `models.py` docstring on C3.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 `_norm`-scope pick + iteration-15 A5a/A5b split + iteration-16 timeout cite (`CHAT_TIMEOUT_SECONDS = 180`) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the triple-join cite table + idempotency cite table + A5a/A5b split + C1–C5 table + migration-sequence cites (`schemas/README.md:3-10` version rule; `staging_validation.py:16` SCHEMA_VERSION; head 0029; `check_migrations.py` OK) + this pass's seam cites (`views.py` 91 defs, `:74-75` service imports, `:2420` grouped, `:2446` convert; `services/results.py` 552, `roadmap_cursor.py` 27).

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 91 defs / 2950 lines, `:74-75` service imports, `:2420` `_grouped_activities`, `:2446` `_import_action_convert` positional `:2456`, `:2006` convert call site, `:2022` grouped reuse; `services/results.py` 552, `roadmap_cursor.py` 27; `models.py:1874-1896` `clean()` with C3 caveat; `staging_validation.py:16` version, `:25-26` `_norm`, `:203-205` hash with C1 caveat; migrations head 0029; iteration-15 template cites carry: `tutor_import_detail.html:148` `item.index` vs `:157` `item.id`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iteration 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress) + iterations 5/7/8 (A1–A9 with A5a/A5b, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Seam discipline: S5→S4→S2 before S1; S1 LAST fused with M3; `models.py` behavior-only extraction; A1–A9 green; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 19): re-check whether the working tree changed (Phase A–E committed, C1–C5 wording fixed, A5b template switched, head past 0029, `v2/` appeared, new service module appeared) and whether the gate file moved a third time (a third off-cycle flip forces the rule-amendment question at iteration 20). If moved, verify the touched R/M/S step against the cumulative synthesis + iteration-5 matrix + this seam map; if unchanged, record "no new evidence" and advance the rotating phase (suggested: draft the R4 seam-ticket skeleton with pinned def spans, or resolve the report-surface pick). Checkpoint duties next due at iteration 20 (cumulative deltas + gate review + docs-only PR); final synthesis at iteration 100 — neither is due now.
