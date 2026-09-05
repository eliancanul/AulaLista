# Supervisor iteration 0021 — baseline architecture and domain contracts

Iteration: 21 | Phase focus: baseline architecture and domain contracts
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–20)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `cc95426` (iteration-20 PR-record append); gate log tip still `b22b55b`; no third flip. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) stands — no PR duty until iteration 30.

Prior memory: `supervisor-iteration-0020.md` (checkpoint, gate back to HOLD 2.5/6, cumulative 11–20, PR 112 push) + `supervisor-cumulative.md` (spine 2→20) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`) + `-0019.md` (ranking + #98 0/7 rubric) + `-0018.md` (seams) + `-0011.md` (baseline, first off-cycle flip).

## Scope

Phase-focus: re-verify baseline architecture and CONTEXT/DESIGN domain contracts against current code, not against prior handoffs. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 30). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`CONTEXT.md` (full, 127 lines), `DESIGN.md` (§Decisión y límites + authority boundary), `AGENTS.md` (skills pointer); `docs/handoffs/supervisor-iteration-0020.md` + `-0019.md` (§-scoped) + `supervisor-cumulative.md` + `IMPLEMENTATION-GATE.md` (carried, not edited); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` tail (head still 0029); `ls -R curriculum/schemas/` (flat); `grep` spot-checks `views.py:2006,2022,2420,2446,2456`, `staging_validation.py:16,25,189`, `curriculum_import.py:23`, `models.py:36,48-55,289-308,369,384,434,444,599,762,1130`; `git log --oneline -3`, `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every line count byte-identical to iterations 2–20; migrations head still 0029; `schemas/` still flat (README + 3 `.schema.json`, no `v2/`); `git diff --stat` identical (+209/−716); status differs from iteration 20 only by the absence of untracked `supervisor-iteration-0019.md` (committed in `606aa64`) — i.e. the expected own-handoff delta, now `supervisor-iteration-0021.md` pending. No Phase A–E commit, no C1–C5 wording fix, no A5b template switch, no `v2/`, no new service module.
2. **Domain contracts hold against code (observed, baseline re-verification).** `CONTEXT.md` vocabulary maps cleanly: only-human-publish enforced at `models.py:289-308` (`publish()` requires `EDITORIAL_REVIEWER_GROUP_NAME`, `models.py:36`, else "La publicación requiere el grupo EditorialReviewer"); immutable SHA256 snapshot at `models.py:48-55` (`_canonical_payload_sha256`), `:369` (hash on publish), `:384` (`sha256` `editable=False`), read as immutable in `views.py:743,2500` with short-hash display `:1031,1091`; teacher-activation gate at `models.py:434,444` + `:599` (`teacher.is_active` checks) with session classes `:762,1233,1253`; AI-proposes-only consistent with `views.py:2331` (proposals are immutable context). DESIGN.md authority boundary (IA solo propone; EditorialReviewer publica; maestra activa; DemoPackage sintético sin claims) contradicts nothing observed. No new egress, no auth-model drift detected this pass.
3. **Fingerprint cites re-confirmed (observed).** `_grouped_activities` `views.py:2420`, `_import_action_convert` `views.py:2446` with positional `entry = job.activities[int(index)]` `:2456`, call site `:2006`, grouped reuse `:2022`; `staging_validation.py:16` `SCHEMA_VERSION = "v1"`, `_norm` `:25`, hash `:189` + block `:203-205` (C1 caveat carries); `CHAT_TIMEOUT_SECONDS = 180` at `curriculum/curriculum_import.py:23` (iteration-20 correction holds — no other repo hit); N+1-fixed note holds (`models.py:1130` `in_bulk`); `views.py` 92 / `models.py` 66 `def` counts (re-derived via grep-count; iteration-18 reported 91/26 by a different counter — methodology difference, not tree movement; canonical fingerprint stays the `wc -l` set).
4. **Gate: no edit, HOLD carries (decision by rule).** No third flip observed (log tip `b22b55b`); iteration-20 2.5/6 scorecard and HOLD stand. Gate review + cumulative deltas + docs-only PR push next due at iteration 30, not now.
5. **Fused-decision spine unchanged (observed + carry).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. #98 stays the sole staging-path `ready-for-agent` candidate at 0/7 executable slots (iteration-19 rubric, carried — issue bodies not re-read, tree unchanged so no re-grade possible). #53/#54/#57 stay correctly unlabeled; #58 stays docs-only epic-body work.
6. **Standing precision debts unchanged (observed).** C1 `_norm` scope, report surface, M4 artifact shape, C3 `models.py:1875` docstring, cursor-duplication evidence debt, S-number pinning — all carried unmodified; none became newly answerable since the tree did not move.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **No gate edit, no cumulative edit, no PR this pass** — non-checkpoint iteration per loop rules.
- **Counter-methodology note adopted:** future `def`-count cites must name the counter (`grep -c "^def \|^    def "` → 92/66 this pass) alongside the iteration-18 numbers (91/26, different counter) to avoid false drift signals. `wc -l` fingerprint remains canonical.
- **Cite discipline re-affirmed:** current lines only (`views.py:2420/2446/2456/2006/2022`, `staging_validation.py:16/25/189`, `curriculum_import.py:23`, `models.py:36/48-55/289-308/369/384/762/1130`); prompt's stale pre-shrink numbers (`views.py:2875-2876,2959-2960,3504`, `models.py:1998,1125-1127`) remain superseded.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→21.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? Two unamended flips is a pattern. (Carry-over 11→21.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→21.)
4. Agent-ready (C1): recursive `_norm` on inner proposal text vs outer-keys-only (`staging_validation.py:25-26` vs `:203-205` vs ADR-0010 §Decisión-2)? Precedes backfill AND staging-adjacent seams. (Carry-over 3→21.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Assumed review-screen + pre-convert list. (Carry-over 5→21.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→21.)
7. Agent-ready (C3): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→21.)
8. Draft-quality: should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→21.)
9. Evidence debt: name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (Carry-over 11→21.)
10. Seam-spec: pin S5/S4/S2 to current `views.py` def spans or retire S-numbers and re-derive post-shrink? (Carry-over 18→21.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Land the five R1 doc-precision patches (C1–C5 from iteration 14) as docs-only PR content; the #98 upgrade depends on C1, the `models.py` docstring on C3.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick + iteration-15 A5a/A5b split + corrected timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (including the `curriculum_import.py:23` correction and the grep-count methodology note), the N+1-fixed note (`models.py:1130` `in_bulk`), and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / `models.py` 2038; `:2420` grouped, `:2446` convert positional `:2456`, `:2006` call site, `:2022` reuse; `staging_validation.py:16` version, `:25` `_norm`, hash `:189/:203-205` with C1 caveat; `curriculum_import.py:23` timeout; `models.py:36` reviewer group, `:48-55` sha256, `:289-308` publish gate, `:384` immutable hash, `:762` session, `:1130` `in_bulk`; `services/results.py` 552, `roadmap_cursor.py` 27; `schemas/` flat, no `v2/`; migrations head 0029), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 22): resume the rotating phase loop (suggested: curriculum staging join and relational model, or idempotency/dedup with a C1 `_norm`-scope decision sketch). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared) and whether the gate moved a third time. Checkpoint duties next due at iteration 30 (cumulative deltas + gate review + docs-only PR push); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push, no new PR. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) untouched this pass.
- This handoff (`supervisor-iteration-0021.md`) remains untracked until the iteration-30 checkpoint packages it with 22–30 per the docs-only PR rule.
