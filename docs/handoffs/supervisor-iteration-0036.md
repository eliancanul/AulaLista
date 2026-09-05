# Supervisor iteration 0036 — security, deployment, and operational constraints

Iteration: 36 | Phase focus: security, deployment, and operational constraints
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–35)

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
?? docs/handoffs/supervisor-iteration-0031.md
?? docs/handoffs/supervisor-iteration-0032.md
?? docs/handoffs/supervisor-iteration-0033.md
?? docs/handoffs/supervisor-iteration-0034.md
?? docs/handoffs/supervisor-iteration-0035.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

(`git diff --cached --name-only` → empty at pass start. HEAD `bef32fd`. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 OPEN, unmerged.)

Prior memory: `supervisor-iteration-0035.md` (tests/evidence/matrix, P1/P2 placement, Q13 runner gap) + `supervisor-iteration-0034.md` (C1–C5 three-way reconciliation) + `supervisor-cumulative.md` (spine 2→30, deltas 21–30) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`, 2.5/6).

## Scope

Non-checkpoint rotating-phase pass (security/deployment/operational constraints, per the 21→28 cycle order and the iteration-35 §Next move). Spec only — nothing implemented, no issue created/edited/labeled, no gate edit, no cumulative edit, no PR push (checkpoint duties next due at iteration 40). This pass re-verifies the iteration-6/26 security envelope against current lines and adds one new precision datum (DEBUG-block scope) without touching code.

## Files inspected

`supervisor-iteration-0035.md` (full) + `supervisor-cumulative.md` (spine + deltas 21–30 headers) + `IMPLEMENTATION-GATE.md` (status + scorecard lines only, no edit); `aulalista/settings.py` (full re-read, 135 lines); `aulalista/urls.py:220-229` (DEBUG block, direct read); `curriculum/views.py:100-142,158-219` (TTL + `teacher_required` + sealed-cookie helpers, direct re-read); `curriculum/curriculum_import.py:21,23,72,279-280` (Ollama URL/timeout/urlopen, by grep); `health/lan.py:19,47-78` + `health/views.py:13-23` (explicit LAN base, by grep); `docs/implementation-current.md:23-33,90-107` (stack/deploy/LAN/physical-run, direct re-read); `docs/teacher-flow.md:61-87` (ownership/retention, direct re-read); `docs/adr/0004-provisional-local-runtime-baseline.md` (full re-read, 5 lines); live greps: `SECURE_|SESSION_COOKIE|CSRF_COOKIE` (0 matches outside comments), `staff/login/permission/signed_cookie` census; `wc -l` (views 2950 / models 2038 / settings 135 / staging_validation 238 / results 552 / roadmap_cursor 27 / test_t54 127 — byte-identical to iterations 2–35); `ls curriculum/schemas/` (README + 3 `.schema.json`, flat, no `v2/`); migrations tail (head still 0029); `python3 scripts/check_migrations.py` → OK; `ls tests/test_*.py | wc -l` → 42; `gh` issue set not re-queried this pass (six-issue set #95/#97/#98/#103/#104/#107 carries from 19–35, no change alleged). `pytest` unrunnable here (no `.venv`); security claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–35; head still 0029; `schemas/` flat; `check_migrations.py` OK (re-run this pass); `git diff --stat` identical (+209/−716); status shape identical modulo the now-present untracked `supervisor-iteration-0035.md`. No Phase A–E commit, no settings hardening, no cookie-flag change, no egress addition, no head advance. Sixteenth consecutive no-drift pass (21–36).
2. **Staff gate re-verified, correctly placed (observed, direct re-read).** `teacher_required` (`views.py:125-142`) requires authenticated + `is_staff` + `is_active`, else `redirect_to_login` / 403. `_safe_teacher_next` (`:106-122`) restricts the `next` param to a validated local path. This is the "staff-gated pipeline" cited since iteration 6 — mechanism now pinned to exact lines. Teacher data isolation holds alongside: `ClassroomGroup`/`group` scoped by `created_by=request.user` (`views.py:840,895,904,921,1224,1263,1323`, by grep). No gap here.
3. **Sealed device/turn cookies re-verified; `Secure` flag still absent (observed, direct re-read).** Seal/unseal (`views.py:158-170`), `set_cookie(httponly=True, samesite="Lax")` (`:173-176`), TTL 12h (`:100-103`), per-browser binding check (`:197-210`). No `Secure=True`, no `__Host-` prefix, no `SESSION_COOKIE_*` / `CSRF_COOKIE_*` / `SECURE_*` settings anywhere (grep 0 matches). Correct posture for LAN-only HTTP (TLS absent by design, see finding 5), but the hardening checklist owner (Q11) still has no answer: whoever signs institutional deploy must record the `Secure`-on-HTTPS flip explicitly.
4. **Dev-default secrets/DEBUG/hosts/validators unchanged (observed, direct re-read).** `settings.py:11-13` dev-default SECRET, `:14-18` DEBUG defaults True, `:19-23` `ALLOWED_HOSTS` defaults `*`, `:107` `AUTH_PASSWORD_VALIDATORS = []`. Mitigating comment (`:7-10`) documents the deploy triple (`AULALISTA_SECRET_KEY` + `AULALISTA_DEBUG=False` + explicit hosts, `check --deploy` must fail otherwise). No `check --deploy` clean run is on record; no env-based test asserts it. Pre-institutional gap, out of scope for the staging lane.
5. **Deployment envelope re-verified: LAN-only HTTP, single-process SQLite, Ollama-only egress (observed).** LAN base explicit via `AULALISTA_LAN_URL` (`settings.py:128-130`), never auto-detected (`health/lan.py:19,47-78`; `implementation-current.md:90-96`); serve on `0.0.0.0` via `runserver` doc example (`:99-102`) and `scripts/run_wsgi.py:18` default host. Single-process: SQLite WAL + finite timeout (`settings.py:81-96`) + `LocMemCache` with the multi-worker warning comment (`:98-105`); ADR-0004 pins SQLite until a measured 30-client loss. Egress: only Ollama localhost (`settings.py:134`, `curriculum_import.py:21,72,279-280` `urlopen` with `noqa S310` trusted-local note), 180s timeout (`:23`); static/QR local-only (`implementation-current.md:28-29`); T12 demo blocks DNS/sockets/`urlopen` (`:104-105`); physical two-phone WAN-disconnected run still pending (`:105-107`).
6. **New precision datum at 36: DEBUG URL block is minimal (observed, direct read).** `aulalista/urls.py:228-229` gates only `staticfiles_urlpatterns()` behind `settings.DEBUG` — no debug toolbar, no extra endpoint. The DEBUG risk is therefore exactly the settings triple in finding 4 (verbose errors + `*` hosts + dev SECRET), not a hidden route. CSRF posture is also complete by reading: `CsrfViewMiddleware` (`settings.py:52`) + `{% csrf_token %}` in every POST template (grep: prepare/join/survey/import-detail/review/active/turn/activity/nav/roadmaps/groups/results).
7. **Gate and issue set unmoved (observed, not edited).** `IMPLEMENTATION-GATE.md` still `STATUS: HOLD` (2.5/6); six-issue `ready-for-agent` set carries (#95/#97/#98/#103/#104/#107, #98 sole on-path at 0/7 per iteration 29 — body not re-read this pass, no change alleged). PR 112 OPEN, unmerged. The parallel coding lane does nothing while the gate is `HOLD` or absent.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **Gate: HOLD observed at iteration 36** (no edit — checkpoint-only file per loop rules). Next gate review due at iteration 40.
- Security verdict: the iteration-6 envelope (LAN-only HTTP, staff-gated pipeline via `views.py:125-142`, sealed 12h cookies, single-process SQLite, Ollama-only egress, no new egress, `media/`-in-tarball by prior cite) is preserved by the tree and broken by none of the uncommitted Phase A–E lines inspected. The only security work before any institutional deploy remains the Q11 hardening checklist (env SECRET/DEBUG/hosts, validators, cookie `Secure` flip on HTTPS, `check --deploy` clean, physical LAN run) with a named owner + runbook location — explicitly out of the staging lane.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→36.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? (Carry-over 11→36.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→36.)
4. Agent-ready (C1, three-way framing at 34, re-verified at 35): confirm `_norm`-join + outer-keys-only hash, or keep exact reads with P1 pinning the exact-vs-`_norm` disagreement? (Carry-over 3→36.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list (with explicit overlap rendering per `test_t54:119-127`), `llm_log` audit copy. (Carry-over 5→36.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→36.)
7. Agent-ready (C3, re-verified at 27/34/35): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→36.)
8. Evidence debt (narrowed at 35): `views.py:1068` vs `_roadmap_cursor` — first 25 lines of `:1046-1094` read (`:1046-1070`); remaining `:1070-1094` still needed for the alias-vs-duplicate verdict. (Carry-over 11→36, actionable, halved.)
9. Seam-spec: keep S-numbers with the iteration-28 span pins, or retire them post-shrink? Recommend keeping with 28 spans as the pin table. (Carry-over 18→36.)
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
11. Security (from 26, re-verified at 36 with `views.py:125-142/:158-176` + `settings.py:7-23,52,81-107` + `urls.py:228-229` pins): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie `Secure` flip on HTTPS, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.
12. Branch anomaly: supervisor passes run on `supervisor/aulalista-docs`, not `updated-tech` per the prompt's "Work starts on" line (carry-over 9→36). Confirm whether future passes should switch branches or amend the prompt — switching with a dirty Phase A–E tree is unsafe, so the anomaly persists until a human directs otherwise.
13. Matrix execution (from 35): where does the A1–A9 + P1/P2 green run execute before wiring, given `pytest` is unrunnable in this supervisor environment (no `.venv`)? Name the runner (coding-lane env or CI) in the #98 upgrade.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Human reviews/commits the Phase A–E tree first — it is the load-bearing blocker for every downstream step (clean base ref, C1–C5 landing, R1→R4 queue).
3. Land the five R1 doc-precision patches (C1 three-site + draft pick with the `:56-62` declared-intent quote, three-way ADR==docstring≠code framing, and the `:119-127` overlap rule; C2–C5) plus the P1/P2 pending-row names as the first committed work once a base ref exists; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface.
4. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23, reframed at 32/33/34) + iteration-15 A5a/A5b split + timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface (with overlap rendering) + iteration-25 P1/P2 rows (placed: `test_t54` beside `:119-127`, P1 boundary + P2 guard-order) + iteration-28 S-span pins and `:1068` cursor verdict (half-read at 35) + iteration-36 security pins (`views.py:125-142` gate, `:158-176` sealed cookies, `urls.py:228-229` minimal DEBUG block) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order. Per Q8 (settled at 30), the upgrade rides as handoff Markdown in the docs-only PR, never as a created issue.
5. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist. The Q11 hardening checklist gets a named owner + runbook location but no lane or ticket until the staging slice lands.
6. Refresh the loop prompt with the qualified #98 sentence, current line cites (six-issue set with #98 sole on-path at 0/7; join `staging_validation.py:76-77` + declared-intent `:56-62` + three-way C1 framing (ADR-0010 §Decisión-2 == docstring `:192` ≠ code `:201-205`) + overlap rule `test_t54:119-127` + P1/P2 placement + writes `views.py:2221-2222,2383-2384` + call sites `:2343,2346/:2423,2426`; cursor `:1068` (half-read `:1046-1070`) vs `:2505…:2866`; `curriculum_import.py:23`; template `item.index :148` vs `item.id :157`; security `views.py:125-142/:158-176` + `settings.py:7-23,52,81-107` + `urls.py:228-229`; head 0029; 42 test files; `check_migrations.py` OK; AST views 91 top-level), the N+1-fixed note (`models.py:1130` `in_bulk`), the A5a/A5b split, the P1/P2 pending rows, the 7-slot draft rubric, and settled Q8.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: security `teacher_required views.py:125-142` + `_safe_teacher_next :106-122` + sealed cookies `:158-176` + TTL `:100-103` + binding `:197-210` + ownership `:840/:1224/:1263/:1323` + `settings.py:7-23,52,81-107,128-134` + `urls.py:228-229` minimal DEBUG + `curriculum_import.py:21,23,279-280`; matrix files t15/t16/t19/t20/t22/t24 + `test_t54` 127 lines/5 tests + overlap rule `:119-127` + P1/P2 placement; hash `:189-208` + dedup `:211-238` + `_norm` `:25-26` vs `:201-202` vs `:232` + join `:76-77` with declared-intent `:56-62`; join writes `views.py:2218-2225,2380-2387` + call sites `views.py:2343,2346/:2423,2426`; `views.py` 2950 / AST 91 top-level defs; cursor `views.py:1068` (read `:1046-1070`, remainder `:1070-1094` pending) vs 7 service sites; `roadmap_cursor.py` 27/1-def; `results.py` 552; `models.py` 2038, `CurriculumImportJob :1760` (no Topic/Subtopic/ActivityProposal tables), `ClassroomSession :762-1230` + `:1233/:1253`, `PublishedPackageSnapshot :376`, `EditorialReviewer` `:36/:308/:1961`, DemoPackage `:121/:137`; `models.py:1130` `in_bulk`, `:1875` C3 path caveat; template `item.index :148` vs `item.id :157`; `_activity_id :2301/:2317/:2428`; `schemas/` flat; migrations head 0029; 42 test files; `check_migrations.py` OK; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat; six-issue `ready-for-agent` set with #98 sole on-path at 0/7), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + Ollama-only egress, M0→M4 + per-step rollback with M4 separate human-confirmed, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; named matrix run (runner per Q13: coding-lane env or CI — supervisor env has no `.venv`) green including P1+P2 BEFORE wiring; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; ambiguous groups may overlap exact pairs (`test_t54:119-127`) and the surface must render overlap with exact-membership checked first (P2 pins guard order); named surface + P1 (join-agreement, pinning the exact-vs-`_norm` boundary per the `:56-62` refinement) + P2 (same-title-separation) required before wiring.
- Migration/rollback explicit per step (M1 additive-only, M2 re-runnable with C1 scope stated, M3 flagged read, M4 separate ticket with named export artifact + restore runbook); seam slices (S5→S4→S2, S1-LAST-fused-with-M3) carry behavior-only rollback (revert PR, no data change) and must not touch `_grouped_activities`/convert before R2 lands.
- Security non-regression per ticket: no new egress beyond Ollama localhost, no CDN/remote fetch, no `Secure`-breaking cookie change, no auth-gate weakening, no `*` hosts / DEBUG-True / dev-SECRET promotion beyond local; the Q11 institutional checklist stays out of staging tickets.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 37): continue the rotating phase loop (suggested: schemas, migration sequence, rollback safety, following the 21→28 cycle order). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired, P1/P2 tests added, `:1070-1094` cursor remainder read, settings hardened, `Secure`/validator flags added, `check --deploy` run recorded) and whether the gate moved. Checkpoint duties next due at iteration 40 (cumulative deltas 31–40 + gate review + docs-only PR push packaging handoffs 0031–0040); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push. This handoff (`supervisor-iteration-0036.md`) remains untracked in the working tree for packaging at the iteration-40 checkpoint into PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged — https://github.com/eliancanul/AulaLista/pull/112), never merged.
