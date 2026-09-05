# Supervisor prompt catalog — rotating phase prompts and evidence-based outcomes

Created at iteration-40 checkpoint per loop rules ("update `docs/handoffs/supervisor-prompt-catalog.md` with the ten rotating phase prompts, their iteration references, and evidence-based outcomes"). The supervisor runs this prompt repeatedly; each non-checkpoint pass takes one phase focus in rotation order, and every 10th iteration is a checkpoint (synthesis + cumulative deltas + gate review + docs-only PR). No fix is ever implemented in this loop — outputs are specs, ADRs, rankings, and handoffs only.

Stable spine for all phases: the single #1 architectural change is ADR-0010 relational staging with idempotency (fused #53 + #98 + #54 as ONE decision; #57 prerequisite; #58 stale epic; #55/#56/#65 peripheral). Inviolable contracts hold every pass (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage).

## The ten rotating phases

### Phase 1 — baseline architecture and domain contracts

- **Iterations:** 0011, 0021, 0031 (next: 0041).
- **Prompt:** re-verify CONTEXT.md / DESIGN.md vocabulary against current code; confirm authority boundaries, ownership, and pseudonymity resolve to live anchors; flag any spine contradiction.
- **Evidence-based outcomes:** 0011 established the off-cycle-flip pattern + N+1/secrets cites; 0021 adopted the counter-methodology (name the `def`-counter beside any count cite); 0031 concluded no re-modeling is needed — remaining work is documentary (R1 C1–C5) + human-gated. No spine contradiction found in any pass.

### Phase 2 — curriculum staging join and relational model

