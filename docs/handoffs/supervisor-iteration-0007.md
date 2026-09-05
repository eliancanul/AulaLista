# Supervisor iteration 0007 — schemas, migration sequence, and rollback safety

Iteration: 7 | Phase focus: schemas, migration sequence, and rollback safety
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

Prior memory: `supervisor-iteration-0006.md` (security/deployment envelope), `-0005.md` (tests/evidence matrix), `-0003.md` (idempotency/ambiguity), `-0002.md` (staging join + relational model), dated handoffs `2026-09-05-01..04`, `cierre-loop`, `loop-implementacion`, `supervisor-bootstrap`. Notes: no `supervisor-iteration-0001.md` / `-0004.md` and no `supervisor-cumulative.md` exist on disk; not due (10th iteration). Working-tree shape is **byte-identical in `git status` to iterations 2, 3, 5, and 6**, and line counts are unchanged (`views.py` 2950 / `models.py` 2038 / `settings.py` 135 / `staging_validation.py` 238 / `test_t54` 127). This pass records "no new tree evidence" and delivers the phase-focus artifact: a schemas↔migration-sequence↔rollback-safety spec, not a repeated conclusion.

## Scope

Phase-focus: pin down everything a future ready-for-agent ticket needs to execute the fused #53/#98/#54 migration without data loss — what `curriculum/schemas/` actually enforces today, the exact ordered migration sequence with #57 as prerequisite, and the rollback guarantee at each step. Spec only — nothing implemented, per loop rules.

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `curriculum/schemas/README.md` + `topics.schema.json` + `activities.schema.json` (full), `curriculum/staging_validation.py` (238, full re-read), `curriculum/models.py:1760-1899` (`CurriculumImportJob` + `clean()`), `curriculum/views.py:2301-2474` (`_activity_id`, remove/topup/grouped/convert), `curriculum/migrations/` inventory (0001–0029, no 003x), `scripts/check_migrations.py` (53), `tests/test_t54_staging_contracts.py` (127, full re-read). Ran `python3 scripts/check_migrations.py` → OK. `pytest` unrunnable here (runtime-only env, no `.venv`), so all test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **Schemas are doc-plus-Python, not JSON-enforced at runtime (observed).** Fact: `schemas/*.schema.json` exist with `$id …/schemas/v1/…` and `draft 2020-12`, but no code loads them — `models.py:1874-1896` `clean()` delegates to `staging_validation.validate_topics/activities/llm_trace`, and `staging_validation.py:1-7` states this explicitly ("Python puro … Los schemas … son la documentación ejecutable"). Consequence: a drift between a `.schema.json` edit and the Python validator is silent unless a test pins both. `test_t54:55-105` pins only the Python side.
2. **Schema-path wording still stale, now load-bearing for this phase (observed, carry-over 5→6→7).** Fact: `models.py:1875` docstring says ``curriculum/schemas/v1`` but the directory is flat (`curriculum/schemas/*.schema.json`, no `v1/`); `schemas/README.md:3` says "`v1/` plano en esta carpeta" (ambiguous); ADR-0010 §Consecuencias says "crea `schemas/v2/`". Three different path stories for the same future step. A migration ticket that follows any one of them verbatim creates the new version in the wrong place.
3. **Version rule has no enforcement point (observed).** Fact: `SCHEMA_VERSION = "v1"` (`staging_validation.py:16`) is a constant nothing branches on; payloads carry no version field; `validate_*` accept v1 shape unconditionally. The README rule ("compatible → keep v1; accepting/rejecting → copy three files to `v2/` + bump `$id` + `SCHEMA_VERSION`") is therefore a human convention, not a code gate. Any ticket touching a shape must add the version gate or state why it stays v1.
4. **Validator coverage gaps that constrain the migration spec (observed).** Fact: `ACTIVITY_KEYS` (`staging_validation.py:20`) excludes `added_by_topup`, and `validate_activities` never checks its type (schema allows boolean, code ignores it); neither the schema nor the validator mentions `content_hash` (the #98 key lives only in `activity_content_hash()` at `:189-208`, zero pipeline call sites — confirmed again this pass). So today's "valid" payload is hash-less by design; the backfill is what introduces hashes, and the ticket must say where the hash will live (new relational column, not a JSON key) to avoid inventing a JSON `content_hash` field mid-transition.
5. **Migration head is 0029; the relational step has not started (observed).** Fact: `curriculum/migrations/` holds 0001–0029 linearly, no 003x; `check_migrations.py` re-run OK this pass; DATABASE.md §Deuda-3 + §Convenciones still record the 0020 collision antecedent (#37 vs #38) and the #57 pre-PR gate (`check_migrations.py` + `makemigrations --check`). ADR-0010 names #57 as prerequisite and rule #58 (model/pipeline change ships `docs/DATABASE.md` in the same PR). Nothing in the tree contradicts this ordering.
6. **Rollback surface is fully implicit today (observed, the phase gap).** Fact: no feature flag, no dual-read switch, no backfill command exists in code; `job.save()` paths in `views.py:2324,2365,2403-2416,2472-2473` write JSON unconditionally; `clean()` deliberately skips `save()` (partials, `models.py:1874-1880`) so half-written jobs are normal. Hypothesis (spec-level, unchanged): the only safe rollback during transition is "keep JSON writes until the drop step, new tables are additive" — any ticket that drops a JSON write in the same migration that adds the read has no rollback.
7. **Convert path still positional, still the pre-dedup blocker (observed, carry-over 2→3→5→6).** Fact: `_import_action_convert` at `views.py:2452-2456` uses `job.activities[int(index)]` while `_import_action_remove_activity` at `:2301-2325` resolves via `_activity_id`. Reorder-between-render-and-POST still converts the wrong draft. The migration sequence must switch convert to `_activity_id` before any dedup UI or backfill-driven collapse, or the backfill will certify rows the UI then mis-addresses.
8. **Stale-number hazard persists (observed, carry-over 2→3→5→6).** The loop prompt's cites (`views.py:2875-2876,2959-2960`, `views.py:3504`, `models.py:1998`, `models.py:1125-1127`) remain pre-shrink numbers. Current cites are §Files-inspected lines above. Every future ticket must cite current lines.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (double-write → backfill with ambiguous report → new-read → drop JSON writes). This phase adds the schemas/migration/rollback envelope that change must fit inside.
- Ordered migration sequence (each item is a separate, individually revertible migration + code step; #57 gate runs before each PR):
  - **M0 — precision patch (docs + comment only, no behavior):** fix `models.py:1875` wording to the flat truth, disambiguate `schemas/README.md:3`, canonicalize the ADR-0010 `schemas/v2/` sentence to one path convention (recommended: flat `*.schema.json` today, `schemas/v2/*.schema.json` on bump — ticket picks one and updates all three cites together). Acceptance: prompt-number hygiene gate.
  - **M1 — relational tables (additive, fully reversible):** new `Topic(job_fk, titulo, pagina_inicio, pagina_fin, orden)`, `Subtopic(topic_fk, titulo, actividades_sugeridas, orden)`, `ActivityProposal(subtopic_fk, id_estable hex8, content_hash, is_valid, issues_json, proposal_json, selected, added_by_topup)` per ADR-0010 §Decisión-1. JSONFields stay the write path; new tables are write-only mirror (double-write) or empty. Rollback: drop tables, JSON is untouched truth.
  - **M2 — backfill command (data migration + management command, re-runnable, non-destructive):** recalculate `activity_content_hash` for every existing row, assign collision-free `hex8` where `id` absent, emit per-job ambiguous report (`exact` vs `same_title_diff_content`), never touch `selected`/state/editorial decisions, never delete JSON. Rollback: truncate new tables, re-run; JSON unchanged so re-backfill is idempotent.
  - **M3 — new-read behind explicit switch (reversible by flag):** `_import_action_*`, `_grouped_activities`, remove/topup read the relational tables; JSON kept as fallback/serialization during transition. Convert switched to `_activity_id` resolution in this step at the latest (prerequisite to any dedup UI). Rollback: flip switch back to JSON read; both stores still populated by double-write.
  - **M4 — drop JSON writes (destructive, last, human-confirmed):** only after M3 has run green with zero ambiguous-unreviewed jobs and the report surface is reviewed. Separate PR, explicit human confirm, `docs/DATABASE.md` updated in the same PR (rule #58).
- Rollback guarantees per step: M0 — trivial revert (docs only). M1 — `migrate <app> <prev>` drops empty/additive tables, zero data loss (JSON never stopped being truth). M2 — reverse is truncate-and-re-run; backfill never mutates JSON or editorial state so re-running converges. M3 — code flag back to JSON read; double-write means both stores agree. M4 — **no automatic rollback** (data deleted); requires a pre-merge JSON export artifact + restore runbook named in the ticket, otherwise the PR is rejected. Single-process SQLite note: DDL and backfill run in one process, no concurrent writers (T10 bound + `locked` finding from iteration 5 stand).
- Schema-versioning rule for the ticket: payload shapes carry no version field today, so the ticket must state (a) whether the relational cutover keeps v1 semantics byte-identical (then no `v2/`), or (b) which accept/reject change forces `v2/` (copy three schemas, bump `$id` + `SCHEMA_VERSION`, add the version branch in `staging_validation`). Silent `.schema.json`-without-Python or Python-without-`.schema.json` edits are rejected; `test_t54` + `test_t24` stay green with minimal adjustments.
- Methodology note for the 100th-iteration final: this handoff is the "schemas/migration/rollback" row of the evidence matrix — future passes update only the sequence/rollback cites and the Gap column, never the M0→M4 order without code evidence.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree on `updated-tech`? Supervisor cannot commit. (Carry-over 2→3→5→6→7.)
2. Agent-ready: path convention for `v2` — flat files vs `schemas/v2/` subdir? ADR-0010 says `schemas/v2/`, disk is flat, README is ambiguous. One-line human pick unblocks M0. (Sharpened this pass.)
3. Agent-ready: recursive `_norm` on inner proposal text vs documented byte-comparison noise? Changes hash values — must be decided before M2 backfill. (Carry-over 3→5→6→7.)
4. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? Iteration-3 draft proposes review-screen + backfill command; human preference unconfirmed. M2 needs the answer. (Carry-over 5→6→7.)
5. Agent-ready: M4 JSON-export artifact — full `topics`+`activities` dump per job vs snapshot-table export? Needed for the M4 restore runbook. (New this pass.)
6. Missing-sequence: `supervisor-iteration-0001.md` and `-0004.md` do not exist; numbering arrives externally. Confirm counter source or accept gaps? (Carry-over 5→6→7.)

## Ranked recommendations

1. Execute M0→M4 in order with the #57 gate (`scripts/check_migrations.py` + `makemigrations --check` green) and rule-#58 `docs/DATABASE.md`-in-same-PR on every model/pipeline step; wire the duplicate report into the three pipeline touchpoints (post-generate append guard, pre-topup count, pre-convert list) as **report + human confirm** per ADR-0010 no later than M2. Acceptance: matrix rows A2+A3+A4+A8 (iteration 5).
2. Convert-path `activity_id` switch (`views.py:2452-2456` → resolve via `_activity_id`, reusing `views.py:2301-2304`) no later than M3, strict prerequisite to any dedup UI. Acceptance: iteration-5 row A5 (new test: reorder-between-render-and-POST converts the intended draft).
3. M0 precision patch (docs + comment only): fix `models.py:1875`, `schemas/README.md:3`, ADR-0010 `schemas/v2/` sentence, and the `settings.py:7-10` fail-closed wording (iteration 6) in one pass — no behavior change. Acceptance: iteration-5 rows A1+A4 + prompt-number hygiene gate.
4. Update #58 order to the fused sequence (#57 prerequisite → fused #53/#98/#54 as M0→M4 → periphery #55/#56/#65).
5. Keep periphery (#55 streaming, #56 landing, #65 half-life), multi-worker/TLS/institutional-deploy proposals, and prototypes/`evidence/demo-viernes/` out of the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (`curriculum/schemas/*.schema.json`, `staging_validation.py:16-27,55-80,189-238`, `models.py:1760-1899`, `views.py:2301-2325,2343-2365,2420-2474`, `scripts/check_migrations.py`, `test_t54:55-127`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iterations 5 (evidence matrix) and 6 (LAN-only HTTP, staff-gated pipeline, sealed device cookies, single-process SQLite, no new egress).
- Migration order: M0 docs-only → M1 additive tables → M2 re-runnable backfill (recalculate hash, collision-free `hex8`, per-job ambiguous report, never touch `selected`/state/editorial) → M3 flagged new-read + convert-to-`activity_id` → M4 destructive drop only with JSON-export artifact + restore runbook + explicit human confirm.
- Dedup behavior: retry of identical content appends nothing without human confirm (or collapses with explicit confirm — ticket must pick one); `exact` deduplicable only with confirm, `same_title_diff_content` side-by-side, never silently merged; overlap presentation is one section per `(topic, sub, title)` key with per-pair `exact`/`ambiguo` badges.
- Schema versioning: state v1-keep vs `v2/`-bump with both `.schema.json` and Python validator updated together; `test_t54` + `test_t24` green; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` updated in the same PR (rule #58); no physical-LAN or concurrent-write claims.
- Branch stays `updated-tech`; no merge, commit, or issue creation by the agent — draft issue text in Markdown only.

## Next move

Next supervisor pass (iteration 8): re-check whether the working tree changed (committed, M0 wording fixed, convert switched to `activity_id`, relations/M2 command added, or head moved past 0029). If moved, verify the touched M-step + report surface + rollback guarantee against this sequence and the iteration-5 matrix / iteration-6 envelope; if unchanged, record "no new evidence" and advance the rotating phase. Checkpoint duties: cumulative synthesis at iteration 10, final synthesis at iteration 100 — neither is due now.
