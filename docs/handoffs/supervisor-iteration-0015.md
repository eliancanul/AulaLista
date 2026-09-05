# Supervisor iteration 0015 — tests, evidence, and acceptance matrix

Iteration: 15 | Phase focus: tests, evidence, and acceptance matrix
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–14)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `b22b55b` (docs: gate stable-id review form slice) on top of `498a4df` (first gate slice) on top of `3848d49` (PR 112 record) on top of `2889fa9` (iteration-10 checkpoint). PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) already exists — no PR duty until iteration 20.

Prior memory: `supervisor-iteration-0014.md` (C1–C5 contradiction reconciliation) + `-0013.md` (`_norm`-scope asymmetry) + `-0012.md` (triple-join cite) + `-0011.md` (2/6 gate scorecard) + `supervisor-cumulative.md` (spine 2→10) + `supervisor-iteration-0005.md` (acceptance matrix A1–A9, the phase baseline re-verified here).

## Scope

Phase-focus: re-verify the iteration-5 acceptance matrix (A1–A9) against current code, not against prior handoffs, and record what the second off-cycle gate flip changes. Spec only — nothing implemented. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 20). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/` inventory (0001–0010, no new ADR), `docs/handoffs/IMPLEMENTATION-GATE.md` (current on-disk second slice), `supervisor-iteration-0005/0011/0012/0013/0014.md`, `supervisor-cumulative.md`; `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` inventory (0001–0029, no 003x); `ls curriculum/schemas/` (4 files: README + activities/llm_trace/topics, no `v2/`); `python3 scripts/check_migrations.py` → OK; `ls tests/test_*.py | wc -l` → 42 files; `python3 -m pytest --collect-only` → `No module named pytest` (no `.venv`); `templates/curriculum/tutor_import_detail.html:144-193` (full read of review/convert block); `rg` for `_import_action_convert|_activity_id|int(index)` in `views.py`, `convert|activity_id|index|def test_` in `test_t15`, `item\.(id|index)|select` in templates; `git show b22b55b --stat` + gate diff, `git show 498a4df --stat`, `git log --all --oneline --grep=41560047`, `git branch -a` (agent branches present); `ls docs/handoffs/ | grep coding` → empty on this branch; `git show agent/aulalista-implementation-41560047f83c --stat` (branch exists, not checked out). Test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **Gate flipped off-cycle a SECOND time — the iteration-11 pattern warning is now CONFIRMED (observed, the one thing that moved).** `b22b55b` (human, "docs: gate stable-id review form slice") rewrote the `498a4df` first slice into a second slice: governing spec adds `coding-41560047f83c.md` alongside ADR-0010 + iteration-10 R2; scope changes from "eliminate the positional hazard in the conversion path" (`curriculum/views.py` + test) to "make the review UI submit the stable `item.id`" (`templates/curriculum/tutor_import_detail.html` + `tests/test_t15_curriculum_import.py` + handoffs); base ref changes from self-referential `supervisor/aulalista-docs` to `agent/aulalista-implementation-41560047f83c` with a stacked-PR base (do not merge automatically). Iterations 11–14 called the first flip a "single off-cycle event, not yet a confirmed pattern" — that sentence is now retired. The loop rule reserving gate changes for 10th iterations has been bypassed twice; iteration 20 must either adopt a human-signed amendment allowing stacked-slice gate updates or revert to `HOLD` with reasoning. Scorecard update in §Decisions.
2. **No new tree evidence on THIS branch (observed).** All line counts byte-identical to iterations 2–14; migrations head still 0029; `check_migrations.py` green; `schemas/` still flat; hash/dedup still unwired; C1–C5 (iteration 14) wording unfixed. On this branch convert is still positional (`views.py:2456` `entry = job.activities[int(index)]` inside `2446-2475`) and the template still submits `item.index` (`tutor_import_detail.html:148` `value="{{ item.index }}"`), with `item.id` present only on the remove form (`:157` `activity_id` `value="{{ item.id }}"`). The first-slice fix (`d758461` "Convert staging activities by stable activity_id") and its handoff record (`ac4ffdb` "Record PR 113 in coding handoff 41560047f83c") exist ONLY on `agent/aulalista-implementation-41560047f83c`, not on this branch. Supervisor-branch A5 therefore stays OPEN; the fix is cross-branch until merged or cherry-picked.
3. **Gate cites evidence invisible on its own branch (observed, NEW traceability gap).** The on-disk gate's governing-decision line cites `docs/handoffs/coding-41560047f83c.md`, but `ls docs/handoffs/ | grep coding` on this branch is empty — the file lives on the agent branch (`git log --all` finds `ac4ffdb` + `d758461` there). Any reviewer standing on `supervisor/aulalista-docs` cannot verify the claimed "completed conversion handler" or "reviewed first-slice implementation branch" without fetching another branch. Iteration-20 gate resolution must either vendor the coding handoff + diff evidence onto the supervisor branch or name the exact cross-branch refs (branch + commit + PR 113 URL) in the gate file.
4. **Acceptance-matrix re-verification (observed — the phase deliverable; Gap column only, per iteration-5 methodology).** A1 title-join transitional (`staging_validation.py:55-80` exact-`==`, writes `views.py:2221-2222,2383-2384`, consumer `views.py:2426,2428`): no removal test, unchanged. A2 idempotency key (`staging_validation.py:189-208`, `_norm` `:25-26`): zero pipeline call sites on this branch, unchanged; C1 scope pick still unstated. A3 report-only dedup (`:211-238`, `test_t54:119-127`): no badges in `_grouped_activities` (`views.py:2420-2444`), unchanged. A4 schema enforcement (`test_t54:55-105`, `models.py:1874-1896`, C3 path caveat): unchanged. A5 convert identity: SPLIT this pass — A5a handler (positional `:2456` here; fixed per gate claim on agent branch `d758461`, unverified from here) vs A5b template contract (`:148` still `item.index`; gate second slice targets exactly this line + one new test in `test_t15`). `test_t15` grep confirms 13 matches with zero `convert`/`activity_id` tests — the regression test the second slice requires does not exist on this branch. A6 N+1 (`models.py:1110-1139` `select_related` + `in_bulk`): still no named perf test, unchanged. A7 single cursor (27-line service, call sites `views.py:2505,2579,2599,2634,2770,2807,2866`): still no named cursor test; duplicated-cursor pair still unnamed — claim must still ride with the service cite or be dropped. A8 anti-collision (`check_migrations.py` OK re-run this pass, head 0029): green, unchanged. A9 design/privacy (`test_design_contract.py`, T13 checklist empty, LAN spec-only): unchanged; no ticket may claim physical-LAN or concurrent-write support.
5. **Test-count and runner facts (observed).** 42 `test_*.py` files (iteration 5 inventoried 42; `implementation-current.md` header still says "238 pruebas" main-snapshot per C4 — apparent contradiction only, different counting methods). `pytest` unrunnable here (runtime-only `requirements.txt`, pytest in `requirements-dev.txt`, no `.venv`); CI remains the verifier. `test_t54` still 127 lines. No test file was added/modified on this branch this pass.
6. **Fused-decision spine unchanged (observed).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite (green again this pass), #58 stale epic body, #55/#56/#65 peripheral — no tracker re-pull this pass (that was iteration 9/10's read-only `gh` job; the qualified "sole `ready-for-agent` issue **on the staging critical path**" sentence stands).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, Steps 0–4 per iteration 8, queue R1–R5 per iteration 9, HOLD + cumulative per iteration 10, 2/6 scorecard per iteration 11, triple-join cite per iteration 12, `_norm`-scope asymmetry per iteration 13, C1–C5 reconciliation per iteration 14).
- **Gate: no edit this pass (10th-iteration duty).** Assessment only — the `b22b55b` second slice against iteration-10's six flip conditions: (a) Phase A–E tree human-reviewed/committed → STILL OPEN (status shape unchanged); (b) narrowed allowed paths → IMPROVED FURTHER (template + one test file + handoffs is the smallest slice yet; Python correctly out-of-scope); (c) mandatory convert-to-`activity_id` + test → SPLIT (handler claimed done cross-branch `d758461`, template + test still pending — the gate correctly targets the remainder); (d) non-self-referential base ref → IMPROVED (base is now the agent branch, not self — but the evidence file it cites is not on this branch, see Finding 3); (e) open questions 2–4 answered → STILL OPEN (M4 correctly excluded, `_norm`/surface picks undecided); (f) zero blockers → STILL OPEN (blocker (a) persists). Score: 2.5/6 (b and d improved, c half, a/e/f open). The parallel coding lane validates the gate independently; supervisor records HOLD-pending-20th-review and does not countermand the on-disk file outside checkpoint duty.
- **Matrix contribution (this pass, no code):** A5 splits into A5a/A5b per Finding 4; Finding 3 adds a traceability rule (gate must cite evidence reachable from its own branch or name exact cross-branch refs). All other rows carry forward unchanged — "no new evidence" for A1–A4, A6–A9 beyond the re-verification cites above.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→15.) Blocks any future supervisor `READY`.
2. Gate provenance: `498a4df` AND `b22b55b` both flipped the gate off-cycle after HOLD. Deliberate stacked-slice strategy or accident? If deliberate, the loop rule needs a human-signed amendment at iteration 20. (Carry-over 11→15, now a confirmed pattern, not a single event.)
3. Traceability (new this pass): vendor `coding-41560047f83c.md` + first-slice diff evidence onto the supervisor branch, or record exact cross-branch refs (branch + commit `d758461`/`ac4ffdb` + PR 113 URL) in the gate? A gate that cites an unreachable file cannot be validated from its own branch.
4. Agent-ready (carry-over 3→15, citable as C1): recursive `_norm` on inner proposal text vs current outer-keys-only (`staging_validation.py:25-26` vs `:203-205` vs `:232` vs ADR-0010 §Decisión-2)? Must precede any backfill slice.
5. Agent-ready (carry-over 5→15): duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? Assumed review-screen + pre-convert list until confirmed. `_grouped_activities` (`views.py:2420-2443`) emits no badges.
6. Agent-ready (carry-over 7→15): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? Needed before any M4 ticket exists.
7. Evidence debt (carry-over 11→15): name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (No pair observed again — all cursor reads via the 27-line service: `views.py:2505,2579,2599,2634,2770,2807,2866`.)
8. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. At iteration 20, resolve the gate cleanly: adopt the two stacked slices verbatim WITH vendored evidence (or exact cross-branch refs + PR 113 URL) + a clean `updated-tech` base ref + answered picks, or revert to `HOLD` with the 2.5/6 scorecard. Do not let a third off-cycle flip accumulate — two is already a pattern.
2. Land the five R1 doc-precision patches (C1–C5 from iteration 14) as docs-only PR content alongside the A5b template slice evidence, since backfill wording depends on C1. Then consume staging work strictly R1 → R2 (A5a handler + A5b template contract `tutor_import_detail.html:148` `item.index` → `item.id`, tested in `test_t15`) → R3 (M1→M3 slice, M4 excluded) → R4 (seams S5→S4→S2; S1 fused with M3). Acceptance: iteration-5 rows A2+A3+A4+A5a+A5b+A8.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + iteration-13/14 `_norm`-scope asymmetry (C1) + this pass's A5a/A5b split before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order (#57 prerequisite → fused #53/#98/#54 → periphery).
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the triple-join cite table (`views.py:2221-2222,2383-2384` writes; `staging_validation.py:55-80` exact-`==` read; `views.py:2426,2428` consumer) + the idempotency cite table (`staging_validation.py:189-208` hash, `:211-238` report, zero pipeline call sites on the supervisor branch, touchpoints `views.py:2218-2251/2343-2362/2446-2475`) + the A5a/A5b split (`views.py:2456` vs `tutor_import_detail.html:148` vs remove `:2317`) + the C1–C5 reconciliation table so future passes stop re-deriving them.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: template contract `tutor_import_detail.html:148` `item.index` vs `:157` `item.id`; convert `views.py:2446-2475`, positional `:2456`; remove `views.py:2307-2325`, resolve `:2317`; `_activity_id` `views.py:2301-2304`; hash `staging_validation.py:189-208`, `_norm` `:25-26`, proposal blob `:203-205`, ambiguous key `:232`, report `:211-238`, join read `:55-80` exact-`==` `:76-77`; join writes `views.py:2221-2222,2383-2384`; generate persist `:2238-2251`; topup pending `:2343-2362`; consumer `views.py:2420-2444`; fixed N+1 site `models.py:1110-1139`; `clean()` `models.py:1874-1896` with path caveat C3; dev defaults `settings.py:8-21`; `test_t54:55-127`; `test_t15` (no convert test — gap A5b); `scripts/check_migrations.py`; migrations head 0029; 42 test files; ADR-0010 §Decisión-2 with C1 caveat; `DATABASE.md:103-105` with C2 caveat), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iterations 5 (A1–A9, now with A5a/A5b), 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress), 7 (M0→M4 + per-step rollback), 8 (Steps 0–4, S1 fused with M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; `scripts/check_migrations.py` + `makemigrations --check` clean at every step; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch (new Finding-3 rule).
- Dedup/schema rules unchanged (report + human confirm; `exact` only with confirm; `same_title_diff_content` side-by-side; `_norm`-scope pick stated per C1; one merged section per title-key with badges; v1-keep vs `v2/`-bump with `.schema.json` + Python validator updated together).
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 16): re-check whether the working tree changed (Phase A–E committed, C1–C5 wording fixed, A5b template switched, report wired, head past 0029) and whether the gate file moved a third time (a third off-cycle flip would force the rule-amendment question at iteration 20). If moved, verify the touched R/M/S step against the cumulative synthesis + iteration-5 matrix; if unchanged, record "no new evidence" and advance the rotating phase (suggested: M4-export shape or report-surface pick, the two least-specified open questions after this pass re-verified the matrix). Checkpoint duties next due at iteration 20 (cumulative deltas + gate review + docs-only PR); final synthesis at iteration 100 — neither is due now.
