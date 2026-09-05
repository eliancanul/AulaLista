# Supervisor iteration 0009 — ready-for-agent ranking and issue draft quality

Iteration: 9 | Phase focus: ready-for-agent ranking and issue draft quality
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; see Finding 1)

`git status --short --branch` at pass time:

```text
## supervisor/aulalista-docs
 M aulalista/settings.py
 M curriculum/models.py
 M curriculum/views.py
 M docs/DATABASE.md
R  docs/adr/0007-pseudonymous-results-and-classroom-retention.md -> docs/adr/0009-pseudonymous-results-and-classroom-retention.md
A  docs/adr/0010-staging-relacional-idempotente.md
A  docs/handoffs/2026-09-05-01-docs-arquitectura.md
A  docs/handoffs/2026-09-05-02-codigo-curriculum.md
A  docs/handoffs/2026-09-05-03-investigacion-evidencia.md
A  docs/handoffs/2026-09-05-04-techdebt-tests.md
A  docs/handoffs/2026-09-05-cierre-loop.md
A  docs/handoffs/2026-09-05-loop-implementacion.md
A  docs/handoffs/2026-09-05-supervisor-bootstrap.md
A  docs/handoffs/IMPLEMENTATION-GATE.md
A  docs/handoffs/supervisor-iteration-0002.md
A  docs/handoffs/supervisor-iteration-0003.md
A  docs/handoffs/supervisor-iteration-0005.md
A  docs/handoffs/supervisor-iteration-0006.md
A  docs/handoffs/supervisor-iteration-0007.md
A  docs/handoffs/supervisor-iteration-0008.md
 M docs/implementation-current.md
 M docs/teacher-flow.md
R  health/templates/health/local_access.html -> templates/health/local_access.html
?? .DS_Store
?? curriculum/schemas/
?? curriculum/services/
?? curriculum/staging_validation.py
?? docs/.DS_Store
?? scripts/check_migrations.py
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty (nothing staged; the `A` entries above are committed in `675eadb` on this branch, the `M`/`??` entries are the uncommitted Phase A–E tree). No commit/merge performed by this pass.

Prior memory: `supervisor-iteration-0008.md` (god-files/service seams S1–S5 + Steps 0–4), `-0007.md` (schemas/migration M0→M4 + rollback), `-0006.md` (security/deployment envelope), `-0005.md` (tests/evidence matrix A1–A9), `-0003.md` (idempotency/ambiguity), `-0002.md` (staging join + relational model). Notes: no `supervisor-iteration-0001.md` / `-0004.md` and no `supervisor-cumulative.md` exist on disk; cumulative + gate review fall due at iteration 10, not now. `IMPLEMENTATION-GATE.md` was committed on this branch as `STATUS: READY_FOR_IMPLEMENTATION` — off-cycle relative to that protocol; see Finding 6.

## Scope

Phase-focus: grade every open issue that claims or needs `ready-for-agent` on the staging critical path, rank them into a single ordered ready-for-agent queue, and ship a draft ticket text (Markdown only, nothing created on the tracker) that a future agent could execute without re-reading the code. Spec only — nothing implemented, per loop rules.

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `docs/handoffs/IMPLEMENTATION-GATE.md`, `wc -l` of `curriculum/views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `tests/test_t54_staging_contracts.py` (127), `curriculum/migrations/` inventory (0001–0029, no 003x), `rg` for `activity_content_hash|find_duplicate_groups|_activity_id|_import_action_convert` across `curriculum/`, convert block vs remove block re-read, `python3 scripts/check_migrations.py` → OK. Read-only `gh` inspection: full open-issue list (24 issues) with labels, plus bodies of #53/#54/#57/#58/#98. `pytest` unrunnable here (runtime-only env, no `.venv`), so all test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **Branch anomaly (observed).** The loop prompt says work starts on `updated-tech`; this pass runs on `supervisor/aulalista-docs` (`675eadb` = docs gate + handoffs on top of `82d4a9d`, which equals `updated-tech` tip). The uncommitted Phase A–E tree is still present and `git status` shape is unchanged from iterations 2, 3, 5, 6, 7, 8. Consequence: every file:line cite below is valid on both branches (tree content identical), but the next pass should state which branch it runs on — cites are content-addressed to the tree, not the branch name.
2. **No new tree evidence (observed).** Line counts byte-identical to iterations 2/3/5/6/7/8; migrations head still 0029; `check_migrations.py` re-run OK this pass; `schemas/` still flat (4 files, no `v2/`); convert still positional (see Finding 3). This pass therefore grades drafts and ranks, and does not repeat a conclusion.
3. **Convert positional hazard re-verified in the working tree (observed).** `_import_action_convert` still reads `entry = job.activities[int(index)]` while `_import_action_remove_activity` resolves via `_activity_id(entry, index)` (`views.py:2301-2325`). Any dedup UI or backfill-driven collapse that shifts indices makes the hazard worse — the `activity_id` switch stays a strict prerequisite to surfacing the duplicate report (carry-over 3→5→6→7→8).
4. **Hash/dedup still unwired (observed).** `rg` confirms `activity_content_hash` / `find_duplicate_groups` live only in `curriculum/staging_validation.py` + `tests/test_t54_staging_contracts.py`; zero pipeline call sites in `views.py`/`models.py`. The three touchpoints from iteration 3 (post-generate append guard, pre-topup count, pre-convert list) remain the only legal wiring points, always as report + human confirm.
5. **Tracker contradiction: #98 is NOT the sole `ready-for-agent` issue (observed, prompt correction).** Open `ready-for-agent` issues today: #95, #97, #98, #103, #104, #107 (six). The prompt's "sole ready-for-agent path" claim is true only with the missing qualifier: **#98 is the sole `ready-for-agent` issue on the staging critical path** (labels: `bug` + `ready-for-agent` + `tech-debt`). The other five are off-path: #95/#103/#104 (Dirección A institucional), #97 (cancel-assistance UI), #107 (A→B validation). They must not interleave with staging writes. Future prompts should carry the qualified sentence.
6. **Gate contradiction (observed, deferred to iteration 10).** `IMPLEMENTATION-GATE.md` on this branch says `STATUS: READY_FOR_IMPLEMENTATION`, but the loop rule defaults to `HOLD` and reserves gate changes for 10th iterations. Quality gaps in the committed gate: (a) base ref is self-referential (`supervisor/aulalista-docs` names its own branch); (b) allowed-paths list spans models + a new 0030 migration + `curriculum_import.py` + `views.py` + `staging_validation.py` + three test files — broader than one bounded change; (c) the convert-to-`activity_id` switch is conditional ("only if required") while iterations 3/5/7/8 spec it as mandatory no-later-than-M3; (d) no line cites, no named ambiguous-report surface pick (iteration-7 open questions 3–4 still open). This pass does NOT edit the gate (10th-iteration duty); it records the revert-or-narrow decision for iteration 10.
7. **Issue draft quality grades (observed, the phase deliverable).**
   - **#98 — best draft, still not agent-executable.** Has acceptance criteria (retry/partial/same-title-different-source, report-ambiguity, preserve sources/editorial/human decisions, #47 antecedent). Missing: exact file:line cites (uses no paths at all), out-of-scope list, migration/rollback plan, contract-preservation clause, base ref, and the three touchpoint names. Grade: closest to `ready-for-agent`; needs the §Draft below appended before any coding lane consumes it.
   - **#53 — plan without acceptance.** Good shape (FK tables, double-write→backfill→new-read, test net t15/t16/t19/t20/t22/t24) but zero acceptance criteria, no idempotency key, no ambiguity policy, and a stale blocker ("Después de la demo del viernes" — that demo is months past). Grade: `tech-debt`, correctly NOT `ready-for-agent`; must reference the fused ADR-0010 + #98 instead of standing alone.
   - **#54 — intent without acceptance.** Two sentences, no criteria, no v1-keep vs `v2/`-bump rule, no validator/schema dual-update requirement. Grade: correctly NOT `ready-for-agent`; the iteration-7 M0 precision patch is its only unblocked slice.
   - **#57 — proposal without gate text.** Names the script + convention correctly (and the tooling now exists: `scripts/check_migrations.py`, verified green this pass), but states no pass/fail gate an agent can assert. Grade: correctly NOT `ready-for-agent` (it is process tooling, and the prerequisite claim lives in ADR-0010, not in the issue).
   - **#58 — stale order (observed).** Lists #53→#54→#57→#55→#56, omits #98 entirely, omits #65, and puts #57 third although ADR-0010 and iterations 5/7/8 make #57 the prerequisite to everything. Grade: epic body needs a one-paragraph fusion update (fused #53/#98/#54 as one item, #57 first, #55/#56/#65 peripheral) — docs-only, human-confirmed.
