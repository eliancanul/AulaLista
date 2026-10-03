# Supervisor final checkpoint — cycle 4 (iterations 301–400)

Checkpoint written at iteration 400 per loop rules ("at every 100th iteration,
write/update `docs/handoffs/supervisor-final-{CYCLE}.md` with all observed
documentation/ADR changes, the ten strongest prompts and their outcomes, and the
methodology"). This is a checkpoint, not permission to implement fixes. Gate stays
`STATUS: HOLD` (2.5/6 + new-scope draft bar).

## 1. Observed documentation / ADR changes across cycle 4

No fix was implemented in this loop at any iteration — all outputs are specs,
ADRs, rankings, and handoffs. Observed doc-space changes (working tree +
packaged PRs):

- **ADRs:** 10 files (`0001`–`0010`) present at every census in cycle 4; no new
  ADR created in-loop. Governing decision unchanged end to end: ADR-0010
  relational staging with idempotency (fused #53 + #98 + #54 as ONE decision; #57
  prerequisite; #58 stale epic; #55/#56/#65 peripheral) preserved as reference,
  with R1–R5 retired as the execution vehicle and the R′-queue (#118 → #116 →
  #119-isolated under epic #117) as the live queue — all pending human Q16
  confirmation, still due at iteration 400 (now 150+ passes old).
- **Docs-only PRs:** PR #115 (`supervisor/aulalista-docs` → `main`) OPEN for the
  entire cycle — created at the iteration-90 checkpoint, updated by checkpoint
  pushes at 310/320/330/340/350/360/370/380/390/400, unmerged per loop rules.
  PR #112 stays MERGED upstream (observed at iteration 60; contents on `main`
  still unverified from this branch at iteration 400).
- **Uncommitted Phase A–E tree:** present and byte-identical at every pass
  (numstat settings 12/2, models 44/4, views 127/681, DATABASE 7/0,
  implementation-current 12/3, teacher-flow 7/1, local_access 0/25) — never
  discarded or reverted per loop rules; still awaiting human review/commit at
  iteration 400 (load-bearing blocker, now 379 consecutive no-drift passes old).
- **Handoff corpus:** 391–400 has no number gap (eighteenth gap-free decade
  overall); cycle-4 gaps stand as accepted missing evidence (0318 only, same
  disposition as 51–55/0099/0101–0102/0166/0284–0287 — no backfill; decades
  301–310, 321–330, 331–340, 341–350, 351–360, 361–370, 371–380, 381–390,
  391–400 all gap-free, only 311–320 broken by 0318 with Phase 8 contributing no
  delta). Plus `supervisor-cumulative.md` (spine 2→30, deltas 31–400),
  `supervisor-prompt-catalog.md` (ten phases, 0010–0400),
  `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6, notes at
  20/30/…/390/400 plus the 0250 rewrite), and this file.
- **Spec refinements landed in handoffs (not code):** none semantic in cycle 4 —
  the per-ticket draft-gap table (0259) + falsifiable close conditions (0299) +
  Q17-narrowing (0290, prototype off-branch at
  `codex/ui-institucional@95d1ab8`) all carried unchanged through 0391–0400;
  C1 three-way + nesting precision, C3-in-commit, C5-narrowed, Q8/Q15
  closed-confirmed, Q11-narrowed, Q14-answered, and the draft-precision triple
  all carried unchanged, which is itself the finding: the spec is stable, only
  the human-gated tree blocks it. Cycle 4's contribution is durability proof —
  100 more iterations (10 checkpoints, every-pass LIVE `gh` in all 99 observed
  passes) with zero drift and zero semantic churn.

## 2. Ten strongest prompts and their evidence-based outcomes

Ranked by durable effect on the loop's precision and safety (phase → outcome):

1. **Phase 10 checkpoint (0400, this pass)** — closed cycle 4 with deltas 391–400
   (eighteenth gap-free decade), HOLD re-affirmed at the 379th consecutive
   no-drift pass, and this file. Proved the 100-iteration checkpoint format
   survives a second full post-re-scope cycle without losing the evidence chain.
2. **Phase 10 checkpoint (0250, carried all cycle)** — the gate rewrite around
   epic #117 + the R′-queue stayed the governing text through all ten cycle-4
   checkpoints (0310–0400 notes re-affirm by reference). No cycle-4 pass found a
   reason to re-cut it.
3. **Phase 9 fresh grading (0249, carried all cycle)** — the R′-grades (#116 ~4/7
   > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 epic, none 7/7) timestamp-verified
   LIVE at every cycle-4 checkpoint (0340–0400 re-queries byte-identical) and
   never re-graded per the carry-rule. The entire cycle executes inside this
   decision.
4. **Phase 9 gap table + close conditions (0259/0299, carried all cycle)** —
   per-ticket draft gaps with falsifiable close conditions stayed actionable
   drafting checklists for 100 more iterations; no gap closed in cycle 4 (Q16 +
   Q17 + dirty-tree blockers all still open), which the table states honestly
   instead of grading upward.
5. **Phase 8 seam pins (0358/0368/0378/0388/0398)** — AST re-parsed fresh each
   decade (91 top-level views / 5+21 models), Q8 census re-pinned (import `:74`,
   divergent `:1068`, 7 service sites `:2505/:2579/:2599/:2634/:2770/:2807/:2866`),
   R2 pins + `roadmap.py` 242 + zero Topic tables + zero pipeline wiring
   re-verified. The seam slice stays specified but correctly post-R2.
6. **Phase 4 contradiction watch (0354/0364/0374/0384/0394)** — C1 three-way +
   nesting precision + C2–C5 reconfirmed at current lines every decade; R1 must
   quote `:56-62` and touch all three C1 wording sites. The R1 docs-only payload
   stayed green for 100 more iterations without edits.
7. **Phase 7 migration watch (0357/0367/0377/0387/0397)** — 0029
   additive-nullable + rollback pin (`migrate curriculum 0028`) + `$id` v1 ×3 +
   no `v2/` + C1/C3-in-commit re-verified; `check_migrations.py` OK every pass.
   The rollback story never degraded.
8. **Phase 2 join watch (0352/0362/0372/0382/0392)** — write sites `:2221/:2383`
   never drifted; exact-join vs `_norm`-hash asymmetry carried as specified
   documentary work, never silently re-picked.
9. **Phase 5 matrix watch (0355/0365/0375/0385/0395)** — A-counts byte-identical
   to the 0075 pins, P1/P2 still pending beside `test_t54:119-127`, Q13 pre-R2
   held, run-unverified stated honestly (`.venv` absent every pass).
10. **Phase 6 envelope watch (0356/0366/0376/0386/0396)** — staff gate, sealed 12h
    cookies without `Secure`, Ollama-only egress 180s, dev-default triple
    re-verified; Q11-narrowed with no owner, never bundled into R′-1/R′-2.

Honorable mentions: Phase 1 baseline watch (CONTEXT/DESIGN/AGENTS anchors live,
numstat baseline stable since 0081, CONTEXT/AGENTS heads re-read at 0400);
Phase 3 idempotency watch (hash `:189-208` + dedup `:211-238` report-only +
overlap rule, zero pipeline call sites, every pass); the 0318-gap handling
(recorded as accepted missing evidence at 0319–400 without backfill and without
breaking the decade discipline — 9 of 10 cycle-4 decades gap-free).

## 3. Methodology (how cycle 4 was run)

- **Graph-based dependency mapping:** fused #53/#98/#54 as ONE decision (ADR-0010);
  #57 prerequisite; #58 stale; #55/#56/#65 peripheral — unchanged all cycle. The
  second layer from 0248 (old lane retired as vehicle but kept as reference per
  Q16; R′-queue #118 → #116 → #119-isolated under epic #117 as the live queue)
  held without re-cut: no pass in cycle 4 found a reason to re-cut either layer.
- **Phased rotating loops:** ten phases with one focus per pass, checkpoint every
  10th iteration. Cycle 4 ran the every-pass LIVE `gh` rule end to end (the 0248
  regime — live re-query beats carried state) in all 99 observed passes
  (0391–0399 + 0400 checkpoint; 0318 accepted as missing evidence, Phase 8 no
  delta that decade). Full re-reads at each pass's own focus + header re-reads
  of the decade at each checkpoint, recorded explicitly, never silently.
- **Evidence matrix:** every pass cites exact `file:line` ranges, distinguishes
  observed facts from hypotheses, notes contradictions, and never cites the
  prompt's stale pre-shrink numbers. Cycle-4 fingerprint locked: views 2950 /
  models 2038 / settings 135 / staging 238 / results 552 / roadmap_cursor 27 /
  roadmap 242 / test_t54 127; numstat +209/−716 byte-identical since 0081; head
  0029; schemas flat; `check_migrations.py` OK; ready-set 04:18:34–37Z ×4 +
  paused ×25 byte-identical at every live re-query; AST 91 / 5+21; 7 service
  sites.
- **Agentic supervision with HOLD-default gate:** `STATUS: HOLD` re-affirmed at
  every checkpoint with a live scorecard re-check (2.5/6 + new-scope draft bar at
  310/320/330/340/350/360/370/380/390/400 — blockers non-none, no clean base
  ref), never by inertia. No off-cycle flip observed in cycle 4 (`git log --all
  -8` clean at every checkpoint). The parallel coding lane did nothing all cycle.
- **Docs-only packaging:** at each 10-iteration checkpoint, only `docs/handoffs/`
  Markdown staged via explicit `git add` (never `git add -A`), verified with
  `git diff --cached --name-only`, committed on `supervisor/aulalista-docs`, and
  pushed to non-merged PR #115 (plus a follow-up record commit per the 200/290
  precedent). Code, tests, settings, migrations, and root docs never touched by
  this loop.

## 4. Cycle-5 handoff (what the next 100 iterations should do)

1. Unblock the load-bearing items, in order: human review/commit of the Phase A–E
   tree (incl. C3 flat-path fix in-commit + settings env-triple safety check) →
   Q16 confirmation (supersede-as-queue / preserve-as-reference) → Q17 owner +
   delivery of `codex/ui-institucional@95d1ab8` onto the lane's base (or explicit
   out-of-inputs with #116 re-scoped). All three are now 110–150+ passes old;
   they are the only things standing between the spec and a draftable ticket.
2. Draft R′-1 #118 first (closest to draftable: needs exact allowed
   interpreter/verification paths + named test files + Q13 runner); R′-2 #116
   stays blocked on Q17; R′-3 #119 stays isolation-only. Never cite any R′ draft
   as authorized work while the gate is HOLD.
3. Keep HOLD until all flip conditions hold simultaneously; keep periphery off the
   critical path; keep Q11 pre-institutional with a named owner.
4. Next checkpoint duties due at iteration 410; cycle-5 final synthesis
   (`supervisor-final-5.md`) due at iteration 500.

(End of file.)
