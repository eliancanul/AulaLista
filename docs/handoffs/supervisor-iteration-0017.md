# Supervisor iteration 0017 — schemas, migration sequence, and rollback safety

Iteration: 17 | Phase focus: schemas, migration sequence, and rollback safety
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–16)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). Gate log tip still `b22b55b` (second slice); no third flip. HEAD unchanged since iteration 15. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) already exists — no PR duty until iteration 20. `git diff --stat` working-tree shape unchanged: `views.py` −808-line-dominant (7 files, +209/−716).

Prior memory: `supervisor-iteration-0016.md` (security envelope, Ollama 180s timeout close-out) + `-0015.md` (A1–A9 re-verification, A5a/A5b split, traceability gap) + `-0014.md` (C1–C5 reconciliation) + `supervisor-cumulative.md` (spine 2→10).

## Scope

Phase-focus: re-verify the iteration-7 migration spine (M0→M4 + per-step rollback, rule #58, #57 gate) and the iteration-14 schema findings (C1/C3) against current code, not against prior handoffs. Spec only — nothing implemented. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 20). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `docs/handoffs/IMPLEMENTATION-GATE.md` (log tip check only); full re-read `curriculum/staging_validation.py` (238), `curriculum/schemas/README.md` (14); `scripts/check_migrations.py` (53, re-run → OK); `curriculum/migrations/` inventory (head still 0029, linear); `ls -R curriculum/schemas/` (flat: README + 3 `.schema.json`, no `v2/`); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `git diff --stat`, `git log --oneline -3`, `git log --oneline -5 -- IMPLEMENTATION-GATE.md`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** All line counts byte-identical to iterations 2–16; status differs from iteration 16 only by the new untracked `supervisor-iteration-0016.md` (last pass's own handoff). Migrations head still 0029; `check_migrations.py` re-run → OK; `schemas/` still flat; gate file untouched since `b22b55b` — the two-flip pattern stands, still no third flip. C1–C5 wording unfixed.
2. **Schemas v1 frozen, correctly (observed).** `SCHEMA_VERSION = "v1"` (`staging_validation.py:16`); README version rule intact (compatible clarifications keep v1; accept/reject changes create `v2/` + bump). No `v2/` directory exists — correct, since no breaking shape change has been specified or implemented. `ACTIVITY_KEYS` (`:20`) still omits `added_by_topup`; validator `:139` subset-check only — the iteration-14 non-contradiction verdict (optional top-up flag consistent across DATABASE/schemas/validator/views) re-verified by re-read, unchanged.
3. **C1 still open, byte-identical (observed, carry-over 13→17).** Module docstring `:189-197` still says "Normaliza (NFKC + casefold + trim) topic, subtema y proposal canónico" but code applies `_norm` (`:25-26`) only to `topic`/`subtopic` (`:201-202`); proposal blob is ordered `json.dumps` (`:203-205`) with no recursive `_norm` on inner strings, while the ambiguous key DOES `_norm(proposal.title)` (`:232`). ADR-0010 §Decisión-2 carries the same overstatement. Any M2-backfill ticket that hashes historical rows without the scope pick stated will silently pick a semantics. R1 docs-only fix still pending; backfill wording depends on it.
4. **C3 still open (observed, carry-over 14→17).** `schemas/README.md:3` says "`v1/` plano en esta carpeta" (flat), consistent with on-disk layout — but the `models.py:1875` docstring path `curriculum/schemas/v1` cited in iteration 14 was not re-read this pass; carried as standing R1 docstring fix (flat `*.schema.json` now, `v2/` reserved). No code behavior depends on the path string.
5. **Migration sequence linear, rollback still spec-only (observed).** Head `0029_curriculumimportjob_progress_finished_at.py`; no `003x`; `check_migrations.py` green. The M0→M4 spine from iteration 7 (M0 precision docs-only → M1 additive tables → M2 re-runnable backfill → M3 flagged new-read → M4 drop-JSON as separate human-confirmed ticket with named export + restore runbook, never bundled; per-step rollback; rule #58 DATABASE.md-in-same-PR; #57 gate green before each step) has zero implementation footprint on this branch: no new models, no dual-write, no backfill command, no flagged read. Rollback today = revert working tree / drop branch — there is nothing migrated to roll back, which is the safe state.
6. **M4-export and report-surface picks still unstated (observed, carry-over 7→17).** No per-job-dump vs snapshot-table-export decision; `_grouped_activities` still emits no dedup badges (iteration-15 cite `views.py:2420-2444` carries; not re-read this pass). Both must be answered before any R3/M ticket, after C1.
7. **Fused-decision spine unchanged (observed).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite (green again this pass), #58 stale, #55/#56/#65 peripheral. Gate traceability gap from iteration 15 (on-disk gate cites `coding-41560047f83c.md`, unreachable from this branch) persists — not re-verified by `ls` this pass, carried as standing finding.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, Steps 0–4 per iteration 8, queue R1–R5 per iteration 9, HOLD + cumulative per iteration 10, 2.5/6 scorecard per iterations 11–16, C1–C5 per iteration 14, envelope per iteration 16).
- **Gate: no edit this pass (10th-iteration duty).** Assessment only — no third flip observed; iteration-15 2.5/6 scorecard carries. Iteration 20 must adopt a human-signed amendment allowing stacked-slice updates (with vendored evidence or exact cross-branch refs) or revert to `HOLD`.
- **Migration contribution (this pass, no code):** sequence health is green (linear, head 0029, v1 frozen) and rollback posture is trivially safe (nothing migrated). The only migration-sequence risks are documentary: C1 scope pick and C3 path string must land as R1 before any backfill slice is drafted.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→17.) Blocks any future supervisor `READY`.
2. Gate provenance: `498a4df` AND `b22b55b` both flipped the gate off-cycle. Deliberate stacked-slice strategy or accident? Loop rule needs a human-signed amendment at iteration 20. (Carry-over 11→17, confirmed pattern.)
3. Traceability (carry-over 15→17): vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate?
4. Agent-ready (carry-over 3→17, citable as C1): recursive `_norm` on inner proposal text vs outer-keys-only (`staging_validation.py:25-26` vs `:203-205` vs `:232` vs ADR-0010 §Decisión-2)? Must precede any backfill slice.
5. Agent-ready (carry-over 5→17): duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Assumed review-screen + pre-convert list.
6. Agent-ready (carry-over 7→17): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)?
7. Agent-ready (carry-over 14→17, citable as C3): `models.py:1875` docstring path — flat `*.schema.json` wording?
8. Evidence debt (carry-over 11→17): name the duplicated-cursor pair with current lines or drop the claim from the loop prompt.
9. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. At iteration 20, resolve the gate cleanly: adopt the two stacked slices verbatim WITH vendored evidence (or exact cross-branch refs + PR 113 URL) + a clean `updated-tech` base ref + answered picks, or revert to `HOLD` with the 2.5/6 scorecard. Do not let a third off-cycle flip accumulate.
2. Land the five R1 doc-precision patches (C1–C5 from iteration 14) as docs-only PR content; backfill wording depends on C1, `models.py` docstring on C3.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 `_norm`-scope pick + iteration-15 A5a/A5b split + iteration-16 timeout cite (`CHAT_TIMEOUT_SECONDS = 180`) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the triple-join cite table + idempotency cite table + A5a/A5b split + C1–C5 table + migration-sequence cites (`schemas/README.md:3-10` version rule; `staging_validation.py:16` SCHEMA_VERSION; head 0029; `check_migrations.py` OK).

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `staging_validation.py:16` version, `:20` keys, `:25-26` `_norm`, `:55-80` join read, `:139` id-optionality, `:189-208` hash with C1 caveat, `:211-238` report; `schemas/` flat, no `v2/`; migrations head 0029; `check_migrations.py` OK; iteration-15 staging cites carry: convert `views.py:2446-2475` positional `:2456`, template `tutor_import_detail.html:148` `item.index` vs `:157` `item.id`, fixed N+1 `models.py:1110-1139`, `clean()` `models.py:1874-1896` with C3 caveat), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iteration 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress) + iterations 5/7/8 (A1–A9 with A5a/A5b, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 18): re-check whether the working tree changed (Phase A–E committed, C1–C5 wording fixed, A5b template switched, head past 0029, `v2/` appeared) and whether the gate file moved a third time (a third off-cycle flip forces the rule-amendment question at iteration 20). If moved, verify the touched R/M/S step against the cumulative synthesis + iteration-5 matrix + this migration spine; if unchanged, record "no new evidence" and advance the rotating phase (suggested: report-surface pick or M4-export shape, the two least-specified open questions). Checkpoint duties next due at iteration 20 (cumulative deltas + gate review + docs-only PR); final synthesis at iteration 100 — neither is due now.
