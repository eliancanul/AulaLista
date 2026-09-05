# Supervisor iteration 0026 — security, deployment, and operational constraints

Iteration: 26 | Phase focus: security, deployment, and operational constraints
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–25)

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
?? docs/handoffs/supervisor-iteration-0021.md
?? docs/handoffs/supervisor-iteration-0022.md
?? docs/handoffs/supervisor-iteration-0023.md
?? docs/handoffs/supervisor-iteration-0024.md
?? docs/handoffs/supervisor-iteration-0025.md
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). HEAD `cc95426` (iteration-20 PR-record append); gate log tip still `606aa64` for `IMPLEMENTATION-GATE.md` (iteration-20 HOLD revert) — no third flip observed. `git diff --stat` working-tree shape unchanged: 7 files, +209/−716, `views.py` −808-line-dominant. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) stands — no PR duty until iteration 30.

Prior memory: `supervisor-iteration-0025.md` (A1–A9 re-verification + P1/P2 pending rows, R1 packaging for 30) + `-0024.md` (C1–C5 three-site sharpening) + `-0023.md` (idempotency/dedup, C1 draft pick) + `-0016.md` (last security-envelope pass; Ollama timeout cite corrected at iteration 20 to `curriculum/curriculum_import.py:23`) + `supervisor-cumulative.md` (spine 2→20) + `IMPLEMENTATION-GATE.md` (`STATUS: HOLD`).

## Scope