8. **Stale-number hazard persists (observed, carry-over).** The loop prompt's cites (`views.py:2875-2876,2959-2960`, `views.py:3504`, `models.py:1998`, `models.py:1125-1127`) remain pre-shrink numbers. Current cites are §Files-inspected lines above. Every ticket draft must cite current lines — the §Draft below does.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, seam Steps 0–4 per iteration 8). This phase adds the ready-for-agent queue it must be consumed through.
- Ready-for-agent queue (each a separate ticket/MR; #57 gate green before each; rule-#58 `docs/DATABASE.md`-in-same-PR on any model/pipeline step):
  - **R1 — M0 precision patch (docs + comments only, no behavior).** Fix `models.py:1875` flat-path wording, `schemas/README.md:3` ambiguity, ADR-0010 `schemas/v2/` sentence, `settings.py:7-10` fail-closed wording. Smallest unblocked win; unblocks all later cites.
  - **R2 — Convert-to-`activity_id` switch.** `views.py` convert block → resolve via `_activity_id` (reuse remove-path pattern); new test: reorder-between-render-and-POST converts the intended draft. Strict prerequisite to any dedup UI (Finding 3).
  - **R3 — Fused staging slice per ADR-0010 (M1→M3 only; M4 excluded).** Additive tables + re-runnable backfill (hash recalc, collision-free `hex8`, per-job ambiguous report, never touch `selected`/state/editorial) + flagged new-read; JSON writes stay. M4 (drop JSON writes) is a separate human-confirmed ticket with a named JSON-export artifact + restore runbook — never bundled.
  - **R4 — Maintainability seams S5→S4→S2** (iteration-8 Steps 1–3), outside the critical path, no-behavior-change, thin delegates. S1 rides fused with R3/M3, never alone.
  - **R5 — Periphery stays out** (#55 streaming, #56 landing, #65 half-life, Dirección A/B issues #95/#103/#104/#107, #97 cancel-assistance): no `ready-for-agent` promotion onto the staging path; #58 epic body updated docs-only to the fused order.
- Label hygiene (proposals, human applies — supervisor never edits the tracker): keep `ready-for-agent` on #98 only within the staging path; do NOT add `ready-for-agent` to #53/#54/#57 (they are inputs to R1–R3, not executable tickets); update #58 body to the fused order; remove or refresh the stale "demo del viernes" blocker on #53.

## Draft ready-for-agent ticket text (NOT created — Markdown only, per loop rules)

> **Title:** Staging idempotente R2+R3-slice: convert-to-`activity_id` + duplicate report wiring (no M4)
> **Governs:** `docs/adr/0010-staging-relacional-idempotente.md` + matrices in `supervisor-iteration-0005.md` (A1–A9), envelopes in `-0006.md`/`-0007.md`, seam order in `-0008.md`.
> **Base ref:** `updated-tech` tip `82d4a9d` (verify before starting; tree must match `views.py` 2950 / `models.py` 2038 / `staging_validation.py` 238).
> **Allowed paths:** `curriculum/views.py` (convert block + three touchpoints only), `curriculum/staging_validation.py` (only if canonicalization pick requires it), `tests/test_t54_staging_contracts.py` + one new focused test file, `docs/DATABASE.md` (same PR, rule #58). **Out of scope:** new tables/M1, backfill/M2, flagged new-read/M3, M4 drop, schemas `v2/`, S-seam moves, #55/#56/#65, settings/packaging/TLS, any `ready-for-agent` promotion of #53/#54/#57.
> **Invariants preserved:** human EditorialReviewer publishes; teacher activates; AI proposes only; sessions read immutable SHA256 snapshots; DemoPackage synthetic with zero pedagogical claims.
> **Behavior:** (1) convert resolves via `_activity_id` (`views.py:2301-2304` pattern), never positional; (2) the three touchpoints (post-generate append, pre-topup count, pre-convert list) call `find_duplicate_groups` and present report + human confirm — `exact` collapses only with explicit confirm, `same_title_diff_content` side-by-side, never silently merged; one section per `(topic, sub, title)` key with per-pair `exact`/`ambiguo` badges (no double-count); (3) backfill command is explicitly OUT of this slice.
> **Acceptance:** new test for reorder-between-render-and-POST; `test_t54` + t15/t16/t19/t20/t22/t24 green; `scripts/check_migrations.py` + `makemigrations --check` clean; no physical-LAN or concurrent-write claims; cite current lines only, never the prompt's stale pre-shrink numbers.
> **Rollback:** code-only revert; no migration in this slice, JSON untouched as truth.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree (`updated-tech` content now sitting on `supervisor/aulalista-docs`)? Supervisor cannot commit. (Carry-over 2→3→5→6→7→8→9.)
2. Iteration-10 duty (due next): write `supervisor-cumulative.md` (deltas synthesis; does not exist yet) and review `IMPLEMENTATION-GATE.md` — revert to `HOLD` or narrow to the §Draft slice above with a non-self-referential base ref + mandatory convert switch + named report surface? (New this pass; Finding 6.)
3. Agent-ready (carry-over 3→5→6→7→8): recursive `_norm` on inner proposal text vs documented byte-comparison noise? Must be decided before any backfill slice; R2/R3-draft inherits the pick.
4. Agent-ready (carry-over 5→6→7→8): duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? The §Draft assumes review-screen + pre-convert list; human preference unconfirmed.
5. Agent-ready (carry-over 7→8): M4 JSON-export artifact shape (per-job `topics`+`activities` dump vs snapshot-table export)? Needed before any M4 ticket exists.
6. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` and `supervisor-cumulative.md` do not exist; numbering arrives externally. Confirm counter source at the iteration-10 checkpoint or accept gaps? (Carry-over 5→6→7→8→9.)

## Ranked recommendations

1. Consume staging work strictly in queue order R1→R2→R3 (M1→M3, M4 excluded) → R4 seams; each step names the governing ADR/matrices, exact allowed paths, and the rollback story. Acceptance: iteration-5 rows A2+A3+A4+A5+A8.
2. Upgrade #98 with the §Draft body (paths, touchpoints, presentation rule, out-of-scope, rollback) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent` until their R-slice is drafted the same way. Acceptance: prompt-number hygiene gate + Finding 7 grades resolved.
3. At iteration 10, set the gate to `HOLD` unless the narrowed R2/R3-slice above is genuinely adopted verbatim (governing ADR, exact paths, out-of-scope, invariants, acceptance tests, migration/rollback, zero blockers, concrete non-self-referential base ref). The committed `READY_FOR_IMPLEMENTATION` must not survive review in its current broad form.
4. Update the #58 epic body docs-only to the fused order (#57 prerequisite → fused #53/#98/#54 as M0→M4 → periphery #55/#56/#65), with #98 named and the stale demo blocker dropped.
5. Keep periphery (Dirección A/B #95/#103/#104/#107, #97, #55/#56/#65, multi-worker/TLS/institutional-deploy, prototypes) out of the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` convert vs `views.py:2301-2325` remove pattern; `staging_validation.py:55-78,189-238`; `models.py:1874-1896`; `test_t54:55-127`; `scripts/check_migrations.py`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iteration 5 (evidence matrix A1–A9), 6 (LAN-only HTTP, staff-gated pipeline, sealed device cookies, single-process SQLite, no new egress), 7 (M0→M4 + per-step rollback), and 8 (seam Steps 0–4, S1 fused with M3).
- Queue discipline: R1 docs-only → R2 convert switch (mandatory, tested) → R3 M1→M3 slice (M4 excluded, JSON writes stay) → R4 seams S5/S4/S2; `scripts/check_migrations.py` + `makemigrations --check` clean at every step; `docs/DATABASE.md` updated in the same PR iff a model/pipeline line moved (rule #58).
- Dedup/schema rules unchanged from iterations 3/5/7 (report + human confirm; `exact` only with confirm; `same_title_diff_content` side-by-side; one merged section per title-key with badges; v1-keep vs `v2/`-bump stated with both `.schema.json` and Python validator updated together).
- Branch stays off `main`; no merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 10 — checkpoint): re-check whether the working tree changed (committed, R1 wording fixed, convert switched, report wired, head past 0029). Then perform the due checkpoint duties: (1) write `docs/handoffs/supervisor-cumulative.md` as deltas-only synthesis across iterations 2–10; (2) review `IMPLEMENTATION-GATE.md` against Finding 6 and set `HOLD` unless the narrowed slice is adopted verbatim; (3) if and only if branch state plus a clean docs-only staged set make it safe, package staged `docs/handoffs/` + `docs/adr/` Markdown onto `supervisor/aulalista-docs` in a pushed, non-merged PR (verify `git diff --cached --name-only` first; never `git add -A`, never stage code, never merge/approve/close). Final synthesis at iteration 100 — not due.