- **Iterations:** 0012, 0022, 0032 (next: 0042).
- **Prompt:** re-pin the title-keyed staging writes and the Topic/Subtopic/ActivityProposal relational target; correct stale prompt line cites with current file:line evidence.
- **Evidence-based outcomes:** 0012 produced the triple-join cite table (writes `views.py:2221-2222,2383-2384`; prompt's `:2875-2876,2959-2960` stale); 0022 split C1 into two questions (recursion scope + join-vs-hash agreement); 0032 reframed the pick around the `:56-62` declared-intent baseline (`_norm`-join vs exact-reads-with-`_norm`-report + P1 boundary test).

### Phase 3 — idempotency, deduplication, ambiguity policy

- **Iterations:** 0013, 0023, 0033 (next: 0043).
- **Prompt:** re-verify `activity_content_hash`, `find_duplicate_groups` (`exact` vs `same_title_diff_content`), the three wiring touchpoints, and the never-silent-merge rule.
- **Evidence-based outcomes:** 0013 identified the `_norm`-scope asymmetry (standing C1); 0023 set ambiguity-enforcement = report-surface pick + recorded the C1 draft pick; 0033 added the overlap rule (`test_t54:119-127` — ambiguous groups overlap exact pairs; guard checks exact-membership first).

### Phase 4 — ADR/documentation contradiction reconciliation

- **Iterations:** 0014, 0024, 0034 (next: 0044).
- **Prompt:** reconcile ADR-0010 against code/docstrings/schemas; maintain the C1–C5 doc-precision table with exact targets.
- **Evidence-based outcomes:** 0014 created the C1–C5 table (R1 docs-only patches); 0024 gave all five patches exact targets (C1 three-file, C2 `DATABASE.md:103-105`, C3 `models.py:1875`, C4 `implementation-current.md:3-6`, C5 ADR-0006 `:29`); 0034 sharpened C1 to three-way (ADR == docstring ≠ code — R1 must touch all three sites).

### Phase 5 — tests, evidence, acceptance matrix

- **Iterations:** 0015, 0025, 0035 (next: 0045).
- **Prompt:** re-verify the A1–A9 acceptance net (with A5a/A5b split) and the P1/P2 pending proving-test rows; name the runner given `pytest` is unrunnable in the supervisor env.
- **Evidence-based outcomes:** 0015 introduced the A5a/A5b split + scored the second off-cycle flip (2.5/6); 0025 sketched P1 (join-agreement) + P2 (same-title-separation), both green BEFORE wiring; 0035 placed both in `test_t54` beside `:119-127` (P1 boundary + P2 guard-order) and recorded the runner gap (Q13).

### Phase 6 — security, deployment, operational constraints

- **Iterations:** 0016, 0026, 0036 (next: 0046).
- **Prompt:** re-verify the iteration-6 envelope (LAN-only, staff-gated, sealed cookies, single-process SQLite, Ollama-only egress, no new egress); keep institutional hardening out of the staging lane with a named owner.
- **Evidence-based outcomes:** 0016 closed the Ollama timeout (`curriculum_import.py:23`, corrected at 20); 0026 recorded the pre-institutional hardening gap (dev-default secrets/DEBUG/hosts, empty validators, absent `Secure` flags — Q11/Q12); 0036 re-pinned all envelope cites (`views.py:125-142`, sealed cookies, `urls.py:228-229`) and confirmed the Phase A–E tree breaks none of them.

### Phase 7 — schemas, migration sequence, rollback safety

- **Iterations:** 0017, 0027, 0037 (next: 0047).
- **Prompt:** re-verify the M0→M4 spine, head position, `schemas/` version rule, `check_migrations.py`, and per-step rollback.
- **Evidence-based outcomes:** 0017 re-verified M0→M4 + rule #58; 0027 confirmed 0029 additive-nullable (rollback-trivial) + `$id` consistency; 0037 added per-step rollback pins (M1 reverse-migrate / M2 truncate+re-run JSON-authoritative / M3 flag-off / M4 export-gated) with M4 a separate human-confirmed ticket.

### Phase 8 — god-files, service seams, maintainability

- **Iterations:** 0018, 0028, 0038 (next: 0048).
- **Prompt:** re-measure `views.py`/`models.py` top-level counts, verify services/ exemplar status, maintain S-span pins, enforce R2-before-seams ordering.
- **Evidence-based outcomes:** 0018 mapped the god-files (views 91 defs / models 26→5 top-level by counter) + set S5→S4→S2 with S1-LAST-fused-with-M3; 0028 named the Q9 cursor pair (`views.py:1068` vs 7 service sites) + re-pinned S-spans; 0038 CLOSED Q8 (alias-with-missing-fallback; one-line accessor routing post-R2, not a standalone ticket).

### Phase 9 — ready-for-agent ranking and issue draft quality

- **Iterations:** 0019, 0029, 0039 (next: 0049).
- **Prompt:** re-grade the six-issue `ready-for-agent` set against the 7-slot rubric ONLY if a body changed (carry-rule otherwise); spend remaining budget on #98 draft precision.
- **Evidence-based outcomes:** 0019 graded #98 closest-but-not-executable + set queue R1→R5; 0029 live re-graded all six on full body re-read (#98 sole on-path at 0/7; `updatedAt 2026-08-28T02:37:01Z` datum); 0039 applied the carry-rule (timestamps unchanged, no re-grade) and added the draft-quality bar (blank-with-owner; unmarked blank = 0/7 ceiling) + opened Q14.

### Phase 10 — checkpoint: synthesis, gap analysis, next-loop handoff

- **Iterations:** 0010, 0020, 0030, 0040 (next: 0050; final synthesis at 0100).
- **Prompt:** write the synthesis handoff, extend cumulative with deltas only, review the gate (flip only if all six conditions hold), update this catalog, and package docs-only Markdown into the pushed, non-merged PR.
- **Evidence-based outcomes:** 0010 resolved the gate contradiction (rewrote gate to HOLD with six flip conditions); 0020 reverted the off-cycle READY flips to HOLD (2.5/6) + pushed handoffs 0011–0019 into PR 112; 0030 settled Q8 (upgrades ride as handoff Markdown, never created issues) + pushed 0021–0030; 0040 answered Q14 (R1-may-land docs-only; Q6/Q13 pre-R2 blockers) + created this catalog + pushes 0031–0040 into PR 112. Gate HOLD re-affirmed at every checkpoint with live re-check, never by inertia.
