# Supervisor final checkpoint — cycle 1 (iterations 1–100)

Checkpoint written at iteration 100 per loop rules ("at every 100th iteration,
write/update `docs/handoffs/supervisor-final-{CYCLE}.md` with all observed
documentation/ADR changes, the ten strongest prompts and their outcomes, and the
methodology"). This is a checkpoint, not permission to implement fixes. Gate stays
`STATUS: HOLD` (2.5/6).

## 1. Observed documentation / ADR changes across cycle 1

No fix was implemented in this loop at any iteration — all outputs are specs,
ADRs, rankings, and handoffs. Observed doc-space changes (working tree +
packaged PRs):

- **ADRs:** 10 files (`0001`–`0010`) present at every census from iteration 61 on;
  no new ADR created in-loop. Governing decision unchanged end to end: ADR-0010
  relational staging with idempotency (fused #53 + #98 + #54 as ONE decision; #57
  prerequisite; #58 stale epic; #55/#56/#65 peripheral).
- **Docs-only PRs:** PR #112 (`supervisor/aulalista-docs` → `main`, handoffs
  0011–0050 + checkpoints 20/30/40/50) — observed MERGED upstream at iteration 60
  (merged outside this loop, contents on `main` still unverified from this branch).
  PR #115 (iteration-90 checkpoint: cumulative deltas 81–90 + prompt catalog + HOLD
  gate) — OPEN at iterations 90–100, unmerged per loop rules.
- **Uncommitted Phase A–E tree:** present and byte-identical at every pass
  (numstat settings 12/2, models 44/4, views 127/681, DATABASE 7/0,
  implementation-current 12/3, teacher-flow 7/1, local_access 0/25) — never
  discarded or reverted per loop rules; still awaiting human review/commit at
  iteration 100 (load-bearing blocker).