Phase-focus: re-verify the iteration-6/16 security/deployment/operational envelope against current code, not against prior handoffs. Spec only — nothing implemented, no issue created/edited/labeled. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 30). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`supervisor-iteration-0025.md` (full) + `-0016.md` envelope claims (via cumulative §0016) + `IMPLEMENTATION-GATE.md` + `supervisor-cumulative.md` (carried, not edited); `aulalista/settings.py:1-135` (full re-read this pass); `curriculum/views.py:100-169` (TTL + `_safe_teacher_next` + `teacher_required` + `_seal/_unseal`, re-read); `curriculum/practice.py:50-90` (capability seal/verify, re-read); `curriculum/curriculum_import.py:21-23,72,254-296` (Ollama URL + `CHAT_TIMEOUT_SECONDS` + `urlopen` call site, re-read); `aulalista/urls.py:228` (DEBUG-only staticfiles); `scripts/run_wsgi.py` (full) + `scripts/package_macos.sh` + `scripts/verify_local_package.py:33-40` (rg-scoped); `docs/adr/0004-provisional-local-runtime-baseline.md` (full) + `docs/adr/0010-staging-relacional-idempotente.md` §Decisión-4 (contracts, re-read); `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27); `ls curriculum/migrations/` tail (head still 0029); `ls tests/test_*.py | wc -l` → 42; `python3 scripts/check_migrations.py` → OK (re-run this pass); `rg` for auth decorators, signing/cookies, egress/timeout, `SESSION_COOKIE|SECURE_` in settings; `git log --oneline -3`, gate log, `git diff --stat`, `git diff --cached --name-only`. `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** Every `wc -l` count byte-identical to iterations 2–25; migrations head still 0029; `schemas/` still flat (README + 3 `.schema.json`, no `v2/`); `check_migrations.py` OK; 42 test files; `git diff --stat` identical (+209/−716); status differs from iteration 25 only by the addition of untracked `supervisor-iteration-0025.md` (the expected own-handoff delta, now `supervisor-iteration-0026.md` pending). No Phase A–E commit, no C1–C5 wording fix, no settings hardening, no new egress, no new service module.
2. **Secrets/debug/allowed-hosts posture re-verified (observed — phase deliverable).** `settings.py:7-13` dev-default `SECRET_KEY` with `AULALISTA_SECRET_KEY` override + deploy comment; `:14-18` `DEBUG` env-gated, default True; `:19-23` `ALLOWED_HOSTS` default `"*"`, env-overridable. Uncommitted diff vs HEAD confirms this block IS the Phase-A–E working-tree change (was hardcoded `SECRET_KEY` + `DEBUG=True` at HEAD) — an improvement in configurability, still dev-open by default. No `check --deploy` enforcement in code, only the comment at `:10`. No `SESSION_COOKIE_*` / `CSRF_COOKIE_*` / `SECURE_SSL_*` / `SECURE_HSTS_*` lines anywhere in `settings.py` (rg confirms; `AUTH_PASSWORD_VALIDATORS = []` at `:107` observed). Middleware keeps `SecurityMiddleware` + `CsrfViewMiddleware` + `XFrameOptionsMiddleware` (`:48-56`). Hypothesis: acceptable for the LAN-local single-node demo; must not be presented as institutional hardening — `implementation-current.md:141-148` already lists "revisar operación, seguridad y endurecimiento antes de cualquier despliegue institucional" as pending.
3. **Staff-gating + safe-next re-verified (observed; corrects naive grep).** A bare `rg` for `staff_member_required|login_required` returns zero hits, but the actual boundary is the custom `teacher_required` decorator (`views.py:125-142`: `is_authenticated` → `redirect_to_login(_safe_teacher_next)`, then `is_staff` + `is_active` → `HttpResponseForbidden`), with `_safe_teacher_next` (`:106-122`) constraining `next` to a local path via `url_has_allowed_host_and_scheme`. Applied broadly (`:517,:599,:675,:687,…` — 20+ sites observed). `LOGIN_URL = "/cms/login/"` (`settings.py:122-124`) reuses Wagtail login. No change since iteration 16; envelope claim "staff-gated pipeline" holds at the decorator level.
4. **Sealed device/practice cookies re-verified (observed).** `_seal/_unseal` (`views.py:158-169`: `signing.dumps/loads` with per-salt + `max_age`, `BadSignature/SignatureExpired/TypeError/ValueError` → `None`) and `practice.py:58-90` capability seal/verify (`PRACTICE_CAPABILITY_SALT`, same swallow-to-`None` shape). TTLs at `views.py:100-103` (`LOCAL_SESSION_TTL = 12h`, turn/device/survey TTLs alias it). Envelope claim "sealed cookies" holds; no `SESSION_COOKIE_*` hardening observed (see finding 2).
5. **Single-process SQLite + cache envelope re-verified (observed).** `settings.py:81-96` WAL + `synchronous=NORMAL` + `timeout: 5` + `busy_timeout=5000`; `:98-105` `LocMemCache` with in-code comment "required before deploying multiple workers or nodes". `scripts/run_wsgi.py` is a stdlib `ThreadingWSGIServer` (threads, single process; default `--host 0.0.0.0`, loopback opt-out documented). `implementation-current.md:112-117` still admits `database table is locked` on the threaded writer probe — not hidden, not claimed as supported. Envelope claim "single-process SQLite" holds; no multi-worker/TLS claim may ride any ticket.
6. **Egress surface re-verified — Ollama only, student path clean (observed).** Sole runtime egress is `curriculum/curriculum_import.py:272-296` (`urllib.request.urlopen(data, timeout=CHAT_TIMEOUT_SECONDS)` to `AULALISTA_OLLAMA_URL`, default `http://localhost:11434` at `:21`, `CHAT_TIMEOUT_SECONDS = 180` at `:23`, env overrides at `settings.py:134-135`). `implementation-current.md:13-15` confines LLM to staging proposals; student/correction/publish never use it. `scripts/verify_local_package.py:35` dials only `127.0.0.1`; `run_evidence_demo.py:166` blocks `urlopen` during the synthetic demo. No CDN/fonts/fetch per `DESIGN.md:94-95`. `aulalista/urls.py:228` serves staticfiles only under `DEBUG`. No new egress observed.
7. **LAN/operational constraints re-verified (observed).** `AULALISTA_LAN_URL` explicit, no interface auto-detect (`settings.py:128-130`); `WAGTAILADMIN_BASE_URL = "http://localhost:8000"` (`:127`) is a localhost default. `package_macos.sh` builds `aulalista-local.tar.gz` excluding `staticfiles`; `MEDIA_ROOT` env-overridable (`settings.py:117-118`). Physical two-phone WAN-disconnected LAN test still pending (`implementation-current.md:103-107` + `docs/qr-lan-test.md`); T13 checklist empty. No ticket may claim physical-LAN or concurrent-write support.
8. **Gate: no edit, HOLD carries (decision by rule).** No third flip (log tip `606aa64`); iteration-20 2.5/6 scorecard and HOLD stand. Gate review + cumulative deltas (21–30) + docs-only PR push next due at iteration 30, not now.
9. **Fused-decision spine unchanged (observed + carry).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. #98 stays the sole staging-path `ready-for-agent` candidate at 0/7 (iteration-19 rubric, carried — issue bodies not re-read, tree unchanged so no re-grade possible). C1–C5 + P1/P2 rows from iterations 23–25 carry unmodified (spot-checked C1 docstring line `staging_validation.py:192` unchanged; full matrix re-verification was iteration 25's job, not repeated here).

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4, Steps 0–4 S1-fused-with-M3, queue R1–R5, HOLD-default gate).
- **No gate edit, no cumulative edit, no PR this pass** — non-checkpoint iteration per loop rules.
- **Envelope contribution (this pass):** LAN-only HTTP, staff-gated pipeline (`teacher_required` + safe-next), sealed device/practice cookies (12h TTL), single-process SQLite (WAL + finite timeouts, `LocMemCache`), Ollama-only egress with 180s timeout, no new egress, `media/`-in-tarball posture — all re-verified against current lines; dev-default secrets/DEBUG/`*`-hosts + empty password validators + absent cookie/SECURE flags recorded as the explicit pre-institutional hardening gap (already pending at `implementation-current.md:141-148`).
- **Cite discipline re-affirmed:** current lines only (settings `:7-23,:48-56,:81-105,:107,:117-135`; `views.py:100-169` + decorator sites `:517…`; `practice.py:58-90`; `curriculum_import.py:21-23,72,254-296`; `urls.py:228`; prompt's stale pre-shrink numbers remain superseded).

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→26.) Blocks any future supervisor `READY`.
2. Loop rule: human-signed amendment legitimizing stacked-slice off-cycle gate updates, or confirm HOLD-only-outside-checkpoints? Two unamended flips is a pattern. (Carry-over 11→26.)
3. Traceability: vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate? (Carry-over 15→26.)
4. Agent-ready (C1, draft pick at 23, three-site at 24, P1/P2 rows at 25): confirm `_norm`-join + outer-keys-only hash, or take the exact-join-intentional alternative with inverted P1? Precedes backfill AND staging-adjacent seams. (Carry-over 3→26.)
5. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Recommended review-screen + pre-convert list, `llm_log` audit copy. Enforcement gap until picked; P2 has nowhere to render without it. (Carry-over 5→26.)
6. Agent-ready: M4 JSON-export artifact shape (per-job dump vs snapshot-table export)? (Carry-over 7→26.)
7. Agent-ready (C3): `models.py:1875` docstring path — flat `*.schema.json` wording? (Carry-over 14→26.)
8. Draft-quality: should the #98 upgrade ride as R1-doc-precision content inside the docs-only PR, or as separate drafted-but-uncreated ticket text? (Carry-over 19→26.)
9. Evidence debt: name the duplicated-cursor pair with current lines or drop the claim from the loop prompt. (Carry-over 11→26.)
10. Seam-spec: pin S5/S4/S2 to current `views.py` def spans or retire S-numbers and re-derive post-shrink? (Carry-over 18→26.)
11. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.
12. Security (new this pass): before any institutional deploy, who signs the hardening checklist (env SECRET/DEBUG/hosts, password validators, cookie/SECURE flags, `check --deploy` clean, physical LAN run)? Out of scope for the staging lane; record owner + runbook location.

