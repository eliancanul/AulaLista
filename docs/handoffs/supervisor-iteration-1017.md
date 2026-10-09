# Supervisor iteration 1017 — schemas, migration sequence, and rollback safety

Iteration: 1017 | Phase focus: schemas, migration sequence, and rollback safety (Phase 7)
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–50, 56–1016)
`git status --short --branch` at pass time (live): `## supervisor/aulalista-docs...origin/supervisor/aulalista-docs`, modified `aulalista/settings.py`, `curriculum/models.py`, `curriculum/views.py`, `docs/DATABASE.md`, `docs/handoffs/supervisor-iteration-0440.md`, `-0590.md`, `-0810.md`, `-0820.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, deleted `health/templates/health/local_access.html`, untracked handoff backlog + `curriculum/schemas/` + `curriculum/services/` + `curriculum/staging_validation.py` + `scripts/check_migrations.py` + `tests/test_t54_staging_contracts.py` + `templates/health/local_access.html` + `.DS_Store` noise (same dirty set as 0831–1016, head `a6f1aa2` = 1010 checkpoint). Nothing discarded or reverted. Current worktree lines only.

Prior memory: `supervisor-iteration-1016.md` (FULL read at 1017) + `supervisor-iteration-1015.md` + `supervisor-iteration-1014.md` (carried) + `IMPLEMENTATION-GATE.md` HOLD notes + `supervisor-cumulative.md` spine/deltas (carried) + `CONTEXT.md`/`DESIGN.md`/`AGENTS.md` anchors (carried; DESIGN full re-read at 1011). `supervisor-final-10.md` written at 1000, not touched this pass.

## Scope

Phase 7 slice: schemas/migration/rollback-safety envelope under the renewed decade grant (1017–1019 carry on the live 1010 `gh` re-query; 1020 must go live). Spec only — nothing implemented, no issue created/edited/labeled, no code/root-doc/config touched. One write this pass: this handoff. No ADR change. `STATUS: HOLD` carries (gate re-check due at 1020, not this pass).

## Files inspected (fresh live evidence this pass)

- Fingerprint (`wc -l` fresh): views 2950 / models 2038 / settings 135 / staging 238 / services `results.py` 552 + `roadmap_cursor.py` 27 / `test_t54` 127 / `curriculum/roadmap.py` 242 — byte-identical to 0081–1016.
- AST (fresh `python3 ast.parse`): views 91 top-level funcs / models 5 funcs + 21 classes — byte-identical to 0018–1016.
- Schemas (fresh `ls` + `README.md` full re-read): flat — `README.md` + `topics` + `activities` + `llm_trace` (4 files, no `v2/`); version rule `README.md:7-10` (compatible stays v1, breaking copies three files to `v2/` + bumps `$id` + `SCHEMA_VERSION`) — unchanged.
- `$id` pin (fresh `sed topics.schema.json:1-12`): `https://aulalista.local/schemas/v1/topics.schema.json`, draft 2020-12 — v1-consistent, unchanged.
- Hash (fresh `sed staging_validation.py:189-208`): `activity_content_hash` SHA256 over `_norm(topic, subtema, proposal)` canonical, excludes `id/selected/added_by_topup/is_valid/issues` — unchanged.
- Zero relational tables (fresh `grep -rn "class Topic|Subtopic|ActivityProposal"` in `curriculum/*.py` → no output, `grep-exit:1`) — reconfirmed live.
- Migrations head 0029 (fresh `ls curriculum/migrations | tail -5`: `0027_teacher_curriculum_ownership`, `0028_grouproadmapprogress`, `0029_curriculumimportjob_progress_finished_at`) — carried, unchanged.
- Numstat (fresh `git diff --numstat` head): settings 12/2, models 44/4, views 127/681, DATABASE 7/0 (+ known handoff/root-doc lines) — byte-identical to the 0081 baseline.
- `git log --all --oneline -5` flip check clean at 1017 (head `a6f1aa2`, no off-cycle gate flip).
- `git diff --cached --name-only` → empty (no output) — nothing staged, consistent with non-checkpoint discipline.
- `gh` state carried from live 1010 (no re-query this pass per decade grant — no re-grade, no inference).

## Findings (observed facts vs hypotheses)

