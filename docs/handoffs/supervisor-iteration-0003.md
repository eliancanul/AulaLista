# Supervisor iteration 0003 — idempotency, deduplication, ambiguity policy

Iteration: 3 | Phase focus: idempotency, deduplication, and ambiguity policy
Branch: `updated-tech` (uncommitted working tree; no commit/merge performed)

`git status --short --branch` at pass time:

```text
## updated-tech...origin/main
 M aulalista/settings.py
 M curriculum/models.py
 M curriculum/views.py
 M docs/DATABASE.md
RM docs/adr/0007-pseudonymous-results-and-classroom-retention.md -> docs/adr/0009-pseudonymous-results-and-classroom-retention.md
 M docs/implementation-current.md
 M docs/teacher-flow.md
R  health/templates/health/local_access.html -> templates/health/local_access.html
?? .DS_Store
?? curriculum/schemas/
?? curriculum/services/
?? curriculum/staging_validation.py
?? docs/.DS_Store
?? docs/adr/0010-staging-relacional-idempotente.md
?? docs/handoffs/
?? scripts/check_migrations.py
?? tests/test_t54_staging_contracts.py
```

Prior memory: `supervisor-iteration-0002.md` (staging join + relational model) plus dated handoffs `2026-09-05-01..04`, `2026-09-05-cierre-loop`, `2026-09-05-loop-implementacion`, `2026-09-05-supervisor-bootstrap`. No `supervisor-cumulative.md` exists — not due (10th iteration). Working-tree shape is **byte-identical in `git status` to iteration 2**: no commits, no new relations, no reverts observed. This pass therefore records "no new tree evidence" and sharpens the idempotency/dedup/ambiguity spec instead of repeating conclusions.

## Scope

Phase-focus deep dive on #98 within the fused #53/#98/#54 decision (ADR-0010): is `activity_content_hash` the right key, does `find_duplicate_groups` enforce the right policy, and where does the pipeline still silently duplicate? Spec only — nothing implemented, per loop rules.

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `docs/handoffs/supervisor-iteration-0002.md`, `docs/handoffs/2026-09-05-cierre-loop.md`, plus read-only inspection of `curriculum/staging_validation.py` (238 lines, full), `curriculum/views.py:2200-2257,2369-2474` (producers, topup, grouped, convert), `curriculum/views.py:2301-2325` (remove path), `curriculum/models.py:1874-1896` (`clean()`), `curriculum/schemas/README.md`, `curriculum/services/roadmap_cursor.py` (27), `tests/test_t54_staging_contracts.py` (127), `scripts/check_migrations.py` (53). Grep for `activity_content_hash|find_duplicate_groups|full_clean|content_hash` across `curriculum/`. Ran `python3 scripts/check_migrations.py` (OK); `pytest` unavailable in this environment (no `pytest` module, no `.venv`), so `test_t54` was read as spec, not executed.

## Findings (observed facts vs hypotheses)