- **Handoff corpus:** 91 `supervisor-iteration-*.md` files on disk at iteration 100
  (0002–0050, 0056–0098, 0100; missing 0001/0004 + 0051–0055 + 0099 accepted as
  missing evidence under external numbering — no backfill). Plus `supervisor-cumulative.md`
  (spine 2→30, deltas 31–100), `supervisor-prompt-catalog.md` (ten phases, 0010–0100),
  `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6, notes at 20/30/40/50/60/70/80/90/100).
- **Key spec refinements landed in handoffs (not code):** C1 three-way + iteration-64
  proposal-nesting precision; C3-in-commit constraint; C5 narrowed to ADR-0006 `:29`;
  Q8 CLOSED (alias-with-missing-fallback, one-line R4 routing); Q11 narrowed
  (validators + `Secure` + `check --deploy`); Q14 answered (R1-may-land docs-only);
  Q15 CONFIRMED (dual-cited module identity + accepted-type clause); 7-slot rubric
  with blank-with-owner rule; draft-precision triple; six-`updatedAt` baseline
  (iteration 49) with carry-rule; per-file numstat baseline (iteration 81);
  A-matrix line-count pins (iteration 75/85/95).

## 2. Ten strongest prompts and their evidence-based outcomes

Ranked by durable effect on the loop's precision and safety (phase → outcome):

1. **Phase 10 checkpoint (0010)** — resolved the gate contradiction by rewriting the
   gate to HOLD with six explicit flip conditions. Every later checkpoint re-checks
   the scorecard live (2.5/6 at 20/30/40/50/60/70/80/90/100) instead of inheriting it.
2. **Phase 9 queue + draft quality (0019/0029/0039)** — set queue R1→R5, graded #98
   sole on-path at 0/7 on full-body re-read, then added the carry-rule (timestamps
   unchanged ⇒ no re-grade) and the blank-with-owner bar. Stopped all re-grading churn.
3. **Phase 8 god-files/seams (0038/0048/0078/0079)** — CLOSED Q8 as a one-line
   post-R2 accessor routing (not a standalone ticket), narrowed its blast radius,
   dual-cited both roadmap modules, and CONFIRMED Q15 with the seam-ticket clause.
4. **Phase 4 contradictions (0014/0034/0044/0064)** — built the C1–C5 doc-precision
   table, sharpened C1 to three-way (ADR == docstring ≠ code), added the C3-in-commit
   constraint and the iteration-64 nesting precision. This is the R1 docs-only payload.
5. **Phase 3 idempotency (0013/0033)** — identified the `_norm`-scope asymmetry (C1)
   and the overlap rule (ambiguous groups overlap exact pairs; guard checks
   exact-membership first). The two load-bearing semantic picks of the whole cycle.
6. **Phase 5 matrix (0015/0025/0035/0095)** — A1–A9 net with A5a/A5b split, P1/P2
   proving-test rows placed beside `test_t54:119-127`, and the Q13 runner gap named
   as a pre-R2 blocker. Every future ticket inherits this net.
7. **Phase 7 migration (0027/0037/0047)** — 0029 additive-nullable (rollback-trivial),
   per-step rollback pins (M1 reverse-migrate / M2 truncate+re-run JSON-authoritative /
   M3 flag-off / M4 export-gated separate ticket), #57 gate green. Made M4 safety explicit.
8. **Phase 6 envelope (0026/0046/0076)** — full envelope pins plus Q11 narrowed to
   validators + `Secure` + `check --deploy` + owner/runbook, kept institutional
   hardening out of the staging lane. Stopped scope-bundling.
9. **Phase 2 join cites (0012/0022/0032)** — triple-join cite table correcting the
   prompt's stale pre-shrink lines, then reframed C1 around the `:56-62` declared-intent
   baseline. Ended cite-rot for the loop's most-referenced fact.
10. **Phase 1 baseline (0021/0041/0071/0081)** — counter-methodology (name the
    `def`-counter), six-`updatedAt` live-query discipline, per-file numstat baseline
    with the measurement-order artifact explained. The loop's anti-drift instrumentation.

## 3. Methodology (how cycle 1 was run)

- **Graph-based dependency mapping:** #53 (Topic/Subtopic/ActivityProposal) + #98
  (idempotency) + #54 (`curriculum/schemas/`) treated as ONE architectural decision
  (ADR-0010); #57 migration anti-collision as prerequisite; #58 stale; #55/#56/#65
  peripheral. Doing any fused member without the others is rework by construction.
- **Phased rotating loops:** ten phases (join → idempotency → matrix → envelope →
  migration → seams → queue → checkpoint) with one phase focus per pass and a
  checkpoint every 10th iteration. Each phase re-verifies its pins against current
  code before concluding — no conclusion is carried without checking for drift.
- **Evidence matrix:** every pass cites exact `file:line` ranges, distinguishes
  observed facts from hypotheses, notes contradictions, and corrects stale prompt
  cites (`views.py:2875-2876,2959-2960`, `views.py:3504`, `models.py:1998`,
  `models.py:1125-1127` are pre-shrink numbers — never cited). Eighty-four
  consecutive no-drift passes at iteration 100 (fingerprint: views 2950 / models
  2038 / settings 135 / staging 238 / results 552 / roadmap_cursor 27 / test_t54
  127 / roadmap.py 242; head 0029; schemas flat; `check_migrations.py` OK).
- **Agentic supervision with HOLD-default gate:** `IMPLEMENTATION-GATE.md` defaults
  to `STATUS: HOLD` and flips only when all six conditions hold simultaneously
  (human-reviewed tree, narrowed slice, mandatory convert + test, non-self-referential
  base ref, open picks answered, zero blockers). Two off-cycle READY flips (iterations
  11/15) were reverted at checkpoint 20 and stand as the pattern the loop rule guards
  against. The parallel coding lane does nothing while the gate is `HOLD` or absent.
- **Docs-only packaging:** at 10-iteration checkpoints, only `docs/handoffs/` (+
  `docs/adr/` if changed) Markdown is staged via explicit `git add` (never
  `git add -A`), verified with `git diff --cached --name-only`, committed on
  `supervisor/aulalista-docs`, and pushed to a non-merged PR. Code, tests, settings,
  migrations, and root docs are never touched by this loop.

## 4. Cycle-2 handoff (what the next 100 iterations should do)

1. Unblock the load-bearing item: human review/commit of the Phase A–E tree
   (incl. C3 flat-path fix in-commit + settings env-triple safety check).
2. Land R1 (docs-only, Q6/Q13 may stay open), then name the Q13 runner and draft R2
   (mandatory convert-to-`activity_id` + P1/P2 green BEFORE wiring).
3. Keep HOLD until 6/6 holds simultaneously; keep periphery off the critical path;
   keep Q11 pre-institutional with a named owner.
4. Next checkpoint duties due at iteration 110; cycle-2 final synthesis
   (`supervisor-final-2.md`) due at iteration 200.
