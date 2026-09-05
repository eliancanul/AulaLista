# Supervisor cumulative synthesis — iterations 2–30 (deltas only)

Checkpoint written at iteration 10, extended at iterations 20 and 30. Prior handoffs are the working memory; this file records only the durable synthesis and what changed per pass. No `supervisor-iteration-0001.md` / `-0004.md` exist (numbering arrives externally); no fix has been implemented in this loop — all outputs are specs, ADRs, rankings, and handoffs.

## Stable spine (agreed 2→10, re-verified each pass against current code)

- **#1 architectural change:** ADR-0010 relational staging with idempotency — fused #53 (Topic/Subtopic/ActivityProposal) + #98 (idempotency) + #54 (`curriculum/schemas/`) as ONE decision. Doing any one without the others is rework. #57 migration anti-collision is the prerequisite; #58 is a stale epic body; #55/#56/#65 are peripheral.
- **Inviolable contracts:** only human EditorialReviewer publishes; only teacher activates ClassroomSession; AI proposes only; sessions read immutable SHA256 PublishedPackageSnapshot; DemoPackage synthetic with zero pedagogical claims.
- **Tree fingerprint (unchanged 2→10):** `views.py` 2950 / `models.py` 2038 / `settings.py` 135 / `staging_validation.py` 238 / `services/results.py` 552 / `services/roadmap_cursor.py` 27 / `test_t54` 127 lines; migrations head 0029; `check_migrations.py` green; `schemas/` flat (4 files, no `v2/`); hash/dedup unwired (zero pipeline call sites); convert positional (`views.py:2456`); remove resolves via `_activity_id` (`views.py:2317`).
- **Loop-prompt corrections (apply to future prompts):** "sole ready-for-agent path" is true only as "sole `ready-for-agent` issue **on the staging critical path**" (six open `ready-for-agent`: #95/#97/#98/#103/#104/#107); prompt line cites (`views.py:2875-2876,2959-2960`, `views.py:3504`, `models.py:1998`, `models.py:1125-1127`) are stale pre-shrink numbers — cite current lines only.

## Deltas per iteration

- **0002 — staging join + relational model.** Pinned title-based staging joins and the Topic/Subtopic/ActivityProposal shape; the relational target everything else builds on.
- **0003 — idempotency/ambiguity.** Specified `activity_content_hash` + `find_duplicate_groups` (`exact` vs `same_title_diff_content`), the three legal wiring touchpoints (post-generate append guard, pre-topup count, pre-convert list), always report + human confirm, never silent merge.
- **0005 — tests/evidence matrix A1–A9.** The acceptance net (t15/t16/t19/t20/t22/t24 + `test_t54`) every later ticket must keep green; rows A2+A3+A4+A5+A8 gate the staging queue.
- **0006 — security/deployment envelope.** LAN-only HTTP, staff-gated pipeline, sealed device cookies, single-process SQLite, no new egress, `media/`-in-tarball — preserved by every ticket, changed by none.
- **0007 — schemas/migration M0→M4 + rollback.** M0 precision patch (docs-only) → M1 additive tables → M2 re-runnable backfill → M3 flagged new-read → M4 drop-JSON (separate human-confirmed ticket with named export artifact + restore runbook, never bundled). Per-step rollback; rule #58 (`docs/DATABASE.md` in same PR on any model/pipeline step); #57 gate green before each step.
- **0008 — god-files/service seams S1–S5, Steps 0–4.** Measured map (`tutor_sessions` 104, `ClassroomSession` 470, etc.); extraction order S5 → S4 → S2, S1 LAST fused with M3 (never before — double churn); S3 frozen as the delegate-shape exemplar; `models.py` behavior-only extraction (fields are migration-pinned).
- **0009 — ready-for-agent queue + draft quality.** Queue R1 (M0 precision, docs-only) → R2 (mandatory convert-to-`activity_id` switch, tested) → R3 (M1→M3 slice, M4 excluded) → R4 (S5→S4→S2) → R5 (periphery stays out); draft ticket text for the R2+R3 slice (Markdown only, nothing created); graded #98 (closest, still not executable) / #53 / #54 / #57 / #58; recorded the gate contradiction for iteration 10.
- **0010 — checkpoint: gate to HOLD + cumulative.** No new tree evidence; sharpened convert cite (`views.py:2446-2475`, positional `:2456`); resolved Finding 6 by rewriting `IMPLEMENTATION-GATE.md` to `STATUS: HOLD` with six explicit flip conditions; packaged docs-only Markdown into a pushed, non-merged PR (see `supervisor-iteration-0010.md` §PR record).

## Deltas iterations 11–20 (no new tree evidence in any pass; all counts byte-identical, head 0029, `schemas/` flat)

- **0011 — baseline architecture and domain contracts.** Re-verified CONTEXT/DESIGN vocabulary against code; first off-cycle gate flip observed (`498a4df` rewrote HOLD→READY ~2 min after the checkpoint); prompt cites corrected (N+1 at `models.py:1110-1135` FIXED via `in_bulk`; cursor-duplication unconfirmed; secrets confirmed as dev-defaults `settings.py:8-21`). Scorecard 2/6.
- **0012 — curriculum staging join and relational model.** Triple-join cite table: title-keyed staging writes at `views.py:2221-2222,2383-2384` (prompt's `:2875-2876,2959-2960` stale).
- **0013 — idempotency, deduplication, ambiguity.** `_norm`-scope asymmetry identified (`staging_validation.py:25-26` vs `:203-205` vs ADR-0010 §Decisión-2) — became standing C1.
- **0014 — ADR/documentation contradiction reconciliation.** C1–C5 doc-precision table (R1 docs-only patches); C1 `_norm` scope, C3 `models.py:1875` docstring path.
- **0015 — tests, evidence, acceptance matrix.** A1–A9 re-verified with A5a/A5b split (A5a convert-identity tested slice vs A5b template `item.index→item.id` slice); second off-cycle flip (`b22b55b`) scored against the six conditions → 2.5/6; gate traceability gap recorded (on-disk gate cites `coding-41560047f83c.md`, unreachable from this branch).
- **0016 — security, deployment, operational constraints.** Envelope re-verified; Ollama timeout closed out (`CHAT_TIMEOUT_SECONDS = 180` — corrected at iteration 20 to `curriculum/curriculum_import.py:23`).
- **0017 — schemas, migration sequence, rollback safety.** Migration spine M0→M4 re-verified (head 0029, `schemas/README.md:3-10` version rule, `check_migrations.py` OK); C1/C3 carried.
- **0018 — god-files, service seams, maintainability.** `views.py` 91 defs / `models.py` 26 defs; services/ is a two-module exemplar (`results.py` 552 + `roadmap_cursor.py` 27, imported `views.py:74-75`); S1-LAST-fused-with-M3 re-confirmed with current cites (`:2420` grouped, `:2446` convert, `:2006` call site, `:2022` reuse).
- **0019 — ready-for-agent ranking and issue draft quality.** Six `ready-for-agent` (#95/#97/#98/#103/#104/#107), #98 sole on-path but 0/7 executable slots under the new 7-slot draft rubric (ADR, allowed paths, out-of-scope, invariants, named tests, migration/rollback, base ref).
- **0020 — checkpoint: gate back to HOLD + cumulative.** No new tree evidence; no third flip; PR 112 verified OPEN; cite correction (`CHAT_TIMEOUT_SECONDS` → `curriculum/curriculum_import.py:23`); gate reverted to `STATUS: HOLD` with 2.5/6 scorecard; nine pending handoffs (0011–0019) staged and pushed with this checkpoint into PR 112 (docs-only, unmerged).

## Deltas iterations 21–30 (no new tree evidence in any pass; all counts byte-identical, head 0029, `schemas/` flat, `check_migrations.py` OK, 42 test files)

- **0021 — baseline architecture and domain contracts.** Re-verified CONTEXT/DESIGN vocabulary against code; adopted counter-methodology (name the `def`-counter beside any count cite — `grep -c` 92/66 vs AST 91 top-level); cite discipline re-affirmed.
- **0022 — curriculum staging join and relational model.** C1 sharpened to TWO questions: (a) `_norm` recursion scope inside the hash, (b) join-vs-hash agreement (exact `==` at `staging_validation.py:76-77` vs normalized hash inputs). Draft pick: `_norm`-join both sides, or document exact-join as intentional with a proving test.
- **0023 — idempotency, deduplication, ambiguity policy.** Ambiguity-enforcement = report-surface pick (recommended review-screen + pre-convert list, `llm_log` audit copy); C1 draft pick recorded (`_norm`-join + outer-keys-only hash) for iteration-30 R1 packaging.
- **0024 — ADR/documentation contradiction reconciliation.** Five R1 doc-precision patches with exact targets: C1 three-file (`adr/0010` §Decisión-2, `staging_validation.py:192` docstring, `schemas/README.md`), C2 (`DATABASE.md:103-105`), C3 (`models.py:1875`), C4 (`implementation-current.md:3-6`), C5 (ADR-0006 `:29` + `teacher-flow.md:110-120`).
- **0025 — tests, evidence, acceptance matrix.** Two pending proving-test rows sketched: P1 join-agreement + P2 same-title-separation, both in `test_t54` (or successor), both green BEFORE any of the three wiring touchpoints (post-generate guard, pre-topup count, pre-convert list).
- **0026 — security, deployment, operational constraints.** Envelope re-verified (LAN-only, staff-gated, sealed cookies 12h, single-process SQLite, Ollama-only egress 180s, no new egress); pre-institutional hardening gap recorded (dev-default secrets/DEBUG/`*`-hosts, empty password validators, absent cookie/SECURE flags; checklist owner still open as Q12).
- **0027 — schemas, migration sequence, rollback safety.** C3 closed by direct re-read (confirmed open); 0029 verified additive-nullable (rollback-trivial); `$id` consistency verified; only migration-sequence risks left are documentary (C1 + C3 as R1).
- **0028 — god-files, service seams, maintainability.** Cursor census names the Q9 pair: direct read `views.py:1068` vs 7 service sites (`:2505…:2866`) — one 50-line read of `:1046-1094` still pending; S5/S4/S2 spans re-pinned to current lines; R2-before-seams ordering re-affirmed (`:2428`/`:2456` index cites).
- **0029 — ready-for-agent ranking and issue draft quality.** Six-issue set live re-graded (#95/#97/#98/#103/#104/#107, #98 sole on-path); #98 full-body re-read re-graded 0/7; fused labels verified correctly absent; A5b (`tutor_import_detail.html:148/:157`) + timeout (`curriculum_import.py:23`) cites re-pinned.
- **0030 — checkpoint: synthesis, gap analysis, HOLD re-affirmed.** Ten-pass no-drift verdict; gate scorecard live re-checked (2.5/6, HOLD with cause); Q8 settled (#98 upgrade + R1 precision ride as handoff Markdown in the docs-only PR, never as created issues); root docs re-read with no spine contradictions (C2/C4 staleness already R1 items); ten pending handoffs (0021–0030) staged and pushed with this checkpoint into PR 112 (docs-only, unmerged).

## Ranked recommendations (standing, in order)

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously (human-reviewed tree, narrowed slice, mandatory convert + test, non-self-referential base ref, open questions 2–4 answered, zero blockers).
2. Consume staging work strictly R1→R2→R3(M4 excluded)→R4; each step names ADR-0010/matrices, exact allowed paths, rollback.
3. Upgrade #98 with the iteration-9 §Draft body before any coding lane starts; #58 epic body updated docs-only to the fused order.
4. Keep periphery off the staging path; no physical-LAN or concurrent-write claims until T13/physical runs exist.
5. Refresh the loop prompt (qualified #98 sentence, current cites) to stop paying re-derivation cost every pass.

## Open questions (standing, iterations 2→20)

1. Human: review/commit the uncommitted Phase A–E tree? (2→20; blocks any future READY.)
2. `_norm` recursion pick before any backfill slice? (3→20; citable as C1.)
3. Duplicate-report surface pick? (5→20; assumed review-screen + pre-convert list.)
4. M4 JSON-export artifact shape? (7→20.)
5. Loop rule: human-signed amendment for stacked-slice off-cycle gate updates, or HOLD-only-outside-checkpoints? (11→20; two unamended flips is a pattern.)
6. Gate traceability: vendor `coding-41560047f83c.md` onto the supervisor branch or record exact cross-branch refs? (15→20.)
7. `models.py:1875` docstring path — flat `*.schema.json` wording? (14→20; citable as C3.)
8. Evidence debt: name the duplicated-cursor pair with current lines or drop the claim. (11→20.)
9. Seam-spec: pin S5/S4/S2 to current def spans or retire S-numbers? (18→20.)
10. Counter source for missing 0001/0004? (5→20; proposal: accept gaps.)

## Methodology note (for the iteration-100 final)

Graph-based dependency mapping (fused #53/#98/#54 + #57 prerequisite + periphery exclusion), phased rotating loops (join → idempotency → matrix → envelope → migration → seams → queue → checkpoint), per-pass evidence matrix with file:line cites distinguishing observed facts from hypotheses, and agentic supervision with a HOLD-default implementation gate. Each 10th iteration writes deltas-only cumulative + gate review + docs-only PR; the 100th writes `supervisor-final-{CYCLE}.md` with documentation/ADR changes, ten strongest prompts and outcomes, and methodology.