1. **No drift, 985th consecutive no-drift pass (observed).** Fingerprint + AST 91/5+21 + schemas-flat + v1 `$id` + hash window + zero-table `grep-exit:1` + head-0029 + numstat + clean log resolve to live tree unchanged (984 at 1016 + this pass). "No-drift" means the working-tree fingerprint is unchanged; pre-existing unstaged content deltas are distinguished, not conflated (fingerprint-vs-content caveat, 0699).
2. **Phase 7 slice resolves with no new movement (observed).** Migration spine M0→M4 positions unchanged: M0 precision patch still docs-only and unlanded; M1 additive tables still unwritten (zero tables live); M2 re-runnable JSON-authoritative backfill still pending; M3 flagged new-read still pending; M4 drop-JSON still a separate human-confirmed ticket, never bundled. Per-step rollback table carries (M1 reverse-migrate / M2 truncate+re-run JSON-authoritative / M3 flag-off / M4 export+runbook-gated; #57 gate green before each step; rule #58 `docs/DATABASE.md` in same PR on any model/pipeline step). The single #1 change (ADR-0010 relational staging with idempotency, #53+#98+#54 fused, #57 prerequisite) remains reference-only pending human Q16; no code authorization follows from this slice. Q6 (M4 artifact shape) / Q13 (matrix runner name) stay pre-R2 blockers per Q14, not pre-R1.
3. **Ranking posture unchanged, carry-rule applied (observed + carried).** Live R′-queue grades carry from 0249/1000/1010: #116 ~4/7 > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 (epic, not executable); none is 7/7. Retired old-lane grade (#98 0/7, iteration-49 six-`updatedAt` table) must never be cited as live. No `gh` call this pass — no re-grade, no inference beyond recording the carry.
   (Hypothesis: none — fingerprint/AST/schemas/`$id`/hash/zero-`grep`/head-0029/numstat/log pins are direct reads executed this pass; R′-grades/`gh` carried explicitly from the 1010 live probe.)

## Decisions (spec only)

- The single #1 architectural change stays **UNDER RE-SCOPING REVIEW pending human Q16: ADR-0010 relational staging with idempotency** as reference; live executable queue R′-1 #118 → R′-2 #116 (Q17-blocked) → R′-3 #119-isolated under epic #117. Unchanged by this pass.
- No ADR change this pass — ADR-0010 stands as reference; R2-before-seams / S1-LAST-fused-with-M3 / Q15-CONFIRMED carry.
- `STATUS: HOLD` carries (re-affirmed at 1010 with gate note; next re-check at 1020).

## Open questions

Carry-over 1–14 + Q16 (re-scope triage, HUMAN confirmation still due) + Q17 (narrowed-but-open; prototypes visual-a/b/c only on the live tree per 1015 re-verification — owner + delivery mechanism still unnamed) + PR #115 OPEN/unmerged (observe, never act) + accepted gaps (51–55, 0099, 0101–0102, 0166, 0284–0287, 0318, 0422–0424, 0428, 0459/0460, 0621–623, 0788-absent, 0961-absent, 0996/0997/0998-absent + 0999-claims-0998 contradiction) + Q11-narrowed (validators `settings.py:107` + `Secure` + `check --deploy` + owner/runbook, pre-institutional, never bundled into R′ — carried, not re-verified this pass: Phase 7 slice) + Q6/Q13 pre-R2 blockers (Q13 confirmed open via `.venv`-absent pattern at 1015, carried) + Q8 provenance correction (0898 dirty-tree-introduced; carries, not backfilled) + doc-precision corrections (no iteration-620 / iteration-720 gate notes exist — recorded at 0630/0740, not backfilled; re-checks covered by the 630/730 notes) + doc-precision D1/D2 from 1014 (DATABASE Deuda-1 pointer; implementation-current header stamp — record only, root-doc write scope unavailable).

## Ranked recommendations

1. Keep `STATUS: HOLD`; respect `paused` stop-work labels absolutely.
2. Human decision required (Q16): supersede-as-queue / preserve-as-reference for ADR-0010/R1–R5 vs R′-queue under #117.
3. Human/artifacts required (Q17): authoritative design-source commit for R′-2 (#116) onto the lane's base — absent on the live tree (re-verified at 1015, carried).
4. Human review/commit required: the uncommitted Phase A–E tree (no clean base ref nameable — the load-bearing blocker; staged set empty this pass, confirmed via `git diff --cached --name-only`).
5. Next pass (1018): Phase 8 god-files/service-seams slice under the decade carry (1018–1019 carry, 1020 must go live). No implementation.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current worktree lines (this pass: fingerprint views 2950 / models 2038 / settings 135 / staging 238, services 552/27, test_t54 127, `curriculum/roadmap.py` 242; AST 91 top-level views / 5+21 models; schemas flat 4 files no `v2/`, version rule `schemas/README.md:7-10`, v1 `$id` `topics.schema.json:2`; hash `staging_validation.py:189-208` `_norm` triple, editorial-state excluded; zero Topic/Subtopic/ActivityProposal tables via `grep-exit:1`; head 0029; numstat byte-identical to 0081 baseline; `git log` clean at `a6f1aa2`; staged set empty; `gh` carried from live 1010 — never unscoped `gh search` output; never the retired #98 0/7 grade as live — quote carried R′-grades #116 ~4/7 > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 epic, none 7/7).
- Preserve inviolable contracts + R2-before-seams + S1-LAST-fused-with-M3 + Q15-CONFIRMED clause; P1 pins the join boundary + P2 pins guard order, both green BEFORE any wiring touchpoint; Q8 fix is one-line accessor routing post-R2, never a standalone ticket; ambiguity surface renders overlap with exact-membership-first guard, never silent merge; migration discipline (M0 docs-only → M1 additive → M2 re-runnable JSON-authoritative → M3 flagged new-read → M4 separate human-confirmed ticket; Q6/Q13 pre-R2); Q11 hardening stays out of the staging lane with a named owner; no merge/commit/issue creation — draft text in Markdown only.

## Next move

Next supervisor pass (iteration 1018): Phase 8 god-files/service-seams/maintainability slice under the decade carry (1018–1019 carry, 1020 must go live). No implementation.

## Docs-only packaging (this pass: non-checkpoint — none)

Non-checkpoint pass: no staging, no commit, no push, no PR action. This handoff remains an unpackaged working-tree file for the 1020 checkpoint. Nothing was discarded or reverted.
