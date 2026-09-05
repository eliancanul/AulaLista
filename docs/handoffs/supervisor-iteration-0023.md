# Supervisor iteration 0023 — idempotency, deduplication, ambiguity policy

Iteration: 23 | Phase focus: idempotency, deduplication, and ambiguity policy
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–22)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `cc95426` (iteration-20 PR-record append); no third gate flip observed. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) stands — no PR duty until iteration 30.

Prior memory: `supervisor-iteration-0022.md` (staging-join re-verification, C1 join-vs-hash sharpening) + `-0021.md` (baseline re-verification, counter-methodology note) + `supervisor-cumulative.md` (spine 2→20) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`) + `-0019.md` (ranking + #98 0/7 rubric) + `-0013.md` (idempotency phase origin).

## Scope

Phase-focus: re-verify the idempotency key (`activity_content_hash`), the dedup reporter (`find_duplicate_groups` exact vs ambiguous), and the ambiguity policy (never silent-merge, report + human confirm) against current code. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 30). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`curriculum/staging_validation.py` (full, 238 lines — the idempotency module); `supervisor-iteration-0022.md` (full) + `supervisor-cumulative.md` + `IMPLEMENTATION-GATE.md` (carried, not edited); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` tail (head still 0029); `ls curriculum/schemas/` (flat: README + 3 `.schema.json`, no `v2/`); `rg` for `activity_content_hash|find_duplicate|group_by_subtopic|_norm` in `staging_validation.py` + `views.py`, zero-wiring count, writers (`views.py:2221-2222,2383-2384`), `_activity_id` (`:2301`), remove (`:2317`), convert positional (`:2456`); `rg` for `Topic|Subtopic|ActivityProposal|JSONField` in `models.py`; `ls docs/adr/` (0010 present); `git log --oneline -3`, `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–22; migrations head still 0029; `schemas/` still flat; `git diff --stat` identical (+209/−716); status differs from iteration 22 only by the absence of untracked `supervisor-iteration-0020.md` (committed) — i.e. the expected own-handoff delta, now `supervisor-iteration-0023.md` pending. No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no `v2/`, no new service module, no new model, no hash wiring.
2. **Idempotency key shape re-confirmed (observed, phase focus).** `activity_content_hash` (`staging_validation.py:189-208`): SHA256 over canonical `{"topic","subtopic","proposal"}`; topic/subtopic outer keys `_norm`ed (`:201-202`, NFKC + casefold + trim via `:25-26`); proposal embedded via `json.dumps(sort_keys=True)` round-trip (`:203-205`) with NO `_norm` on inner proposal text; excludes `id`/`selected`/`added_by_topup`/`is_valid`/`issues` (docstring `:193-195`). Stable across retries of identical content, distinct across distinct proposals sharing a title — the design intent holds.
3. **Dedup reporter re-confirmed, still unwired (observed, phase focus).** `find_duplicate_groups` (`:211-238`) returns `{"exact": [...], "same_title_diff_content": [...]}`: `exact` = shared hash (`:224-225`); ambiguous = shared `_norm`ed `(topic, subtopic, proposal.title)` key (`:232`) with >1 distinct hash (`:236`), docstring `:217` "jamás fusionar en silencio". `rg -c` for either function name in `views.py` returns **0** — zero pipeline call sites, unchanged since iteration 2. The three legal wiring touchpoints (post-generate append guard, pre-topup count, pre-convert list, per iteration-0003) remain unimplemented.
4. **Ambiguity policy is specified, not enforced (observed, phase focus).** The policy exists in prose only: exact → safe-to-dedup candidate, ambiguous → report + human confirm, never silent merge (docstrings `:212-217` + iteration-0003 rule). No review-screen section, no `llm_log` entry, no pre-convert list renders either bucket today — report-surface question (open Q5) is therefore the enforcement gap, not a display preference. No code changed; only the framing sharpens: without a named surface, the policy is unenforceable by definition.
5. **C1 decision sketch — both halves, draft pick (spec, not a fix).** (a) Inner-text half (carry-over): `_norm` applies to outer keys (`:201-202`) and title key (`:232`) but NOT to inner proposal body (`:203-205` verbatim JSON). (b) Join-agreement half (iteration-22 new): exact-`==` join (`:76-77`) disagrees with normalized hash inputs (`:201-202`). Draft pick for the R1 precision patch: **normalize the join with `_norm` on both sides AND normalize only outer keys + title in the hash (inner proposal body stays verbatim), documented with two named tests** — (i) case/whitespace-variant titles join together and dedup together; (ii) same-title/different-proposal entries stay separate and surface as `same_title_diff_content`. Rationale: join∷hash agreement removes the split-brain edge (same logical subtopic, different groups, matching hashes); verbatim inner body keeps the hash conservative against false-positive merges (a case-only proposal edit still yields a distinct hash only if inner text differs — safer default for pedagogical content). Alternative spec-valid pick: keep exact join + document case-variants as intentionally separate with a proving test. Either is acceptable; silence is not.
6. **Relational target absent; JSON staging present (observed).** No `Topic|Subtopic|ActivityProposal` model classes in `models.py`; `CurriculumImportJob` holds staging as JSON (`topics`/`activities`/`llm_trace`/`llm_log` JSONFields, `:1815-1859`; docstring `:1875` cites `curriculum/schemas/v1` — C3 wording question carries). No migration past 0029. ADR-0010 remains the spec. Fused-decision spine unchanged: #53/#98/#54 as ONE decision, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. #98 stays the sole staging-path `ready-for-agent` candidate at 0/7 (iteration-19 rubric, carried — issue bodies not re-read, tree unchanged so no re-grade possible).
7. **Gate: no edit, HOLD carries (decision by rule).** Non-checkpoint iteration; gate review + cumulative deltas + docs-only PR push next due at iteration 30, not now. Iteration-20 2.5/6 scorecard and HOLD stand.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **No gate edit, no cumulative edit, no PR this pass** — non-checkpoint iteration per loop rules.
- **Ambiguity-policy enforcement = report-surface pick.** The R1 precision patch must name the surface (recommended: review-screen section + pre-convert list; `llm_log` as audit copy only) before any wiring slice lands — otherwise `exact` vs `same_title_diff_content` has nowhere to appear and the "never silent merge" rule is untestable.
- **C1 draft pick recorded (above) for iteration-30 R1 packaging**; the alternative (exact-join-intentional) stays spec-valid if paired with its proving test.
- **Cite discipline re-affirmed:** current lines only (`staging_validation.py:25-26` `_norm`, `:55-80` join, `:76-77` exact equality, `:189-208` hash, `:201-202` normalized keys, `:203-205` verbatim proposal, `:211-238` dedup, `:232` title key; `views.py:2221-2222/:2383-2384` writers, `:2346/:2426` callers, `:2301` `_activity_id`, `:2317` remove, `:2456` positional convert); prompt's stale pre-shrink numbers remain superseded.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→23.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? Two unamended flips is a pattern. (Carry-over 11→23.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→23.)
4. Agent-ready (C1, draft pick recorded): confirm `_norm`-join + outer-keys-only hash normalization, or take the exact-join-intentional alternative? Precedes backfill AND staging-adjacent seams. (Carry-over 3→23, draft pick new.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list, `llm_log` audit copy. Enforcement gap until picked. (Carry-over 5→23, sharpened to enforcement framing.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→23.)
7. Agent-ready (C3): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→23.)
8. Draft-quality: should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→23.)
9. Evidence debt: name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (Carry-over 11→23.)
10. Seam-spec: pin S5/S4/S2 to current `views.py` def spans or retire S-numbers and re-derive post-shrink? (Carry-over 18→23.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Land the five R1 doc-precision patches (C1–C5 from iteration 14, with C1 now carrying the §Findings-5 draft pick and the report-surface enforcement pick) as docs-only PR content at iteration 30; the #98 upgrade depends on C1, the `models.py` docstring on C3.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves) + iteration-15 A5a/A5b split + corrected timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + this pass's ambiguity-enforcement surface before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (join `:76-77`, writers `:2221-2222/:2383-2384`, hash `:189-208`, zero-wiring count, title key `:232`), the N+1-fixed note (`models.py:1130` `in_bulk`), and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / `models.py` 2038; `staging_validation.py` 238 with `_norm` `:25-26`, join `:55-80` exact `:76-77`, hash `:189-208` with keys `:201-202` + verbatim proposal `:203-205`, dedup `:211-238` with title key `:232`, zero `views.py` call sites; writers `views.py:2221-2222/:2383-2384`; callers `:2346/:2426`; `_activity_id` `:2301`, remove `:2317`, convert positional `:2456`; `models.py:36` reviewer group, `:48-55` sha256, `:289-308` publish gate, `:384` immutable hash, `:762` session, `:1130` `in_bulk`; `services/results.py` 552, `roadmap_cursor.py` 27; `schemas/` flat, no `v2/`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; named surface + two proving tests (join-agreement + same-title-separation) required before wiring.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 24): resume the rotating phase loop (suggested: tests/evidence matrix A1–A9 with the two new proving tests sketched as pending rows, or ADR/documentation contradiction reconciliation C1–C5 packaging for iteration 30). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired into the pipeline) and whether the gate moved a third time. Checkpoint duties next due at iteration 30 (cumulative deltas + gate review + docs-only PR push); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push, no new PR. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) untouched this pass.
- This handoff (`supervisor-iteration-0023.md`) remains untracked until the iteration-30 checkpoint packages it with 21–30 per the docs-only PR rule.
