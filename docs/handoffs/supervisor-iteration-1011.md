# Supervisor iteration 1011 — baseline architecture and domain contracts

Iteration: 1011 | Phase focus: baseline architecture and domain contracts (Phase 1)
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–50, 56–1010)
`git status --short --branch` at pass time (live): `## supervisor/aulalista-docs...origin/supervisor/aulalista-docs`, modified `aulalista/settings.py`, `curriculum/models.py`, `curriculum/views.py`, `docs/DATABASE.md`, `docs/handoffs/supervisor-iteration-0440.md`, `-0590.md`, `-0810.md`, `-0820.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, deleted `health/templates/health/local_access.html`, untracked handoff backlog + `curriculum/schemas/` + `curriculum/services/` + `curriculum/staging_validation.py` + `scripts/check_migrations.py` + `tests/test_t54_staging_contracts.py` + `templates/health/local_access.html` + `.DS_Store` noise (same dirty set as 0831–1010, head `a6f1aa2` = 1010 checkpoint). Nothing discarded or reverted. Current worktree lines only.

Prior memory: `supervisor-iteration-1010.md` (FULL read at 1011) + `IMPLEMENTATION-GATE.md` HOLD notes + `supervisor-prompt-catalog.md` Phase 1 addenda + `CONTEXT.md`/`DESIGN.md` re-reads (DESIGN full re-read at 1011; CONTEXT anchors live-verified this pass, full re-read carried from 1002 per carry-once discipline). `supervisor-final-10.md` written at 1000, not touched this pass.

## Scope

Phase 1 slice: CONTEXT/DESIGN domain vocabulary vs live code anchors (EditorialReviewer gate, DemoPackage flag, snapshot spine, `in_bulk` fix, teacher-gated pipeline) under the renewed decade grant (1011–1019 carry on the live 1010 `gh` re-query; 1020 must go live). Spec only — nothing implemented, no issue created/edited/labeled, no code/root-doc/config touched. One write this pass: this handoff. No ADR change. `STATUS: HOLD` carries (gate re-check due at 1020, not this pass).

## Files inspected (fresh live evidence this pass)

- Fingerprint (`wc -l` fresh): views 2950 / models 2038 / settings 135 / staging 238 / services `results.py` 552 + `roadmap_cursor.py` 27 / `test_t54` 127 / `curriculum/roadmap.py` 242 — byte-identical to 0081–1010.
- AST (fresh `ast.parse`): views 91 top-level funcs / models 5 funcs + 21 classes — byte-identical to 0018–1010.
- CONTEXT anchors (fresh `grep`): `EDITORIAL_REVIEWER_GROUP_NAME models.py:36` + human gate `:306` (`:1990` ensure-group) / `is_demo models.py:137` / `in_bulk models.py:1130` (prompt's `models.py:1125-1127` stale by ~5 lines) / `teacher_required views.py:125` + gated sites `:517/:599/:675/:687` — all resolve, no spine contradiction.
- DESIGN (full re-read at 1011): direction C (Aula directa), inviolable authority boundary (AI proposes only; EditorialReviewer publishes; teacher activates), DemoPackage synthetic-no-claims, deterministic results off PublishedPackageSnapshot — consistent with CONTEXT anchors above; contract is for future surfaces, changes no routes/models/templates.
- Schemas (fresh `ls -R` + `grep $id`): `curriculum/schemas/` flat — `README.md` + 3 JSON (`activities`, `llm_trace`, `topics`), no `v2/`, no `v1/` subdir; `$id` v1-consistent ×3 (`https://aulalista.local/schemas/v1/*.schema.json`) — byte-identical pin.
- Migrations (fresh `ls`): head 0029 `curriculumimportjob_progress_finished_at` — unchanged.
- Q8 window (fresh `sed :1066-1072`): divergent inline read (`GroupRoadmapProgress.for_session` + `ordered_activities` + manual `next(... if row["id"] == current_id ...)`) vs 7 service sites — census byte-identical to 0088–1010 (import `views.py:74`, sites `:2505/:2579/:2599/:2634/:2770/:2807/:2866` carried from 1010).
- Q17 (fresh `ls prototypes/`): visual-a / visual-b / visual-c only; `revision-planeacion-prototype/` absent — OPEN re-verified live.
- Numstat (fresh `git diff --numstat`): settings 12/2, models 44/4, views 127/681, DATABASE 7/0 — byte-identical to the 0081 baseline.
- `git log --all --oneline -5` flip check clean at 1011 (head `a6f1aa2`, no off-cycle gate flip).
- `gh` state carried from live 1010 (no re-query this pass per decade grant — no re-grade, no inference).

## Findings (observed facts vs hypotheses)

