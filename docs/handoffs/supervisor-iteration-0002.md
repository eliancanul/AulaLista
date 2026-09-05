# Supervisor iteration 0002 — staging join + relational model

Iteration: 2 | Phase focus: curriculum staging join and relational model
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

Prior memory: dated handoffs `2026-09-05-01..04`, `2026-09-05-cierre-loop`,
`2026-09-05-loop-implementacion`. No `supervisor-iteration-0001.md` and no
`supervisor-cumulative.md` exist — this is the first handoff under the
supervisor protocol; the dated handoffs serve as working memory. Not a 10th
iteration, so no cumulative update is due.

## Scope

Verify the Phase-focus claims against current code: title-based staging join,
god-files, JSON-without-schema, N+1, duplicated cursor, secrets/debug, and the
#53/#98/#54 single-decision thesis. Correct stale line cites without touching
implementation. Spec only — nothing was fixed in this pass.

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`,
`docs/implementation-current.md`, `docs/teacher-flow.md`,
`docs/adr/0010-staging-relacional-idempotente.md`,
`docs/adr/0007-group-roadmap-progress-per-session.md`,
`docs/adr/0009-pseudonymous-results-and-classroom-retention.md`, all six
`docs/handoffs/*.md`, plus read-only inspection of `curriculum/views.py`
(2950 lines), `curriculum/models.py` (2038), `curriculum/staging_validation.py`
(238), `curriculum/services/roadmap_cursor.py` (27),
`curriculum/services/results.py` (552), `curriculum/schemas/*.schema.json` +
`README.md`, `aulalista/settings.py:1-35`, `scripts/check_migrations.py` (53).

## Findings (observed facts vs hypotheses)

1. **Title join NOT eliminated — relocated, correctly labeled transitional.**
   Fact: `curriculum/staging_validation.py:72-78` (`group_by_subtopic`) still
   joins on exact `==` of `topic_title`/`subtopic_title`; producers still write
   title keys at `curriculum/views.py:2221-2222` and `2383-2384`; consumer
   `_grouped_activities` at `views.py:2420-2443` now delegates to the helper
   but keeps the same key. The old cites `views.py:2875-2876,2959-2960` are
   stale (file shrank 3504→2950). ADR-0010 and the helper docstring
   (`staging_validation.py:55-62`) explicitly mark this as the future
   replacement target — that framing is accurate, not a contradiction.
2. **Positional-index bug half-fixed.** Fact: `_activity_id()` exists at
   `views.py:2301-2304` and the remove path uses it (`2317`), but
   `_import_action_convert` still reads `job.activities[int(index)]` at
   `views.py:2455-2456`. A reorder between render and POST can still convert
   the wrong draft. Hypothesis: switching convert to `activity_id` is small
   and safe — left as a ready-for-agent item, not done here.
3. **N+1 fixed (observed).** Fact: `models.py:1129-1146` uses one
   `in_bulk` with fail-closed `DoesNotExist` on missing snapshots. Old cite
   `models.py:1125-1127` is stale; the fix is real.
4. **Cursor dedup done (observed).** Fact: 7 call sites route through
   `_roadmap_cursor.current_activity_id` (`views.py:2505,2579,2599,2634,2770,
   2807,2866`); implementation is 27 lines in
   `curriculum/services/roadmap_cursor.py`. `views.py:1068` reads the model
   attribute directly and is not duplicated cursor logic.
5. **God-files reduced, still large.** Fact: `views.py` 3504→2950,
   `models.py` 1998→2038, new `services/results.py` (552). Direction good;
   files remain god-sized — no new claim beyond that.
6. **Schema-path docstrings disagree (minor, docs-only).** Fact:
   `models.py:1875` says `curriculum/schemas/v1`, but the directory is flat
   (`curriculum/schemas/*.schema.json`, no `v1/`); `staging_validation.py:5`
   says `schemas/*.schema.json` (accurate); `schemas/README.md:3` says
   "`v1/` plano en esta carpeta" (ambiguous); `2026-09-05-loop-implementacion`
   says `schemas/v1/` (stale). No functional impact: the Python validator is
   the runtime source of truth and the JSON files are doc/fixtures per the
   README. Precision fix belongs in a future docs pass.
7. **`clean()` contract matches ADR-0010 intent (observed).** Fact:
   `models.py:1874-1896` validates only non-empty payloads; `save()` does not
   call `clean()` (pipeline writes partials); human review calls
   `full_clean()`. Correct; no change proposed.
8. **Secrets/debug softened, defaults still local-permissive (observed).**
   Fact: `aulalista/settings.py:7-23` reads `AULALISTA_SECRET_KEY` /
   `AULALISTA_DEBUG` / `AULALISTA_ALLOWED_HOSTS` from env with local defaults
   plus a deploy warning comment. Acceptable for the local node; must not
   deploy without env. Docs-only follow-up at most.
9. **Relational tables still future — correct per this loop.** Fact: no
   `Topic`/`Subtopic`/`ActivityProposal` models exist; ADR-0010
   (`docs/adr/0010-staging-relacional-idempotente.md:28`) schedules them as a
   future migration with double-write → backfill → new-read. The #53/#98/#54
   single-decision thesis holds: step 1 (schemas + `content_hash` +
   `find_duplicate_groups` reporting without silent fusion +
   `CurriculumImportJob.clean()`) is present; enforcement and tables are not.
10. **#57 satisfied as tooling, #58 still stale, periphery untouched.**
    Fact: `scripts/check_migrations.py` exists; `docs/DATABASE.md` documents
    the pre-PR convention. #58 order predates the fusion (per handoff 04) and
    still needs updating. #55/#56/#65 untouched — correct.

## Decisions (spec only)

- The single #1 architectural change remains **ADR-0010 relational staging
  with idempotency** (double-write → backfill with ambiguous report →
  new-read → drop JSON writes). No competing #1 emerged this pass.
- Next increment is the convert-path `activity_id` switch plus the
  `schemas/v1` docstring precision fix — both small, both left specified
  but unimplemented per loop rules.
- The uncommitted Phase A–E working tree (loop-implementacion) is **not**
  reviewed-in, committed, or merged by this pass; supervisor records only.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree on `updated-tech`?
   Supervisor cannot commit.
2. Agent-ready: should `_import_action_convert` (`views.py:2455-2456`) switch
   from positional `select` indices to `activity_id` (reusing `_activity_id`)?
3. Docs: canonicalize the schema path wording (`schemas/` flat, version in
   `SCHEMA_VERSION` + `$id`) in `models.py:1875`, `schemas/README.md:3`, and
   the loop-implementacion handoff?

## Ranked recommendations

1. Relational staging migration per ADR-0010 (double-write → backfill with
   ambiguous report → new-read), with #57 pre-PR gates in the same PR.
2. Convert-path `activity_id` fix (kills the remaining positional-index
   hazard from finding 2).
3. Update #58 order to the fused sequence (#57 prerequisite → fused
   #53/#98/#54 → periphery #55/#56/#65) and fix the three stale
   `schemas/v1` wordings.
4. Keep periphery (#55 streaming, #56 landing, #65 half-life) and
   prototypes/`evidence/demo-viernes/` out of the staging critical path.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (`staging_validation.py:72-78`,
  `views.py:2221-2222,2383-2384,2420-2443,2455-2456,2301-2304`,
  `models.py:1129-1146,1874-1896`, `settings.py:7-23`), not the stale
  pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher
  activates; AI proposes only; immutable SHA256 snapshots; synthetic
  DemoPackage with zero pedagogical claims).
- Backfill must recalculate `content_hash`, report `exact` vs
  `same_title_diff_content` ambiguities to human review, and never silently
  merge or touch editorial decisions/state.
- Green: t15/t16/t19/t20/t22/t24 plus `test_t54_staging_contracts.py`;
  `scripts/check_migrations.py` + `makemigrations --check` clean;
  `docs/DATABASE.md` updated in the same PR.
- Branch stays `updated-tech`; no merge, commit, or issue creation by the
  agent — draft issue text in Markdown only.

## Next move

Next supervisor pass (iteration 3): re-check whether the working tree changed
(committed, amended, or new relations added), then either sharpen the
double-write/backfill spec or record "no new evidence" with tighter
acceptance criteria. Checkpoint duties: cumulative synthesis at iteration 10,
final synthesis at iteration 100 — neither is due now.
