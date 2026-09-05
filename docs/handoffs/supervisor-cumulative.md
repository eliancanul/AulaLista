# Supervisor cumulative synthesis — iterations 2–10 (deltas only)

Checkpoint written at iteration 10. Prior handoffs are the working memory; this file records only the durable synthesis and what changed per pass. No `supervisor-iteration-0001.md` / `-0004.md` exist (numbering arrives externally); no fix has been implemented in this loop — all outputs are specs, ADRs, rankings, and handoffs.

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

## Ranked recommendations (standing, in order)

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously (human-reviewed tree, narrowed slice, mandatory convert + test, non-self-referential base ref, open questions 2–4 answered, zero blockers).
2. Consume staging work strictly R1→R2→R3(M4 excluded)→R4; each step names ADR-0010/matrices, exact allowed paths, rollback.
3. Upgrade #98 with the iteration-9 §Draft body before any coding lane starts; #58 epic body updated docs-only to the fused order.
4. Keep periphery off the staging path; no physical-LAN or concurrent-write claims until T13/physical runs exist.
5. Refresh the loop prompt (qualified #98 sentence, current cites) to stop paying re-derivation cost every pass.

## Open questions (standing)

1. Human: review/commit the uncommitted Phase A–E tree? (2→10; blocks any future READY.)
2. `_norm` recursion pick before any backfill slice? (3→10.)
3. Duplicate-report surface pick? (5→10; assumed review-screen + pre-convert list.)
4. M4 JSON-export artifact shape? (7→10.)
5. Counter source for missing 0001/0004? (5→10; proposal: accept gaps.)

## Methodology note (for the iteration-100 final)

Graph-based dependency mapping (fused #53/#98/#54 + #57 prerequisite + periphery exclusion), phased rotating loops (join → idempotency → matrix → envelope → migration → seams → queue → checkpoint), per-pass evidence matrix with file:line cites distinguishing observed facts from hypotheses, and agentic supervision with a HOLD-default implementation gate. Each 10th iteration writes deltas-only cumulative + gate review + docs-only PR; the 100th writes `supervisor-final-{CYCLE}.md` with documentation/ADR changes, ten strongest prompts and outcomes, and methodology.