## Ranked recommendations

1. Keep `STATUS: HOLD` until all six flip conditions hold simultaneously; the parallel coding lane does nothing while the gate is `HOLD` or absent.
2. Land the five R1 doc-precision patches (C1 three-site + draft pick, C2–C5) plus the P1/P2 pending-row names as docs-only PR content at iteration 30; the #98 upgrade depends on C1, the `models.py` docstring on C3, wiring on P1/P2 + report surface. This pass adds no new R1 item — the envelope re-verification confirms R1 stays docs-only with no code touch.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + C1 pick (both halves, iteration 23) + iteration-15 A5a/A5b split + corrected timeout cite (`curriculum_import.py:23`) + iteration-18 seam guard + iteration-23 ambiguity-enforcement surface + iteration-25 P1/P2 rows before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist. Institutional hardening (finding 2 + question 12) is an explicit non-goal of the staging lane.
5. Refresh the loop prompt with the qualified #98 sentence, current line cites (envelope: `settings.py:7-23,:81-105`; `views.py:106-169`; `practice.py:58-90`; `curriculum_import.py:21-23`; staging: join `:76-77`, writers `:2221-2222/:2383-2384`, hash `:189-208`, zero-wiring count, title key `:232`, template `:148` vs `:157`, convert `:2456`), the A5a/A5b split, the P1/P2 pending rows, and the 7-slot draft rubric from iteration 19.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `views.py` 2950 / `models.py` 2038 / `settings.py` 135; envelope `settings.py:7-23,:48-56,:81-105,:107,:117-135`, `views.py:100-169` + decorator sites, `practice.py:58-90`, `curriculum_import.py:21-23,72,254-296`, `urls.py:228`; staging hash `:189-208`, dedup `:211-238`, join `:76-77`, writers `views.py:2221-2222/:2383-2384`, callers `:2006/:2428`, `_activity_id` `:2301`, remove `:2317`, grouped `:2420-2444`, convert `:2446-2475` positional `:2456`; template `item.index :148` vs `item.id :157`; `models.py:1130` `in_bulk`, `:1875` C3 path caveat; `schemas/` flat; migrations head 0029; 42 test files; ADR-0010 with C1 caveat; `DATABASE.md:103-105` C2 caveat; `implementation-current.md:3-6` C4 caveat; ADR-0006 `:29` C5 caveat), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and envelopes from iterations 5/6/7/8 (A1–A9 with A5a/A5b + P1/P2 pending, LAN-only + staff-gated + sealed cookies + single-process SQLite + no new egress, M0→M4 + per-step rollback, Steps 0–4 S1-fused-with-M3).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; 7-slot draft completeness; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- Ambiguity rule explicit: `exact` → dedup candidate, `same_title_diff_content` → listed separately for human decision, never silent merge; named surface + P1 (join-agreement) + P2 (same-title-separation) required before wiring.
- Security scope explicit: staging slices touch no secrets/cookies/auth/egress surface; institutional hardening travels in a separate human-owned ticket with a physical-LAN + `check --deploy` runbook.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 27): resume the rotating phase loop (suggested: schemas/migration M0→M4 rollback re-verification, or god-files/service-seams re-check). Re-check whether the working tree changed (Phase A–E committed, C1–C5 fixed, A5b template switched, head past 0029, `v2/` appeared, hash wired into the pipeline, P1/P2 tests added, settings hardened) and whether the gate moved a third time. Checkpoint duties next due at iteration 30 (cumulative deltas 21–30 + gate review + docs-only PR push packaging handoffs 0021–0030); final synthesis at iteration 100 — neither is due now.

## PR record

- Non-checkpoint iteration: no staging, no commit, no push, no new PR. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, OPEN, unmerged) untouched this pass.
- This handoff (`supervisor-iteration-0026.md`) remains untracked until the iteration-30 checkpoint packages it with 21–30 per the docs-only PR rule.
