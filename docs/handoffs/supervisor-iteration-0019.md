# Supervisor iteration 0019 — ready-for-agent ranking and issue draft quality

Iteration: 19 | Phase focus: ready-for-agent ranking and issue draft quality
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–18)

`git status --short --branch` at pass time:

```text
## supervisor/aulalista-docs...origin/supervisor/aulalista-docs
 M aulalista/settings.py
 M curriculum/models.py
 M curriculum/views.py
 M docs/DATABASE.md
 M docs/implementation-current.md
 M docs/teacher-flow.md
 D health/templates/health/local_access.html
?? .DS_Store
?? curriculum/schemas/
?? curriculum/services/
?? curriculum/staging_validation.py
?? docs/.DS_Store
?? docs/handoffs/supervisor-iteration-0011.md
?? docs/handoffs/supervisor-iteration-0012.md
?? docs/handoffs/supervisor-iteration-0013.md
?? docs/handoffs/supervisor-iteration-0014.md
?? docs/handoffs/supervisor-iteration-0015.md
?? docs/handoffs/supervisor-iteration-0016.md
?? docs/handoffs/supervisor-iteration-0017.md
?? docs/handoffs/supervisor-iteration-0018.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). Gate log tip still `b22b55b` (second slice); no third flip. HEAD unchanged since iteration 15. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) already exists — no PR duty until iteration 20. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant.

Prior memory: `supervisor-iteration-0018.md` (god-files, S1-LAST-fused-with-M3 re-verified, 91 defs) + `-0017.md` (migration spine M0→M4, C1/C3 carry) + `-0016.md` (security envelope, Ollama 180s close-out) + `-0015.md` (A1–A9 re-verification, A5a/A5b split, traceability gap) + `supervisor-cumulative.md` (spine 2→10).

## Scope

Phase-focus: re-grade the `ready-for-agent` set and the draft quality of the staging-critical issue (#98) against current code, not against prior handoffs. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 20). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`docs/handoffs/IMPLEMENTATION-GATE.md` (log tip check only); `gh issue list` (full + `ready-for-agent` label filter); `gh issue view 98` (full body); label/state probes for #53/#54/#57/#58; `wc -l` of `views.py` (2950) / `models.py` (2038) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `settings.py` (135); `ls curriculum/schemas/` (flat); `curriculum/migrations/` tail (head still 0029); `git diff --stat`, `git log --oneline -5`, gate log. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** All line counts byte-identical to iterations 2–18; status differs from iteration 18 only by the new untracked `supervisor-iteration-0018.md` (last pass's own handoff). Migrations head still 0029; `schemas/` still flat (README + 3 `.schema.json`, no `v2/`); gate file untouched since `b22b55b` — the two-flip pattern stands, still no third flip. C1–C5 wording unfixed.
2. **`ready-for-agent` set unchanged at six (observed).** Label-filtered list returns exactly #95, #97, #98, #103, #104, #107 — same six recorded in the cumulative spine. Only #98 sits on the staging critical path; #95/#103/#104/#107 are Dirección A/B institutional work and #97 is teacher-UI assist-cancel. The loop-prompt correction from the cumulative synthesis still applies: "sole ready-for-agent path" is true only as "sole `ready-for-agent` issue **on the staging critical path**."
3. **#98 draft body unchanged and still not executable (observed).** Full body re-read this pass: 2 sections, ~6 criteria lines (idempotent retry, documented key/rules, preserve sources/editorial/human decisions, ambiguous conflicts reported not silently merged, retry/partial/same-title-different-source tests, #47 antecedent + editorial-workflow check). It names zero ADRs, zero file:line cites, zero allowed/out-of-scope paths, zero named test files, zero migration/rollback plan, zero base ref, zero invariant list. Grade carries from iteration 9/15: closest on the staging path but not agent-executable.
4. **Draft-quality gap sharpened with a rubric (this pass, no ticket created).** An executable staging ticket needs 7 slots: (a) governing ADR/spec, (b) exact allowed paths, (c) explicit out-of-scope paths, (d) invariants preserved, (e) acceptance tests by file name, (f) migration/rollback plan, (g) concrete base ref. #98 as observed fills ~(none) of 7: it implies (e) generically ("pruebas de reintento…") without file names and (d) partially ("estado editorial y decisiones humanas") without the full contract list. The other five `ready-for-agent` issues were not body-read this pass; they are ranked peripheral by title/label alone and must not be promoted onto the staging path regardless of their individual quality.
5. **Ranking re-verified (observed + carry).** R1 (M0 precision, docs-only) → R2 (mandatory convert-to-`activity_id` switch, tested) → R3 (M1→M3 slice, M4 excluded) → R4 (S5→S4→S2) → R5 (periphery stays out) from iteration 9 still holds. #53/#54 bear no `ready-for-agent` label (observed: #53 `enhancement+tech-debt`, #54 `tech-debt` only) — correctly unlabeled, since promoting either alone would invite doing one third of the fused decision without the others. #57 (`tech-debt` only) correctly unlabeled as prerequisite tooling. #58 correctly unlabeled stale epic.
6. **What the #98 upgrade must contain (precision advance, not a ticket).** Beyond the iteration-9 §Draft body, a future docs-only upgrade must add: triple-join cite (iteration 12), C1 `_norm`-scope pick (iteration 14, still open), A5a/A5b split (iteration 15: A5a convert-identity tested slice vs A5b template `item.index→item.id` slice), timeout cite (`CHAT_TIMEOUT_SECONDS = 180`, iteration 16), and the iteration-18 seam guard (S1 LAST fused with M3; staging-adjacent seams blocked on C1). Current-line cites for the draft: `views.py:2420` `_grouped_activities`, `:2446` `_import_action_convert` positional `:2456`, `:2006` convert call site, `:2022` grouped reuse; `staging_validation.py:16` version, `:25-26` `_norm`, `:203-205` hash with C1 caveat; `services/results.py` 552 + `roadmap_cursor.py` 27 as delegate-shape exemplar; migrations head 0029; `schemas/` flat.
7. **Fused-decision spine unchanged (observed).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. Gate traceability gap from iteration 15 (on-disk gate cites `coding-41560047f83c.md`, unreachable from this branch) persists — carried as standing finding, not re-verified by `ls` this pass.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, Steps 0–4 per iteration 8, queue R1–R5 per iteration 9, HOLD + cumulative per iteration 10, 2.5/6 scorecard per iterations 11–18, C1–C5 per iteration 14, envelope per iteration 16, seam map per iteration 18).
- **Gate: no edit this pass (10th-iteration duty).** Assessment only — no third flip observed; iteration-15 2.5/6 scorecard carries. Iteration 20 must adopt a human-signed amendment allowing stacked-slice updates (with vendored evidence or exact cross-branch refs) or revert to `HOLD`.
- **Ranking contribution (this pass, no code):** #98 stays the sole staging-path `ready-for-agent` candidate and stays not-executable until upgraded with the §Draft body + 5 cites/picks listed in Finding 6; #53/#54/#57 stay unlabeled by design; #58 stays a docs-only epic-body update; #95/#97/#103/#104/#107 stay peripheral regardless of draft polish.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→19.) Blocks any future supervisor `READY`.
2. Gate provenance: `498a4df` AND `b22b55b` both flipped the gate off-cycle. Deliberate stacked-slice strategy or accident? Loop rule needs a human-signed amendment at iteration 20. (Carry-over 11→19, confirmed pattern.)
3. Traceability (carry-over 15→19): vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate?
4. Agent-ready (carry-over 3→19, citable as C1): recursive `_norm` on inner proposal text vs outer-keys-only (`staging_validation.py:25-26` vs `:203-205` vs `:232` vs ADR-0010 §Decisión-2)? Must precede any backfill slice AND any staging-adjacent seam work.
5. Agent-ready (carry-over 5→19): duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Assumed review-screen + pre-convert list.
6. Agent-ready (carry-over 7→19): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)?
7. Agent-ready (carry-over 14→19, citable as C3): `models.py:1875` docstring path — flat `*.schema.json` wording?
8. Draft-quality (new, for iteration 20+): should the #98 upgrade be staged as R1-doc-precision content inside the docs-only PR, or as a separate drafted-but-uncreated ticket text reviewed alongside it?
9. Evidence debt (carry-over 11→19): name the duplicated-cursor pair with current lines or drop the claim from the loop prompt.
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. At iteration 20, resolve the gate cleanly: adopt the two stacked slices verbatim WITH vendored evidence (or exact cross-branch refs + PR 113 URL) + a clean `updated-tech` base ref + answered picks, or revert to `HOLD` with the 2.5/6 scorecard. Do not let a third off-cycle flip accumulate.
2. Land the five R1 doc-precision patches (C1–C5 from iteration 14) as docs-only PR content; the #98 upgrade wording depends on C1, `models.py` docstring on C3.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 `_norm`-scope pick + iteration-15 A5a/A5b split + iteration-16 timeout cite (`CHAT_TIMEOUT_SECONDS = 180`) + iteration-18 seam guard (S1-LAST-fused-with-M3) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the triple-join cite table + idempotency cite table + A5a/A5b split + C1–C5 table + migration-sequence cites (`schemas/README.md:3-10` version rule; `staging_validation.py:16` SCHEMA_VERSION; head 0029; `check_migrations.py` OK) + this pass's ranking cites (six `ready-for-agent`: #95/#97/#98/#103/#104/#107; #98 body has 0/7 executable slots).

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: six-issue set #95/#97/#98/#103/#104/#107 with #98 sole staging-path; #98 body 0/7 slots; `views.py` 2950 lines, `:2420` grouped, `:2446` convert positional `:2456`; `staging_validation.py:16` version, `:25-26` `_norm`, `:203-205` hash with C1 caveat; `services/results.py` 552, `roadmap_cursor.py` 27; `schemas/` flat, no `v2/`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iteration 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress) + iterations 5/7/8 (A1–A9 with A5a/A5b, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness (ADR, allowed paths, out-of-scope, invariants, named tests, migration/rollback, base ref); `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 20): checkpoint duties fall due — update `supervisor-cumulative.md` with deltas only (iterations 11–20), review/repair `IMPLEMENTATION-GATE.md` (adopt stacked slices with vendored evidence + clean base ref or revert to `HOLD` with scorecard), and package only staged `docs/handoffs/` + `docs/adr/` Markdown on `supervisor/aulalista-docs` into a pushed, non-merged PR when safe (verify `git diff --cached --name-only` first; never `git add -A`, never stage code, never merge). Pre-checks: whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, new service module) and whether the gate moved a third time. Final synthesis at iteration 100 — not due now.