1. **Hash design is sound and tested (observed).** Fact: `staging_validation.py:189-208` — SHA256 over canonical `(topic, subtema, proposal)` with `_norm` (NFKC + casefold + trim, `:25-26`), excluding `id/selected/added_by_topup/is_valid/issues`. `test_t54_staging_contracts.py:108-116` pins state-independence (retry with different `selected/issues` → same hash) and source-sensitivity (different `micro_lesson` → different hash). This matches ADR-0010 §2 and the inviolable contracts (no editorial state in the key).
2. **Reporter exists but has zero pipeline call sites (observed, the #1 gap this phase).** Fact: grep finds `activity_content_hash` / `find_duplicate_groups` only in `staging_validation.py` and `test_t54_staging_contracts.py`. No caller in `views.py` or `models.py`. Consequence: producers at `views.py:2218-2228` (stage C) and `views.py:2380-2391` (topup D+) append unconditionally with fresh `uuid4().hex[:8]`; an interrupted-then-retried stage re-appends identical content as new rows; topup counts `len(existing)` via the title-exact `group_by_subtopic`, so duplicates inflate the count it tries to fill; `_import_action_convert` (`views.py:2452-2456`) converts positional `select` indices, so an exact duplicate converts twice into two `CurriculumPackage` rows. Hypothesis (for agent spec): the report-then-dedup must interpose at exactly three points — post-generate append, pre-topup count, pre-convert list — and nowhere else.
3. **Ambiguity policy is declared but has no surface (observed).** Fact: `find_duplicate_groups` (`staging_validation.py:211-238`) returns `{"exact": ..., "same_title_diff_content": ...}` and docstring says "reporte para humana, jamás fusionar en silencio" — correct per #98. But no view, template, or `llm_log`/`error_message` writer consumes it; no `docs/DATABASE.md` section documents what the teacher sees. The `same_title_diff_content` key is `(norm topic, norm sub, norm proposal.title)` (`:232`) — narrow by design (same visible title, different body). Overlapping categories are real: the test asserts `exact == [[0,1]]` *and* `same_title_diff_content == [[0,1,2]]` (`test_t54:119-127`), i.e. exact pairs also appear inside the ambiguous group. A future UI that counts both lists independently will double-count; spec must define the presentation rule.
4. **Normalization mismatch between join and hash (observed, precision sharpening).** Fact: `group_by_subtopic` (`staging_validation.py:72-78`) matches with exact `==`, no normalization (docstring admits it, `:55-62`); `activity_content_hash` and the `by_title` index in `find_duplicate_groups` normalize via `_norm`. So `"Fracciones "` vs `"fracciones"` are *different groups* for counting/display but the *same key component* for hashing. During transition this is tolerable (helper is labeled transitional), but the backfill/migration spec must state which normalization wins for relational FK resolution — hypothesis: normalized `_norm` wins, exact-`==` retires with the JSON join.
5. **Canonicalization depth is under-specified (observed).** Fact: `activity_content_hash` canonicalizes the proposal via `json.dumps(sort_keys=True)` round-trip (`:200-206`) but only normalizes the two title strings; inner proposal text (`title`, `objective`, `micro_lesson`, questions) is compared byte-wise after `sort_keys`, not whitespace/case-normalized. Two retries differing only by trailing space inside `micro_lesson` yield different hashes → land in `same_title_diff_content` instead of `exact`. That is safe (human review) but noisy; spec should either normalize inner text recursively or explicitly accept the noise and say so.
6. **`added_by_topup` exclusion is correct (observed).** Fact: hash excludes the flag (`:193`), so a topup retry of identical content hashes equal to the original → `exact`, collapsible. Correct; do not "fix" by including origin in the key.
7. **Convert positional hazard still open, now blocks dedup UI (observed, carry-over sharpened).** Fact: remove path uses `_activity_id` (`views.py:2317`), convert path still uses `job.activities[int(index)]` (`views.py:2455-2456`). Any dedup UI that hides/collapses rows shifts indices and makes the hazard worse. The `activity_id` switch is therefore a strict prerequisite to surfacing the duplicate report, not a parallel cleanup.
8. **Backfill destination undefined (observed).** Fact: ADR-0010 §3 says "backfill (recalculando `content_hash`, reportando ambiguos…)" but neither the ADR nor `docs/DATABASE.md` names the artifact: management command output, migration-time report table, `llm_log` entry, or review-screen section. Old jobs may lack `id` (validator allows absent, `staging_validation.py:143-146`), so backfill must assign stable `hex8` without colliding with existing ones — also unspecified.
9. **#57 gate green (evidence).** Fact: `python3 scripts/check_migrations.py` → `OK — numeración lineal sin duplicados` this pass. `pytest` could not be executed (no module / no `.venv`); `test_t54` conformance is by reading only.
10. **Schema-path wording still stale (observed, carry-over).** Fact: `models.py:1875` says `curriculum/schemas/v1`, directory is flat (`curriculum/schemas/*.schema.json`), `schemas/README.md:3` says "`v1/` plano en esta carpeta" (ambiguous). No functional impact (Python validator is runtime truth). Docs-only fix, still deferred.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (double-write → backfill with ambiguous report → new-read → drop JSON writes). This phase confirms the hash key and report-only policy are correctly designed; what is missing is *wiring and surface*, not key redesign.
- Ambiguity policy sharpened: `exact` = safe to collapse **only with explicit human confirmation**, never auto-delete; `same_title_diff_content` = always side-by-side to human review, never auto-pick, never touch `selected`/editorial state; overlapping membership (exact ⊆ ambiguous window) must be presented as one merged section per title-key with per-pair badges, not two independent counts.
- Normalization decision for the future relational migration: `_norm` (NFKC + casefold + trim) is the canonical join key; exact-`==` in `group_by_subtopic` retires with the JSON join. Inner-proposal whitespace/case handling must be explicitly specified (normalize recursively or document the noise) before the backfill PR.
- No ADR edit in this pass (writes limited to handoffs per loop discipline; ADR update belongs to a future spec pass or the implementing PR's same-PR docs update per rule #58).

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree on `updated-tech`? Supervisor cannot commit. (Carry-over from iteration 2.)
2. Agent-ready: where should the duplicate report surface — review-screen section vs `llm_log` entry vs management-command output for backfill? Draft spec below proposes review-screen + backfill command, but the human review-surface preference is unconfirmed.
3. Agent-ready: recursive normalization of inner proposal text for `activity_content_hash`, or documented byte-comparison noise? Needs a decision before backfill (changes hash values for existing rows).
4. Docs: canonicalize the schema path wording (`schemas/` flat, version in `SCHEMA_VERSION` + `$id`) in `models.py:1875`, `schemas/README.md:3`, and the loop-implementacion handoff? (Carry-over.)

## Ranked recommendations

1. Wire the duplicate report into the three pipeline touchpoints (post-generate append guard, pre-topup count, pre-convert list) as **report + human confirm**, per ADR-0010; exact never auto-deletes, ambiguous never auto-merges. Includes the backfill command spec (recalculate hash, assign collision-free `hex8` to id-less rows, emit per-job ambiguous report without touching editorial state).
2. Convert-path `activity_id` switch (`views.py:2455-2456` → resolve via `_activity_id`, reusing `views.py:2301-2304`) as strict prerequisite to any dedup UI.
3. Pin hash canonicalization depth (recursive `_norm` on inner proposal strings vs documented noise) and normalization-wins rule (`_norm` replaces exact-`==`) in ADR-0010 + `docs/DATABASE.md` in the same PR (rule #58).
4. Update #58 order to the fused sequence (#57 prerequisite → fused #53/#98/#54 → periphery #55/#56/#65) and fix the three stale `schemas/v1` wordings.
5. Keep periphery (#55 streaming, #56 landing, #65 half-life) and prototypes/`evidence/demo-viernes/` out of the staging critical path.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (`staging_validation.py:55-78,189-238`, `views.py:2218-2228,2380-2391,2420-2443,2446-2474,2301-2325`, `models.py:1874-1896`, `test_t54_staging_contracts.py:108-127`, `scripts/check_migrations.py`), not stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims).
- Dedup behavior: retry of identical content appends nothing without human confirm (or collapses with explicit confirm — ticket must pick one); `exact` pairs deduplicable, `same_title_diff_content` listed side-by-side, never silently merged; backfill recalculates `content_hash`, assigns collision-free `hex8` where absent, reports ambiguities, never touches `selected`/state/editorial decisions.
- Presentation rule for overlap: one section per `(topic, sub, title)` key with per-pair `exact`/`ambiguo` badges; no double-counting across the two lists.
- Green: t15/t16/t19/t20/t22/t24 plus `test_t54_staging_contracts.py`; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` updated in the same PR (rule #58); #57 gates in the same PR.
- Branch stays `updated-tech`; no merge, commit, or issue creation by the agent — draft issue text in Markdown only.

## Next move

Next supervisor pass (iteration 4): re-check whether the working tree changed (committed, amended, hash wired into views, or relations added). If wired, verify the three touchpoints and the report surface against this spec; if unchanged, record "no new evidence" and either draft the ADR-0010 §2–§3 precision patch (canonicalization depth + report surface + backfill artifact) or advance the rotating phase. Checkpoint duties: cumulative synthesis at iteration 10, final synthesis at iteration 100 — neither is due now.
