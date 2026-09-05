# Supervisor iteration 0022 — curriculum staging join and relational model

Iteration: 22 | Phase focus: curriculum staging join and relational model
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–21)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `cc95426` (iteration-20 PR-record append); no third gate flip observed. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) stands — no PR duty until iteration 30.

Prior memory: `supervisor-iteration-0021.md` (baseline re-verification, counter-methodology note) + `-0020.md` (checkpoint, gate back to HOLD 2.5/6, PR 112 push) + `supervisor-cumulative.md` (spine 2→20) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`) + `-0019.md` (ranking + #98 0/7 rubric) + `-0012.md` (staging-join phase origin).

## Scope

Phase-focus: re-verify the curriculum staging join (title-keyed writes, grouping reads, exact-vs-normalized equality) and the relational model target (Topic/Subtopic/ActivityProposal absent, JSON staging present, ADR-0010 as spec) against current code, not against prior handoffs. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 30). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`CONTEXT.md` (carried — no re-read; baseline verified at 21), `DESIGN.md` (carried); `supervisor-iteration-0021.md` (full) + `supervisor-cumulative.md` + `IMPLEMENTATION-GATE.md` (carried, not edited); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` tail (head still 0029); `ls -R curriculum/schemas/` (flat); `views.py:2006,2022,2221-2222,2301-2304,2313-2317,2343-2346,2383-2384,2420-2443,2446-2456` (read in full this pass); `staging_validation.py:25-26,55-80,189-238` (read in full); `models.py:1760-1809` (`CurriculumImportJob` header); `grep` for `Topic|Subtopic|ActivityProposal|JSONField` in `models.py`, `group_by_subtopic|activity_content_hash|find_duplicate` across `curriculum/`, `hash|duplicate` in `views.py`; `ls docs/adr/` (0010 present); `git log --oneline -3`, `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–21; migrations head still 0029; `schemas/` still flat (README + 3 `.schema.json`, no `v2/`); `git diff --stat` identical (+209/−716); status differs from iteration 21 only by the absence of untracked `supervisor-iteration-0020.md` (committed in `606aa64`) — i.e. the expected own-handoff delta, now `supervisor-iteration-0022.md` pending. No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no `v2/`, no new service module, no new model.
2. **Staging join is centralized and exactly-equal (observed, phase focus).** `group_by_subtopic(topics, activities)` at `staging_validation.py:55-80` is the single join: matches on `entry.get("topic_title") == topic.get("titulo")` AND `entry.get("subtopic_title") == sub.get("titulo")` (`:76-77`, exact `==`, no normalization). Its own docstring (`:56-62`) declares this is "la clave actual: título exacto" and names idempotency (#98) + relational tables (#53) as the future replacement per ADR-0010, "no este helper". Two callers: top-up guard `views.py:2346` and grouped view `views.py:2426`. Writers stamp the keys at `views.py:2221-2222` (generate path) and `:2383-2384` (top-up path), both `"topic_title": topic["titulo"]` / `"subtopic_title": sub["titulo"]`. Iteration-12's triple-join cite table holds; prompt's `:2875-2876,2959-2960` remain stale pre-shrink numbers.
3. **C1 asymmetry sharpened with a new precise cite (observed, phase focus).** `_norm` (`staging_validation.py:25-26`, NFKC + casefold + trim) IS used inside `activity_content_hash` (`:201-202` normalizes topic/subtopic) and inside the dedup title key (`:232` normalizes topic/subtopic/title) — but is NOT used in the join (`:76-77` exact `==`). So the standing C1 question ("recursive `_norm` on inner proposal text vs outer-keys-only") now has a sharper companion: **should the join itself normalize (join agrees with hash) or stay exact (join disagrees with hash by design)?** Exact join + normalized hash means two entries differing only by case/whitespace land in different subtopic groups yet share nearby hashes only if proposals also match — a real, citable edge the R1 precision patch must pick. No code changed; only the spec question got more precise.
4. **Hash/dedup specified but unwired (observed, phase focus).** `activity_content_hash` (`:189-208`, content-keyed SHA256 excluding `id`/`selected`/`added_by_topup`/`is_valid`/`issues`) + `find_duplicate_groups` (`:211-238`, `exact` vs `same_title_diff_content`, "jamás fusionar en silencio") are fully defined, but `grep -c` for either name in `views.py` returns **0** — zero pipeline call sites. The three legal wiring touchpoints (post-generate append guard, pre-topup count, pre-convert list, per iteration-0003) remain unimplemented. This is unchanged since iteration 2, re-confirmed by direct count this pass.
5. **Relational target absent; JSON staging present (observed, phase focus).** `grep` for `Topic|Subtopic|ActivityProposal` as model classes in `models.py` returns nothing; `CurriculumImportJob` (`models.py:1760+`) still holds staging as JSON (`topics`, `activities`, `llm_log` JSONFields — header docstring `:1761-1767` confirms "Nothing here creates or modifies CurriculumPackage"). No migration past 0029. ADR-0010 (`docs/adr/0010-staging-relacional-idempotente.md`, present in `ls`) remains the spec, not the code. Fused-decision spine unchanged: #53/#98/#54 as ONE decision, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. #98 stays the sole staging-path `ready-for-agent` candidate at 0/7 (iteration-19 rubric, carried — issue bodies not re-read, tree unchanged so no re-grade possible).
6. **Stable-id vs positional split re-confirmed (observed).** `_activity_id(entry, fallback_index)` at `views.py:2301-2304` (`entry.get("id") or f"idx-{fallback_index}"`); used by grouped view `:2428` and remove path `:2317`; convert still positional `entry = job.activities[int(index)]` at `:2456`. The A5a (convert-identity tested slice) vs A5b (template `item.index→item.id`) split from iteration 15 holds byte-identical.
7. **Gate: no edit, HOLD carries (decision by rule).** Non-checkpoint iteration; gate review + cumulative deltas + docs-only PR push next due at iteration 30, not now. Iteration-20 2.5/6 scorecard and HOLD stand.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **No gate edit, no cumulative edit, no PR this pass** — non-checkpoint iteration per loop rules.
- **C1 precision sharpened (not resolved):** the R1 precision patch must now answer TWO normalization questions, not one: (a) `_norm` recursion scope inside the hash (inner proposal text vs outer keys — carry-over), AND (b) join-vs-hash agreement (exact `==` join at `:76-77` vs normalized hash inputs at `:201-202` — new this pass). Recommended pick to draft: normalize the join with `_norm` on both sides (join agrees with hash), OR document exact-join as intentional with a named test proving case-variant titles stay separate. Either is spec-valid; silence is not.
- **Cite discipline re-affirmed:** current lines only (`group_by_subtopic` `:55-80`, join `:76-77`, writers `:2221-2222/:2383-2384`, callers `:2346/:2426`, `_activity_id` `:2301-2304`, remove `:2317`, convert `:2456`, `_norm` `:25-26`, hash `:189-208`, dedup `:211-238`); prompt's stale pre-shrink numbers remain superseded.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→22.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? Two unamended flips is a pattern. (Carry-over 11→22.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→22.)
4. Agent-ready (C1-extended): (a) recursive `_norm` on inner proposal text vs outer-keys-only (`:25-26` vs `:203-205` vs ADR-0010 §Decisión-2)? (b — new 22) exact join (`:76-77`) vs `_norm` join agreeing with hash (`:201-202`)? Both precede backfill AND staging-adjacent seams. (Carry-over 3→22, sharpened.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Assumed review-screen + pre-convert list. (Carry-over 5→22.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→22.)
7. Agent-ready (C3): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→22.)
8. Draft-quality: should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→22.)
9. Evidence debt: name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (Carry-over 11→22.)
10. Seam-spec: pin S5/S4/S2 to current `views.py` def spans or retire S-numbers and re-derive post-shrink? (Carry-over 18→22.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Land the five R1 doc-precision patches (C1–C5 from iteration 14, with C1 now extended per §Decisions) as docs-only PR content; the #98 upgrade depends on C1, the `models.py` docstring on C3.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves) + iteration-15 A5a/A5b split + corrected timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (join `:76-77`, writers `:2221-2222/:2383-2384`, hash `:189-208`, zero-wiring count), the N+1-fixed note (`models.py:1130` `in_bulk`), and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / `models.py` 2038; join `staging_validation.py:55-80` exact `:76-77`; writers `views.py:2221-2222/:2383-2384`; callers `:2346/:2426`; `_activity_id` `:2301-2304`, remove `:2317`, convert positional `:2456`; `_norm` `:25-26`, hash `:189-208`, dedup `:211-238`, zero `views.py` call sites; `models.py:36` reviewer group, `:48-55` sha256, `:289-308` pubish gate, `:384` immutable hash, `:762` session, `:1130` `in_bulk`; `services/results.py` 552, `roadmap_cursor.py` 27; `schemas/` flat, no `v2/`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 23): resume the rotating phase loop (suggested: idempotency/dedup/ambiguity with a C1 `_norm`-scope decision sketch covering both halves, or tests/evidence matrix A1–A9). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired into the pipeline) and whether the gate moved a third time. Checkpoint duties next due at iteration 30 (cumulative deltas + gate review + docs-only PR push); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push, no new PR. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) untouched this pass.
- This handoff (`supervisor-iteration-0022.md`) remains untracked until the iteration-30 checkpoint packages it with 21–30 per the docs-only PR rule.
