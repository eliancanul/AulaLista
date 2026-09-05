# Supervisor iteration 0008 — god-files, service seams, maintainability spec

Iteration: 8 | Phase focus: god-files, service seams, and maintainability specs
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

Prior memory: `supervisor-iteration-0007.md` (schemas/migration/rollback M0→M4), `-0006.md` (security/deployment envelope), `-0005.md` (tests/evidence matrix A1–A9), `-0003.md` (idempotency/ambiguity), `-0002.md` (staging join + relational model), dated handoffs `2026-09-05-01..04`, `cierre-loop`, `loop-implementacion`, `supervisor-bootstrap`, `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`). Notes: no `supervisor-iteration-0001.md` / `-0004.md` and no `supervisor-cumulative.md` exist on disk; not due (10th iteration). Working-tree shape is **byte-identical in `git status` to iterations 2, 3, 5, 6, and 7**, and line counts are unchanged (`views.py` 2950 / `models.py` 2038 / `settings.py` 135 / `staging_validation.py` 238 / `services/results.py` 552 / `services/roadmap_cursor.py` 27). This pass records "no new tree evidence" and delivers the phase-focus artifact: a god-file → service-seam map with extraction order and maintainability acceptance gates, not a repeated conclusion.

## Scope

Phase-focus: pin down exactly where the god-files are, which seams are extractable without touching the fused #53/#98/#54 critical path, in what order, and under which no-behavior-change gates. Spec only — nothing implemented, per loop rules. `IMPLEMENTATION-GATE.md` is untouched (gate revisions happen at 10th iterations; this is iteration 8).

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0010-staging-relacional-idempotente.md`, function inventory of `curriculum/views.py` (2950 lines, 91 top-level `def`/`class`), `curriculum/models.py` (2038 lines, class-size ranking), `curriculum/services/results.py` (552 lines, 12 fns, full name list), `curriculum/services/roadmap_cursor.py` (27 lines, 1 fn), `curriculum/staging_validation.py` (238 lines, 10 fns), `curriculum/migrations/` inventory (0001–0029, no 003x). Ran `python3 scripts/check_migrations.py` → OK. `pytest` unrunnable here (runtime-only env, no `.venv`), so all test claims are by reading. Largest-function ranking computed read-only this pass (see Findings 1–2).

## Findings (observed facts vs hypotheses)

1. **God-file map, measured this pass (observed).** Fact: `views.py` 2950 lines / 91 defs — largest are `tutor_sessions` 104 lines (`views.py:774-877`), `student_question_assistance` 102 (`:2849-2950`), `_import_action_add_missing_activities` 91 (`:2328-2418`), `tutor_import_detail` 90 (`:1946-2035`), `_run_import_job_stage_once` 88 (`:1576-1663`); `tutor_roadmaps` 81 (`:519-599`), `student_turn_start` 80 (`:360-439`). `models.py` 2038 lines — largest classes are `ClassroomSession` 470 (`models.py:762-1231`), `CurriculumPackage` 255 (`:120-374`), `StudentRoadmapProgress` 182 (`:1501-1682`), `CurriculumImportJob` 155 (`:1760-1914`), `StudentTurn` 149 (`:1351-1499`), `PublishedRoadmapSnapshot` 127 (`:413-539`). Old prompt cites (`views.py:3504`, `views.py:2875-2876,2959-2960`, `models.py:1998`, `models.py:1125-1127`) remain pre-shrink numbers — every future ticket must cite the ranges above.
2. **One extraction already done and it is the pattern exemplar (observed).** Fact: `services/results.py` (552 lines, 12 fns: `_result_activity_catalog`, `_presented_roadmap_activity_ids`, `_frozen_catalog`, `_result_row_activity_context`, `_result_matches_snapshot`, `_result_aggregate`, `_individual_result_register`, `_roadmap_results_navigation`, `_result_card_context`, plus 3 small predicates) plus `services/roadmap_cursor.py` (27 lines, `current_activity_id`, 7 call sites per iteration 2) show the house pattern: pure-ish helpers over `(session, results)` with no new tables, no contract change, thin view delegates. Any new seam must copy this shape — not invent a framework.
3. **Five seams identified, sharply bounded (observed, the phase deliverable).** Fact, by function clustering: **S1 staging pipeline** (`views.py:~1576-2474`: stage runner + `_import_action_*` + `_grouped_activities` + `_activity_id` + POST parsers); **S2 session lifecycle** (`~910-1200`: prepare/review/active/confirm/close + join context + teacher-session guards); **S3 results/export** (already extracted — freeze, see finding 2); **S4 student runtime** (`~226-439` join/turn-start/recover/ready + `~2790-2950` answer/assistance + roadmap context `~2505-2866`); **S5 sealed device/turn cookies** (`~120-225`: `_seal/_unseal/_set_sealed_cookie`, device binding, turn capability). S1 is the only seam overlapping the fused ADR-0010 write path; S2/S4/S5 do not touch staging JSON.
4. **`models.py` is god-sized but not extractable as tables (observed, constraint).** Fact: the four largest classes are Django models whose tables are migration-pinned (0001–0029 linear, `check_migrations.py` OK this pass). Extracting *behavior* (managers, querysets, snapshot-resolution helpers like the `in_bulk` fail-closed path) is allowed; moving fields or splitting tables is a migration and belongs to ADR-0010 M1, not to a maintainability pass. Hypothesis (spec-level): a seam ticket that renames/splits a model field without an M1 migration must be rejected on sight.
5. **Convert positional hazard and hash-wiring gaps unchanged (observed, carry-over 2→3→5→6→7).** Fact re-verified: `_import_action_convert` still positional (`views.py:2452-2456` per iteration 7; ranking confirms the import-action cluster unmoved), `_activity_id` still remove-only, `activity_content_hash`/`find_duplicate_groups` still zero pipeline call sites. S1 extraction must therefore happen **with or after** M3 (new-read + convert-to-`activity_id`), never before — extracting S1 first would churn the exact lines M1–M3 rewrite.
6. **No new evidence on schemas/rollback/security (observed).** `schemas/` flat (4 files, no `v1/`), `staging_validation.py` 238 lines, `settings.py` 135 lines, migrations head still 0029 — all identical to iteration 7. Findings 1–4 of iteration 7 (JSON-schema doc-only, `v2/` path ambiguity, hash-less valid payloads) and the iteration-6 envelope (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, `media/`-in-tarball) stand without amendment.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7). This phase adds the seam envelope it must fit inside.
- Seam extraction order (each a separate no-behavior-change PR, #57 gate green, rule-#58 `docs/DATABASE.md`-in-same-PR only if a model/pipeline line is touched — pure moves touch no docs):
  - **Step 0 — freeze S3.** `services/results.py` + `roadmap_cursor.py` are the pattern reference. No further extraction from the results path until S1 lands; tickets cite it as the delegate-shape example.
  - **Step 1 — S5 (cookies/binding) first.** Smallest, purest, zero staging coupling. Move `_seal/_unseal/_set_sealed_cookie/_device_*_/_turn_*` into `services/device_binding.py` (name is a proposal; ticket picks one) with thin view delegates. Lowest regression risk.
  - **Step 2 — S4 (student runtime) next.** Join/turn/answer/assistance + `_roadmap_context/_activity_snapshot` move as a cohort; snapshot-immutability reads stay exactly as-is (fail-closed `in_bulk` path untouched).
  - **Step 3 — S2 (session lifecycle) next.** Prepare/confirm/close + guards move as a cohort; teacher-ownership scoping and POST+CSRF posture unchanged.
  - **Step 4 — S1 (staging pipeline) LAST, fused with M3.** `_import_action_*`, `_grouped_activities`, POST parsers, and the convert-to-`activity_id` switch move together with the relational new-read flip, so the JSON→relational rewrite and the file move happen once, in one reviewable diff. Extracting S1 earlier is rejected as double churn.
- Seam rules (hard gates for every extraction ticket): no behavior change (byte-identical responses); no new tables/fields/dependencies; no contract change (EditorialReviewer publishes, teacher activates, AI proposes only, SHA256 snapshots, synthetic DemoPackage); thin delegates (views keep routing/auth/POST-shape, services hold logic); existing tests stay green with zero fixture edits unless the ticket names each one; `scripts/check_migrations.py` + `makemigrations --check` clean.
- Methodology note for the 100th-iteration final: this handoff is the "god-files/service-seams" row of the evidence matrix — future passes update only the function-range cites and the Step 0–4 order, never the order without code evidence.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree on `updated-tech`? Supervisor cannot commit. (Carry-over 2→3→5→6→7→8.)
2. Agent-ready: S5 module name — `services/device_binding.py` vs keeping cookie helpers in `views.py`? One-line pick unblocks Step 1. (New this pass.)
3. Agent-ready: S4/S2 cohort boundaries — move with tests-first per seam, or one move + one test PR each? Affects review size. (New this pass.)
4. Agent-ready (carry-over 3→5→6→7): recursive `_norm` on inner proposal text vs documented byte-comparison noise? Must be decided before M2 backfill; S1-Step-4 inherits the pick.
5. Agent-ready (carry-over 5→6→7): duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? M2/S1-Step-4 needs the answer.
6. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` and `supervisor-cumulative.md` do not exist; numbering arrives externally. Confirm counter source or accept gaps? (Carry-over 5→6→7→8.)

