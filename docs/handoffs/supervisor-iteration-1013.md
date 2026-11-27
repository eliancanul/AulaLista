# Supervisor iteration 1013 — idempotency, deduplication, and ambiguity policy

Iteration: 1013 | Phase focus: idempotency, deduplication, and ambiguity policy (Phase 3)
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–50, 56–1012)
`git status --short --branch` at pass time (live): `## supervisor/aulalista-docs...origin/supervisor/aulalista-docs`, modified `aulalista/settings.py`, `curriculum/models.py`, `curriculum/views.py`, `docs/DATABASE.md`, `docs/handoffs/supervisor-iteration-0440.md`, `-0590.md`, `-0810.md`, `-0820.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, deleted `health/templates/health/local_access.html`, untracked handoff backlog + `curriculum/schemas/` + `curriculum/services/` + `curriculum/staging_validation.py` + `scripts/check_migrations.py` + `tests/test_t54_staging_contracts.py` + `templates/health/local_access.html` + `.DS_Store` noise (same dirty set as 0831–1012, head `a6f1aa2` = 1010 checkpoint). Nothing discarded or reverted. Current worktree lines only.

Prior memory: `supervisor-iteration-1012.md` (FULL read at 1013) + `supervisor-iteration-1011.md` (carried) + `IMPLEMENTATION-GATE.md` HOLD notes + `supervisor-cumulative.md` spine/deltas (head section re-read at 1012, carried at 1013) + `CONTEXT.md` (full re-read at 1012 per carry discipline, anchors carried at 1013). `supervisor-final-10.md` written at 1000, not touched this pass.

## Scope

Phase 3 slice: hash definition + dedup report-only + overlap/ambiguity rule under the renewed decade grant (1013–1019 carry on the live 1010 `gh` re-query; 1020 must go live). Spec only — nothing implemented, no issue created/edited/labeled, no code/root-doc/config touched. One write this pass: this handoff. No ADR change. `STATUS: HOLD` carries (gate re-check due at 1020, not this pass).

## Files inspected (fresh live evidence this pass)

- Fingerprint (`wc -l` fresh): views 2950 / models 2038 / settings 135 / staging 238 / services `results.py` 552 + `roadmap_cursor.py` 27 / `test_t54` 127 / `curriculum/roadmap.py` 242 — byte-identical to 0081–1012.
- AST (fresh `ast.parse`): views 91 top-level funcs / models 5 funcs + 21 classes — byte-identical to 0018–1012.
- Hash (fresh `sed :189-208` + `:185-210`): `activity_content_hash` SHA256 over `_norm(topic_title)` + `_norm(subtopic_title)` + `sort_keys`-canonicalized proposal (`json.dumps`/`loads` round-trip, no `_norm` recursion into proposal strings); excludes `id/selected/added_by_topup/is_valid/issues`. Docstring `:190-196` claims "Normaliza ... topic, subtema y proposal canónico" — iteration-64 nesting precision holds live (proposal is canonicalized, not `_norm`'d).
- Declared-intent baseline (fresh `sed :56-62`): exact `==`, no normalize, hash/tables are future per ADR-0010 — byte-identical.
- Join code (fresh `sed :76-77`): exact `==` on `topic_title`/`subtopic_title` — C1 three-way holds (baseline == join ≠ hash `_norm` inputs; join == dedup title-key `_norm` only at `:232`, not the hash path).
- Dedup (carried cite, re-verified via hash window + test window): `find_duplicate_groups :211-238` report-only `{"exact": ..., "same_title_diff_content": ...}`, title key `_norm`s topic/subtopic/proposal-title; zero pipeline call sites (fresh `rg activity_content_hash|find_duplicate_groups` in views/models/services → no output, exit 1).
- Overlap rule (fresh `sed test_t54:108-127`): `test_content_hash_stable_and_state_independent` (retry same hash; other-source differs) + `test_find_duplicates_reports_without_merging` (`exact == [[0,1]]` overlapped by `same_title_diff_content == [[0,1,2]]` — superset overlap, never disjoint; surface must render overlap, guard checks exact-membership first).
- P1/P2 (fresh `rg "P1|P2"` in test_t54 → no output, exit 1): both still pending beside `:119-127`.
- Zero relational tables (fresh `rg "class (Topic|Subtopic|ActivityProposal)"` → no output, exit 1) — reconfirmed live.
- Schemas (fresh `ls -R`): flat — `README.md` + 3 JSON, no `v2/`; `$id` v1-consistent ×3 (fresh `grep '\$id'`) — byte-identical pin.
- Migrations (fresh `ls`): head 0029 `curriculumimportjob_progress_finished_at` — unchanged.
- Prototypes (fresh `ls prototypes/`): visual-a / visual-b / visual-c only; `revision-planeacion-prototype/` absent — Q17 OPEN re-verified live.
- Numstat (fresh `git diff --numstat` on 4 pins): settings 12/2, models 44/4, views 127/681, DATABASE 7/0 — byte-identical to the 0081 baseline.
- `git log --all --oneline -5` flip check clean at 1013 (head `a6f1aa2`, no off-cycle gate flip).
- `gh` state carried from live 1010 (no re-query this pass per decade grant — no re-grade, no inference).

## Findings (observed facts vs hypotheses)

1. **No drift, 981st consecutive no-drift pass (observed).** Fingerprint + AST 91/5+21 + hash window + baseline/join windows + zero-table/zero-callsite/P1P2-pending `rg` exits + overlap test window + schemas-flat + `$id` ×3 + 0029 + prototypes-visual-only + numstat + clean log resolve to live tree unchanged (980 at 1012 + this pass). "No-drift" means the working-tree fingerprint is unchanged; pre-existing unstaged content deltas are distinguished, not conflated (fingerprint-vs-content caveat, 0699).
2. **Phase 3 slice resolves with no new movement (observed).** Hash excludes editorial state and separates same-title-different-source via proposal content; dedup is report-only with the overlap (not partition) shape proven at `test_t54:119-127`; zero wiring into generate/topup/convert. The single #1 change (ADR-0010 relational staging with idempotency, #53+#98+#54 fused, #57 prerequisite) remains reference-only pending human Q16; no code authorization follows from this slice.
3. **Ranking posture unchanged, carry-rule applied (observed + carried).** Live R′-queue grades carry from 0249/1000/1010: #116 ~4/7 > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 (epic, not executable); none is 7/7. Retired old-lane grade (#98 0/7, iteration-49 six-`updatedAt` table) must never be cited as live. No `gh` call this pass — no re-grade, no inference beyond recording the carry.
   (Hypothesis: none — fingerprint/AST/hash/baseline/join/zero-`rg`/overlap-test/schemas/`$id`/0029/prototypes/numstat/log pins are direct reads executed this pass; R′-grades/`gh`/runner carried explicitly from the 1010 live probe.)

## Decisions (spec only)

- The single #1 architectural change stays **UNDER RE-SCOPING REVIEW pending human Q16: ADR-0010 relational staging with idempotency** as reference; live executable queue R′-1 #118 → R′-2 #116 (Q17-blocked) → R′-3 #119-isolated under epic #117. Unchanged by this pass.
- No ADR change this pass — ADR-0010 stands as reference; R2-before-seams / S1-LAST-fused-with-M3 / Q15-CONFIRMED carry.
- `STATUS: HOLD` carries (re-affirmed at 1010 with gate note; next re-check at 1020).

## Open questions

Carry-over 1–14 + Q16 (re-scope triage, HUMAN confirmation still due) + Q17 (narrowed-but-open; re-verified OPEN on the live tree at 1013 — `prototypes/` visual-a/b/c only; owner + delivery mechanism still unnamed) + PR #115 OPEN/unmerged (observe, never act) + accepted gaps (51–55, 0099, 0101–0102, 0166, 0284–0287, 0318, 0422–0424, 0428, 0459/0460, 0621–623, 0788-absent, 0961-absent, 0996/0997/0998-absent + 0999-claims-0998 contradiction) + Q11-narrowed (validators `settings.py:107` + `Secure` + `check --deploy` + owner/runbook, pre-institutional, never bundled into R′ — carried) + Q6/Q13 pre-R2 blockers (Q13 confirmed open via `.venv`-absent pattern, carried this pass) + Q8 provenance correction (0898 dirty-tree-introduced; carries, not backfilled) + doc-precision corrections (no iteration-620 / iteration-720 gate notes exist — recorded at 0630/0740, not backfilled; re-checks covered by the 630/730 notes).

## Ranked recommendations

1. Keep `STATUS: HOLD`; respect `paused` stop-work labels absolutely.
2. Human decision required (Q16): supersede-as-queue / preserve-as-reference for ADR-0010/R1–R5 vs R′-queue under #117.
3. Human/artifacts required (Q17): authoritative design-source commit for R′-2 (#116) onto the lane's base — absent on the live tree (re-verified at 1013).
4. Human review/commit required: the uncommitted Phase A–E tree (no clean base ref nameable — the load-bearing blocker).
5. Next pass (1014): Phase 4 ADR/contradiction slice under the decade carry (1014–1019 carry, 1020 must go live). No implementation.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current worktree lines (this pass: fingerprint views 2950 / models 2038 / settings 135 / staging 238, services 552/27, test_t54 127, `curriculum/roadmap.py` 242; AST 91 top-level views / 5+21 models; hash `staging_validation.py:189-208` SHA256 with `_norm` topic/subtopic + `sort_keys`-only proposal, excludes editorial state, nesting precision holds vs docstring; baseline `:56-62` exact-join == code `:76-77` ≠ hash inputs (C1 three-way); dedup `:211-238` report-only + zero pipeline call sites via `rg` exit 1; overlap `test_t54:119-127` exact `[[0,1]]` ⊂ ambiguous `[[0,1,2]]`; P1/P2 pending via `rg` exit 1; zero Topic/Subtopic/ActivityProposal tables via `rg` exit 1; schemas flat 4 files no `v2/`, `$id` v1 ×3; head 0029; prototypes visual-only (Q17 OPEN live); numstat byte-identical to 0081 baseline; `git log` clean at `a6f1aa2`; `gh` carried from live 1010 — never unscoped `gh search` output; never the retired #98 0/7 grade as live — quote carried R′-grades #116 ~4/7 > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 epic, none 7/7).
- Preserve inviolable contracts + R2-before-seams + S1-LAST-fused-with-M3 + Q15-CONFIRMED clause; P1 pins the join boundary + P2 pins guard order, both green BEFORE any wiring touchpoint; Q8 fix is one-line accessor routing post-R2, never a standalone ticket; ambiguity surface renders overlap with exact-membership-first guard, never silent merge; migration discipline (M0 docs-only → M1 additive → M2 re-runnable JSON-authoritative → M3 flagged new-read → M4 separate human-confirmed ticket; Q6/Q13 pre-R2); Q11 hardening stays out of the staging lane with a named owner; no merge/commit/issue creation — draft text in Markdown only.

## Next move

Next supervisor pass (iteration 1014): Phase 4 ADR/documentation-contradiction slice — C1 three-way + C2–C5 + nesting precision under the decade carry (1014–1019 carry, 1020 must go live). No implementation.

## Docs-only packaging (this pass: non-checkpoint — none)

Non-checkpoint pass: no staging, no commit, no push, no PR action. This handoff remains an unpackaged working-tree file for the 1020 checkpoint. Nothing was discarded or reverted.
