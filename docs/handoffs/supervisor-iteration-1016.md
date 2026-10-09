# Supervisor iteration 1016 — security, deployment, and operational constraints

Iteration: 1016 | Phase focus: security, deployment, and operational constraints (Phase 6)
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–50, 56–1015)
`git status --short --branch` at pass time (live): `## supervisor/aulalista-docs...origin/supervisor/aulalista-docs`, modified `aulalista/settings.py`, `curriculum/models.py`, `curriculum/views.py`, `docs/DATABASE.md`, `docs/handoffs/supervisor-iteration-0440.md`, `-0590.md`, `-0810.md`, `-0820.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, deleted `health/templates/health/local_access.html`, untracked handoff backlog + `curriculum/schemas/` + `curriculum/services/` + `curriculum/staging_validation.py` + `scripts/check_migrations.py` + `tests/test_t54_staging_contracts.py` + `templates/health/local_access.html` + `.DS_Store` noise (same dirty set as 0831–1015, head `a6f1aa2` = 1010 checkpoint). Nothing discarded or reverted. Current worktree lines only.

Prior memory: `supervisor-iteration-1015.md` (FULL read at 1016) + `supervisor-iteration-1014.md` + `supervisor-iteration-1013.md` (carried) + `IMPLEMENTATION-GATE.md` HOLD notes + `supervisor-cumulative.md` spine/deltas (carried) + `CONTEXT.md`/`DESIGN.md`/`AGENTS.md` anchors (carried; DESIGN full re-read at 1011). `supervisor-final-10.md` written at 1000, not touched this pass.

## Scope

Phase 6 slice: security/deployment/operational-constraints envelope under the renewed decade grant (1016–1019 carry on the live 1010 `gh` re-query; 1020 must go live). Spec only — nothing implemented, no issue created/edited/labeled, no code/root-doc/config touched. One write this pass: this handoff. No ADR change. `STATUS: HOLD` carries (gate re-check due at 1020, not this pass).

## Files inspected (fresh live evidence this pass)

- Fingerprint (`wc -l` fresh): views 2950 / models 2038 / settings 135 / staging 238 / services `results.py` 552 + `roadmap_cursor.py` 27 / `test_t54` 127 / `curriculum/roadmap.py` 242 — byte-identical to 0081–1015.
- AST (fresh `ast.parse`): views 91 top-level funcs / models 5 funcs + 21 classes — byte-identical to 0018–1015.
- Envelope gate (fresh `sed views:107-145`): `_safe_teacher_next` allow-list validation + `teacher_required` staff/active double-gate — unchanged.
- Secrets triple (fresh `sed settings:1-30`): dev-default `SECRET_KEY` + `DEBUG` env-true-default + `ALLOWED_HOSTS *` default, with in-file WARNING comment (`AULALISTA_SECRET_KEY` + `AULALISTA_DEBUG=False` + explicit hosts for any deploy) — unchanged, still pre-institutional.
- Validators (fresh `sed settings:100-115`): `AUTH_PASSWORD_VALIDATORS = []` — unchanged, Q11 item open.
- Cookies (fresh `rg`): sealed 12h TTLs (`LOCAL_SESSION_TTL :100-103`, `_set_sealed_cookie :173` + call sites `:214/:307`); `rg secure=` → no output, exit 1 — no `Secure` flag anywhere, unchanged.
- Deploy surface (fresh `sed urls:220-235` tail): DEBUG-only `staticfiles_urlpatterns()` block — unchanged.
- Egress (fresh `rg requests|urllib|httpx|Ollama|OLLAMA|CHAT_TIMEOUT` in views/models/services → single hit `views.py:1847` display-string `pipeline.llm_model()/ollama_url()`; import-staging pins `curriculum_import.py:21-23` `localhost:11434` / `qwen2.5:14b` / 180s via env-scoped `settings.py:134-135`) — Ollama-only, unchanged.
- Zero relational tables (fresh `rg "class (Topic|Subtopic|ActivityProposal)"` in curriculum → no output, exit 1) — reconfirmed live.
- Schemas (fresh `ls`): flat — `README.md` + 3 JSON, no `v2/`; migrations head 0029 (carried).
- Numstat (fresh `git diff --numstat`): settings 12/2, models 44/4, views 127/681, DATABASE 7/0 (+ known handoff/root-doc lines) — byte-identical to the 0081 baseline.
- `git log --all --oneline -5` flip check clean at 1016 (head `a6f1aa2`, no off-cycle gate flip).
- `git diff --cached --name-only` → empty (exit 0, no output) — nothing staged, consistent with non-checkpoint discipline.
- `gh` state carried from live 1010 (no re-query this pass per decade grant — no re-grade, no inference).

## Findings (observed facts vs hypotheses)

1. **No drift, 984th consecutive no-drift pass (observed).** Fingerprint + AST 91/5+21 + gate/secret/validator/cookie/urls/egress windows + `secure=`-absent + zero-table `rg` exits + schemas-flat + numstat + clean log resolve to live tree unchanged (983 at 1015 + this pass). "No-drift" means the working-tree fingerprint is unchanged; pre-existing unstaged content deltas are distinguished, not conflated (fingerprint-vs-content caveat, 0699).
2. **Phase 6 slice resolves with no new movement (observed).** Envelope positions unchanged: staff-gated pipeline, sealed-but-not-`Secure` 12h cookies, DEBUG-only static block, single-process SQLite posture, Ollama-only egress, dev-default secrets triple + empty validators. The single #1 change (ADR-0010 relational staging with idempotency, #53+#98+#54 fused, #57 prerequisite) remains reference-only pending human Q16; no code authorization follows from this slice. Q11 hardening (validators + `Secure` + `check --deploy` + owner/runbook) stays pre-institutional, named-owner-open, and explicitly out of the staging lane.
3. **Ranking posture unchanged, carry-rule applied (observed + carried).** Live R′-queue grades carry from 0249/1000/1010: #116 ~4/7 > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 (epic, not executable); none is 7/7. Retired old-lane grade (#98 0/7, iteration-49 six-`updatedAt` table) must never be cited as live. No `gh` call this pass — no re-grade, no inference beyond recording the carry.
   (Hypothesis: none — fingerprint/AST/gate/secret/validator/cookie/urls/egress/zero-`rg`/schemas/numstat/log pins are direct reads executed this pass; R′-grades/`gh` carried explicitly from the 1010 live probe.)

## Decisions (spec only)

- The single #1 architectural change stays **UNDER RE-SCOPING REVIEW pending human Q16: ADR-0010 relational staging with idempotency** as reference; live executable queue R′-1 #118 → R′-2 #116 (Q17-blocked) → R′-3 #119-isolated under epic #117. Unchanged by this pass.
- No ADR change this pass — ADR-0010 stands as reference; R2-before-seams / S1-LAST-fused-with-M3 / Q15-CONFIRMED carry.
- `STATUS: HOLD` carries (re-affirmed at 1010 with gate note; next re-check at 1020).

## Open questions

Carry-over 1–14 + Q16 (re-scope triage, HUMAN confirmation still due) + Q17 (narrowed-but-open; prototypes visual-a/b/c only on the live tree per 1015 re-verification — owner + delivery mechanism still unnamed) + PR #115 OPEN/unmerged (observe, never act) + accepted gaps (51–55, 0099, 0101–0102, 0166, 0284–0287, 0318, 0422–0424, 0428, 0459/0460, 0621–623, 0788-absent, 0961-absent, 0996/0997/0998-absent + 0999-claims-0998 contradiction) + Q11-narrowed (validators `settings.py:107` + `Secure` + `check --deploy` + owner/runbook, pre-institutional, never bundled into R′ — re-verified this pass: validators empty live, `secure=` absent live) + Q6/Q13 pre-R2 blockers (Q13 confirmed open via `.venv`-absent pattern at 1015, carried) + Q8 provenance correction (0898 dirty-tree-introduced; carries, not backfilled) + doc-precision corrections (no iteration-620 / iteration-720 gate notes exist — recorded at 0630/0740, not backfilled; re-checks covered by the 630/730 notes) + doc-precision D1/D2 from 1014 (DATABASE Deuda-1 pointer; implementation-current header stamp — record only, root-doc write scope unavailable).

## Ranked recommendations

1. Keep `STATUS: HOLD`; respect `paused` stop-work labels absolutely.
2. Human decision required (Q16): supersede-as-queue / preserve-as-reference for ADR-0010/R1–R5 vs R′-queue under #117.
3. Human/artifacts required (Q17): authoritative design-source commit for R′-2 (#116) onto the lane's base — absent on the live tree (re-verified at 1015, carried).
4. Human review/commit required: the uncommitted Phase A–E tree (no clean base ref nameable — the load-bearing blocker; staged set empty this pass, confirmed via `git diff --cached --name-only`).
5. Next pass (1017): Phase 7 schemas/migration slice under the decade carry (1017–1019 carry, 1020 must go live). No implementation.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current worktree lines (this pass: fingerprint views 2950 / models 2038 / settings 135 / staging 238, services 552/27, test_t54 127, `curriculum/roadmap.py` 242; AST 91 top-level views / 5+21 models; gate `views.py:107-145` allow-list + staff/active; secrets triple `settings.py:7-23` with WARNING comment; validators `[] settings.py:107`; cookies sealed 12h `:100-103/:173/:214/:307`, `secure=` absent via `rg` exit 1; DEBUG-only `urls.py:228-229` shape; egress single display-string hit `views.py:1847`, import pins `curriculum_import.py:21-23` via `settings.py:134-135`; zero Topic/Subtopic/ActivityProposal tables via `rg` exit 1; schemas flat 4 files no `v2/`; head 0029; numstat byte-identical to 0081 baseline; `git log` clean at `a6f1aa2`; staged set empty; `gh` carried from live 1010 — never unscoped `gh search` output; never the retired #98 0/7 grade as live — quote carried R′-grades #116 ~4/7 > #118 ~3.5–4/7 > #119 ~3.5/7 > #117 ~3.5/7 epic, none 7/7).
- Preserve inviolable contracts + R2-before-seams + S1-LAST-fused-with-M3 + Q15-CONFIRMED clause; P1 pins the join boundary + P2 pins guard order, both green BEFORE any wiring touchpoint; Q8 fix is one-line accessor routing post-R2, never a standalone ticket; ambiguity surface renders overlap with exact-membership-first guard, never silent merge; migration discipline (M0 docs-only → M1 additive → M2 re-runnable JSON-authoritative → M3 flagged new-read → M4 separate human-confirmed ticket; Q6/Q13 pre-R2); Q11 hardening stays out of the staging lane with a named owner; no merge/commit/issue creation — draft text in Markdown only.

## Next move

Next supervisor pass (iteration 1017): Phase 7 schemas/migration/rollback-safety slice under the decade carry (1017–1019 carry, 1020 must go live). No implementation.

## Docs-only packaging (this pass: non-checkpoint — none)

Non-checkpoint pass: no staging, no commit, no push, no PR action. This handoff remains an unpackaged working-tree file for the 1020 checkpoint. Nothing was discarded or reverted.