## Ranked recommendations

1. Execute seam Steps 0→4 in order with the iteration-7 M0→M4 migration sequence interleaved only at Step 4 (S1 fused with M3); S5 first as the low-risk pattern proof. Acceptance: matrix rows A5+A7 (iteration 5) plus the seam gates in §Decisions.
2. Keep the convert-to-`activity_id` switch inside S1-Step-4/M3 (strict prerequisite to any dedup UI), never as a standalone pre-extraction. Acceptance: iteration-5 row A5.
3. M0 precision patch stays the cheapest unblocked win (docs + comment only): `models.py:1875` flat-path wording, `schemas/README.md:3`, ADR-0010 `schemas/v2/` sentence, `settings.py:7-10` fail-closed wording. Acceptance: iteration-5 rows A1+A4 + prompt-number hygiene gate.
4. Update #58 order to the fused sequence (#57 prerequisite → fused #53/#98/#54 as M0→M4 with S1 at M3 → periphery #55/#56/#65; S5/S4/S2 maintainability moves ride outside the critical path).
5. Keep periphery (#55 streaming, #56 landing, #65 half-life), multi-worker/TLS/institutional-deploy proposals, and prototypes/`evidence/demo-viernes/` out of the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py:120-225` S5, `226-439` + `2790-2950` S4, `519-599,601-674,774-877,910-963,1046-1098,1197-1260,1400-1459` S2, `1576-1663,1946-2035,2190-2261,2328-2418,2301-2325,2452-2456` S1; `models.py:120-374,413-539,622-660,662-760,762-1231,1273-1349,1351-1499,1501-1682,1760-1914`; `services/results.py` 12 fns + `roadmap_cursor.py`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iteration 5 (evidence matrix), 6 (LAN-only HTTP, staff-gated pipeline, sealed device cookies, single-process SQLite, no new egress), and 7 (M0→M4 + rollback guarantees).
- Seam gates: no behavior change; no new tables/fields/dependencies; thin delegates; tests green with named fixtures only; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` updated in the same PR iff a model/pipeline line moved (rule #58); S1 moves only with M3.
- Dedup/schema rules unchanged from iteration 7 (report + human confirm; `exact` only with confirm; `same_title_diff_content` side-by-side; v1-keep vs `v2/`-bump stated with both `.schema.json` and Python validator updated together).
- Branch stays `updated-tech`; no merge, commit, or issue creation by the agent — draft issue text in Markdown only.

## Next move

Next supervisor pass (iteration 9): re-check whether the working tree changed (committed, S5/S4/S2 seam moved, convert switched to `activity_id`, relations/M2 command added, or head moved past 0029). If moved, verify the touched seam step or M-step against this order plus the iteration-5 matrix / iteration-6 envelope / iteration-7 sequence; if unchanged, record "no new evidence" and advance the rotating phase. Checkpoint duties: cumulative synthesis + `IMPLEMENTATION-GATE.md` review at iteration 10, final synthesis at iteration 100 — neither is due now.