1. **No drift, 979th consecutive no-drift pass (observed).** Fingerprint + AST 91/5+21 + CONTEXT anchors (`:36/:137/:306/:1130`, `views.py:125`) + DESIGN re-read + schemas-flat + `$id` ×3 + 0029 + Q8 window + prototypes-visual-only + numstat + clean log resolve to live tree unchanged (978 at 1010 + this pass). "No-drift" means the working-tree fingerprint is unchanged; pre-existing unstaged content deltas are distinguished, not conflated (fingerprint-vs-content caveat, 0699).
2. **Baseline slice resolves with no new movement (observed).** CONTEXT vocabulary (School/Director/PlatformAdministrator/TeacherAssignment/CoordinationAction/ClassroomRoadmapSummary/CurriculumPackage/PublishedPackageSnapshot/EditorialReviewer/DemoPackage/TeacherWorkflow/CurriculumProgress/PublishedRoadmapSnapshot/StudentRoadmapProgress/GroupRoadmapProgress/ActivityDraft/ActivityReview/ClassroomSession/ClassroomGroup/LocalDeviceQueue/StudentTurn/DeviceAssignment/practice-result trio) maps to live anchors with no contradiction; DESIGN direction-C + authority boundary + synthetic-demo + deterministic-results clauses agree with the same anchors. Remaining work is documentary (R1 C1–C5) + human-gated, not a re-modeling of the domain.
3. **Ranking posture unchanged, carry-rule applied (observed + carried).** Live R′-queue grades carry from 0249/1000/1010: #116 ~4/7 > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 (epic, not executable); none is 7/7. Retired old-lane grade (#98 0/7, iteration-49 six-`updatedAt` table) must never be cited as live. No `gh` call this pass — no re-grade, no inference beyond recording the carry.
   (Hypothesis: none — fingerprint/AST/anchors/DESIGN/schemas/`$id`/0029/Q8-window/prototypes/numstat/log pins are direct reads executed this pass; R′-grades/`gh`/runner carried explicitly from the 1010 live probe.)

## Decisions (spec only)

- The single #1 architectural change stays **UNDER RE-SCOPING REVIEW pending human Q16: ADR-0010 relational staging with idempotency** as reference; live executable queue R′-1 #118 → R′-2 #116 (Q17-blocked) → R′-3 #119-isolated under epic #117. Unchanged by this pass.
- No ADR change this pass — ADR-0010 stands as reference; R2-before-seams / S1-LAST-fused-with-M3 / Q15-CONFIRMED carry.
- `STATUS: HOLD` carries (re-affirmed at 1010 with gate note; next re-check at 1020).

## Open questions

Carry-over 1–14 + Q16 (re-scope triage, HUMAN confirmation still due) + Q17 (narrowed-but-open; re-verified OPEN on the live tree at 1011 — `prototypes/` visual-a/b/c only; owner + delivery mechanism still unnamed) + PR #115 OPEN/unmerged (observe, never act) + accepted gaps (51–55, 0099, 0101–0102, 0166, 0284–0287, 0318, 0422–0424, 0428, 0459/0460, 0621–623, 0788-absent, 0961-absent, 0996/0997/0998-absent + 0999-claims-0998 contradiction) + Q11-narrowed (validators `settings.py:107` + `Secure` + `check --deploy` + owner/runbook, pre-institutional, never bundled into R′ — carried) + Q6/Q13 pre-R2 blockers (Q13 confirmed open via `.venv`-absent pattern, carried this pass) + Q8 provenance correction (0898 dirty-tree-introduced; carries, not backfilled) + doc-precision corrections (no iteration-620 / iteration-720 gate notes exist — recorded at 0630/0740, not backfilled; re-checks covered by the 630/730 notes).

## Ranked recommendations

1. Keep `STATUS: HOLD`; respect `paused` stop-work labels absolutely.
2. Human decision required (Q16): supersede-as-queue / preserve-as-reference for ADR-0010/R1–R5 vs R′-queue under #117.
3. Human/artifacts required (Q17): authoritative design-source commit for R′-2 (#116) onto the lane's base — absent on the live tree (re-verified at 1011).
4. Human review/commit required: the uncommitted Phase A–E tree (no clean base ref nameable — the load-bearing blocker).
5. Next pass (1012): Phase 2 staging-join slice under the decade carry (1012–1019 carry, 1020 must go live). No implementation.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current worktree lines (this pass: fingerprint views 2950 / models 2038 / settings 135 / staging 238, services 552/27, test_t54 127, `curriculum/roadmap.py` 242; AST 91 top-level views / 5+21 models; CONTEXT anchors `models.py:36/:137/:306/:1130` + `views.py:125` gate sites; DESIGN direction-C + authority boundary re-read 1011; Q8 divergent `:1066-1072` window + 7 service sites carried from 1010; schemas flat 4 files no `v2/`, `$id` v1 ×3; head 0029; prototypes visual-only (Q17 OPEN live); numstat byte-identical to 0081 baseline; `git log` clean at `a6f1aa2`; `gh` carried from live 1010 — never unscoped `gh search` output; never the retired #98 0/7 grade as live — quote carried R′-grades #116 ~4/7 > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 epic, none 7/7).
- Preserve inviolable contracts + R2-before-seams + S1-LAST-fused-with-M3 + Q15-CONFIRMED clause; P1 pins the join boundary + P2 pins guard order, both green BEFORE any wiring touchpoint; Q8 fix is one-line accessor routing post-R2, never a standalone ticket; ambiguity surface renders overlap with exact-membership-first guard, never silent merge; migration discipline (M0 docs-only → M1 additive → M2 re-runnable JSON-authoritative → M3 flagged new-read → M4 separate human-confirmed ticket; Q6/Q13 pre-R2); Q11 hardening stays out of the staging lane with a named owner; no merge/commit/issue creation — draft text in Markdown only.

## Next move

Next supervisor pass (iteration 1012): Phase 2 curriculum-staging-join slice — write sites + C1 three-way + nesting precision under the decade carry (1012–1019 carry, 1020 must go live). No implementation.

## Docs-only packaging (this pass: non-checkpoint — none)

Non-checkpoint pass: no staging, no commit, no push, no PR action. This handoff remains an unpackaged working-tree file for the 1020 checkpoint. Nothing was discarded or reverted.
