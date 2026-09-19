# Supervisor iteration 1014 — ADR and documentation contradiction reconciliation

Iteration: 1014 | Phase focus: ADR and documentation contradiction reconciliation (Phase 4)
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–50, 56–1013)
`git status --short --branch` at pass time (live): `## supervisor/aulalista-docs...origin/supervisor/aulalista-docs`, modified `aulalista/settings.py`, `curriculum/models.py`, `curriculum/views.py`, `docs/DATABASE.md`, `docs/handoffs/supervisor-iteration-0440.md`, `-0590.md`, `-0810.md`, `-0820.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, deleted `health/templates/health/local_access.html`, untracked handoff backlog + `curriculum/schemas/` + `curriculum/services/` + `curriculum/staging_validation.py` + `scripts/check_migrations.py` + `tests/test_t54_staging_contracts.py` + `templates/health/local_access.html` + `.DS_Store` noise (same dirty set as 0831–1013, head `a6f1aa2` = 1010 checkpoint). Nothing discarded or reverted. Current worktree lines only.

Prior memory: `supervisor-iteration-1013.md` (FULL read at 1014) + `supervisor-iteration-1012.md` + `supervisor-iteration-1011.md` (carried) + `IMPLEMENTATION-GATE.md` HOLD notes + `supervisor-cumulative.md` spine/deltas (carried) + `CONTEXT.md`/`DESIGN.md` anchors (carried; DESIGN full re-read at 1011) + ADR-0010 (FULL re-read at 1014). `supervisor-final-10.md` written at 1000, not touched this pass.

## Scope

Phase 4 slice: reconcile ADR-0010 wording against live tree + root-doc pointers under the renewed decade grant (1014–1019 carry on the live 1010 `gh` re-query; 1020 must go live). Spec only — nothing implemented, no issue created/edited/labeled, no code/root-doc/config touched. One write this pass: this handoff. No ADR change. `STATUS: HOLD` carries (gate re-check due at 1020, not this pass).

## Files inspected (fresh live evidence this pass)

- Fingerprint (`wc -l` fresh): views 2950 / models 2038 / settings 135 / staging 238 / services `results.py` 552 + `roadmap_cursor.py` 27 / `test_t54` 127 / `curriculum/roadmap.py` 242 — byte-identical to 0081–1013.
- AST (fresh `ast.parse`): views 91 top-level funcs / models 5 funcs + 21 classes — byte-identical to 0018–1013.
- ADR-0010 (full re-read at 1014): Estado "Aceptado (diseño; migración pendiente)", fusión #53+#98+#54, hash excludes `id/selected/added_by_topup/is_valid/issues`, `find_duplicate_groups` report-only `exact` vs `same_title_diff_content` AMBIGUO, migration double-write→backfill→new-read with #57 prerequisite, rule #58 DATABASE.md-in-same-PR.
- C1 three-way (fresh `sed :56-62` + `:76-77` + `:189-208`): baseline docstring `:56-62` exact `==` no-normalize == join code `:76-77` exact `==` on `topic_title`/`subtopic_title` ≠ hash `:189-208` (`_norm` topic/subtopic + `sort_keys`-only proposal canonicalization, no `_norm` recursion — iteration-64 nesting precision holds vs docstring `:190-196` "Normaliza ... topic, subtema y proposal canónico").
- Zero wiring (fresh `rg activity_content_hash|find_duplicate_groups` in views/models/services → no output, exit 1) + zero relational tables (fresh `rg "class (Topic|Subtopic|ActivityProposal)"` → no output, exit 1) — reconfirmed live.
- Write sites (fresh `rg topic_title` in views): `:2221-2222` (generate) + `:2383-2384` (topup), both title-keyed dict staging, no FK; prompt's `:2875-2876,:2959-2960` stale by ~650 lines.
- Overlap rule (fresh `sed test_t54:108-127`): `exact == [[0,1]]` ⊂ `same_title_diff_content == [[0,1,2]]` — overlap, never partition; surface must render overlap, guard checks exact-membership first.
- Candidate doc pointers (fresh `sed`): `docs/DATABASE.md:101-111` Deuda-1 says "revisar antes de escalar (nuevo ADR)"; `docs/implementation-current.md:1-7` header says Rama `main` + commit `d4fcb99`.
- Schemas (fresh `ls -R`): flat — `README.md` + 3 JSON, no `v2/`; migrations head 0029; prototypes visual-a/b/c only (Q17 OPEN re-verified live).
- Numstat (fresh `git diff --numstat` on 4 pins): settings 12/2, models 44/4, views 127/681, DATABASE 7/0 — byte-identical to the 0081 baseline.
- `git log --all --oneline -5` flip check clean at 1014 (head `a6f1aa2`, no off-cycle gate flip).
- `gh` state carried from live 1010 (no re-query this pass per decade grant — no re-grade, no inference).

## Findings (observed facts vs hypotheses)

1. **No drift, 982nd consecutive no-drift pass (observed).** Fingerprint + AST 91/5+21 + C1 three-way windows + zero-table/zero-callsite `rg` exits + write sites + overlap test window + schemas-flat + 0029 + prototypes-visual-only + numstat + clean log resolve to live tree unchanged (981 at 1013 + this pass). "No-drift" means the working-tree fingerprint is unchanged; pre-existing unstaged content deltas are distinguished, not conflated (fingerprint-vs-content caveat, 0699).
2. **Phase 4 reconciliation: two doc-precision items confirmed, zero load-bearing contradictions (observed).** (a) DATABASE Deuda-1 "(nuevo ADR)" pointer is stale in letter but resolved in substance: ADR-0010 IS the nuevo ADR (fusion #53+#98+#54, dated 2026-09-05) and Deuda-1's substance (title joins must go) agrees with ADR-0010's Context line 1. Fix is a one-line pointer update, docs-only, out of this lane's write scope (DATABASE.md is a root doc — safety boundary forbids; record only). (b) `implementation-current.md:5-6` header (Rama `main`, commit `d4fcb99`) disagrees with the live lane (`supervisor/aulalista-docs`, head `a6f1aa2`); header is a stale snapshot stamp, not an authority claim — record only, same write-scope bar. Neither item changes the #1-change posture, the R′-queue, or HOLD.
3. **ADR-0010 Step-1 status reconciled (observed).** ADR-0010 Context claims "Paso 1: schemas v1 + `staging_validation.py` + `clean()`" — live tree HAS schemas v1 flat + `staging_validation.py` (238 lines, untracked working-tree file) with hash/dedup semantics matching the ADR verbatim, but zero pipeline call sites and zero tables. Consistent with ADR header "Aceptado (diseño; migración pendiente)": reference implementation exists uncommitted, nothing wired, nothing migrated. No contradiction; the uncommitted-state blocker (no clean base ref) carries.
   (Hypothesis: none — fingerprint/AST/C1/zero-`rg`/write-sites/overlap-test/doc-pointer/schemas/0029/prototypes/numstat/log pins are direct reads executed this pass; R′-grades/`gh`/runner carried explicitly from the 1010 live probe.)

## Decisions (spec only)

- The single #1 architectural change stays **UNDER RE-SCOPING REVIEW pending human Q16: ADR-0010 relational staging with idempotency** as reference; live executable queue R′-1 #118 → R′-2 #116 (Q17-blocked) → R′-3 #119-isolated under epic #117. Unchanged by this pass.
- No ADR change this pass — ADR-0010 stands as reference; R2-before-seams / S1-LAST-fused-with-M3 / Q15-CONFIRMED carry.
- `STATUS: HOLD` carries (re-affirmed at 1010 with gate note; next re-check at 1020).

## Open questions

Carry-over 1–14 + Q16 (re-scope triage, HUMAN confirmation still due) + Q17 (narrowed-but-open; re-verified OPEN on the live tree at 1014 — `prototypes/` visual-a/b/c only; owner + delivery mechanism still unnamed) + PR #115 OPEN/unmerged (observe, never act) + accepted gaps (51–55, 0099, 0101–0102, 0166, 0284–0287, 0318, 0422–0424, 0428, 0459/0460, 0621–623, 0788-absent, 0961-absent, 0996/0997/0998-absent + 0999-claims-0998 contradiction) + Q11-narrowed (validators `settings.py:107` + `Secure` + `check --deploy` + owner/runbook, pre-institutional, never bundled into R′ — carried) + Q6/Q13 pre-R2 blockers (Q13 confirmed open via `.venv`-absent pattern, carried this pass) + Q8 provenance correction (0898 dirty-tree-introduced; carries, not backfilled) + doc-precision corrections (no iteration-620 / iteration-720 gate notes exist — recorded at 0630/0740, not backfilled; re-checks covered by the 630/730 notes) + NEW doc-precision items from this pass: (D1) DATABASE Deuda-1 "(nuevo ADR)" pointer → should name ADR-0010; (D2) `implementation-current.md:5-6` header stamp (`main`/`d4fcb99`) vs live lane — record only, both require root-doc write scope unavailable to this lane.

## Ranked recommendations

1. Keep `STATUS: HOLD`; respect `paused` stop-work labels absolutely.
2. Human decision required (Q16): supersede-as-queue / preserve-as-reference for ADR-0010/R1–R5 vs R′-queue under #117.
3. Human/artifacts required (Q17): authoritative design-source commit for R′-2 (#116) onto the lane's base — absent on the live tree (re-verified at 1014).
4. Human review/commit required: the uncommitted Phase A–E tree (no clean base ref nameable — the load-bearing blocker).
5. Next pass (1015): Phase 5 slice under the decade carry (1015–1019 carry, 1020 must go live). No implementation.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current worktree lines (this pass: fingerprint views 2950 / models 2038 / settings 135 / staging 238, services 552/27, test_t54 127, `curriculum/roadmap.py` 242; AST 91 top-level views / 5+21 models; ADR-0010 re-read 1014 "Aceptado (diseño; migración pendiente)"; C1 `:56-62` baseline + `:76-77` exact-join ≠ `:189-208` `_norm`+`sort_keys`-only with nesting precision vs `:190-196` docstring; write sites `views.py:2221-2222/:2383-2384` title-keyed, prompt cites stale; zero Topic/Subtopic/ActivityProposal tables + zero pipeline call sites via `rg` exit 1; overlap `test_t54:119-127` exact `[[0,1]]` ⊂ ambiguous `[[0,1,2]]`; doc-precision D1 (DATABASE Deuda-1 pointer) + D2 (implementation-current header) recorded, not edited; schemas flat 4 files no `v2/`; head 0029; prototypes visual-only (Q17 OPEN live); numstat byte-identical to 0081 baseline; `git log` clean at `a6f1aa2`; `gh` carried from live 1010 — never unscoped `gh search` output; never the retired #98 0/7 grade as live — quote carried R′-grades #116 ~4/7 > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 epic, none 7/7).
- Preserve inviolable contracts + R2-before-seams + S1-LAST-fused-with-M3 + Q15-CONFIRMED clause; P1 pins the join boundary + P2 pins guard order, both green BEFORE any wiring touchpoint; Q8 fix is one-line accessor routing post-R2, never a standalone ticket; ambiguity surface renders overlap with exact-membership-first guard, never silent merge; migration discipline (M0 docs-only → M1 additive → M2 re-runnable JSON-authoritative → M3 flagged new-read → M4 separate human-confirmed ticket; Q6/Q13 pre-R2); Q11 hardening stays out of the staging lane with a named owner; no merge/commit/issue creation — draft text in Markdown only.

## Next move

Next supervisor pass (iteration 1015): Phase 5 slice under the decade carry (1015–1019 carry, 1020 must go live). No implementation.

## Docs-only packaging (this pass: non-checkpoint — none)

Non-checkpoint pass: no staging, no commit, no push, no PR action. This handoff remains an unpackaged working-tree file for the 1020 checkpoint. Nothing was discarded or reverted.
