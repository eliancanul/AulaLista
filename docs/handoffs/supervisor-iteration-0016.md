# Supervisor iteration 0016 — security, deployment, and operational constraints

Iteration: 16 | Phase focus: security, deployment, and operational constraints
Branch at pass time: `supervisor/aulalista-docs` (NOT `updated-tech`; anomaly carries over from iterations 9–15)

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
?? scripts/check_migrations.py
?? templates/health/local_access.html
?? tests/test_t54_staging_contracts.py
```

`git diff --cached --name-only` → empty at pass start (nothing staged). Gate log tip still `b22b55b` (second slice); no third flip. HEAD unchanged since iteration 15. PR 112 (`supervisor/aulalista-docs` → `main`, docs-only, not merged) already exists — no PR duty until iteration 20.

Prior memory: `supervisor-iteration-0015.md` (A1–A9 re-verification, A5a/A5b split, traceability gap) + `-0014.md` (C1–C5 reconciliation) + `-0006.md` (security envelope baseline, re-verified here) + `supervisor-cumulative.md` (spine 2→10).

## Scope

Phase-focus: re-verify the iteration-6 security/deployment/operational envelope against current code, not against prior handoffs, and record what moved. Spec only — nothing implemented. No gate edit and no cumulative edit (both are 10th-iteration duty; next due at iteration 20). No commit/push this pass (non-checkpoint iteration).

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `aulalista/settings.py` (135, full re-read), `aulalista/urls.py` (DEBUG tail `:228-229`), `curriculum/views.py` (`teacher_required` `:125-132`, cookie grep), `curriculum/curriculum_import.py` (Ollama timeout grep), `scripts/package_macos.sh` (full head, exclusion list), `docs/handoffs/IMPLEMENTATION-GATE.md` (on-disk second slice) + `git log --oneline -3` on it; `wc -l` of `views.py` (2950) / `models.py` (2038) / `settings.py` (135) / `staging_validation.py` (238) / `services/results.py` (552) / `services/roadmap_cursor.py` (27) / `test_t54` (127); `curriculum/migrations/` tail (head still 0029); `ls -R curriculum/schemas/` (flat, no `v2/`). `pytest` unrunnable here (no `.venv`); test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **No new tree evidence (observed).** All line counts byte-identical to iterations 2–15; status differs from iteration 15 only by the new untracked `supervisor-iteration-0015.md` (last pass's own handoff). Migrations head still 0029; `schemas/` still flat; gate file untouched since `b22b55b` — the two-flip pattern stands, still no third flip. C1–C5 wording unfixed.
2. **Fail-closed comment still aspirational (observed, carry-over 6→16).** `settings.py:7-13` says "Con DEBUG=False y sin SECRET_KEY, Django debe fallar en check", but `SECRET_KEY = os.environ.get(..., "aulalista-t01-local-development-only")` (`:11-13`) unconditionally falls back — no failing code path. `DEBUG` defaults `True` (`:14-18`), `ALLOWED_HOSTS` defaults `"*"` (`:19-23`). The uncommitted diff that introduced this block (env-override + warning comment) is itself the precision upgrade; the remaining gap is comment-vs-code only. R1 wording fix still pending; human call whether to add a real guard.
3. **Hardening absence re-verified (observed).** Settings grep this pass: zero `SECURE_*`, zero `*_COOKIE_*` settings; `AUTH_PASSWORD_VALIDATORS = []` (`settings.py:107`); only `XFrameOptionsMiddleware` (`:55`). Device cookie `httponly=True, samesite="Lax"`, no `Secure` (cookie grep, one hit) — correct for `http://192.168.x` LAN, pins deployment to LAN-only HTTP. Institutional TLS/reverse-proxy remains unscoped future. `csrf_exempt` not re-grepped this pass; iteration-6 zero-hit claim carries.
4. **AuthN/authZ + LAN-explicit re-verified (observed).** `teacher_required` (`views.py:125-132`) gates on authenticated + `is_staff`; `AULALISTA_LAN_URL` explicit, never auto-detected (`settings.py:128-130`); `urls.py:228-229` serves staticfiles only under `DEBUG`. Inviolable contracts hold in docs; code-shape cites unchanged.
5. **Ollama timeout question RESOLVED (observed, the one thing that moved).** Iteration 6 left "no timeout value verified in the read window". This pass: `curriculum/curriculum_import.py` defines `CHAT_TIMEOUT_SECONDS = 180` and calls `urllib.request.urlopen(..., timeout=CHAT_TIMEOUT_SECONDS)` (`# noqa: S310 - local trusted service`). Egress stays server-side, env-pinned (`AULALISTA_OLLAMA_URL` default `localhost:11434`), teacher-triggered staging only — operator-misconfiguration risk, not student input. No ticket may claim timeout-unknown after this pass.
6. **`media/`-in-tarball still open (observed).** `scripts/package_macos.sh` excludes `.git/.venv/__pycache__/db.sqlite3*/staticfiles/dist` but NOT `media/` — teacher PDFs under `curriculum_imports/` still ship inside `aulalista-local.tar.gz`. `MEDIA_ROOT` env-overridable (`settings.py:118`). Benign for synthetic demo; purge-vs-bundle decision still required before any real-teacher packaging run.
7. **Single-process limits re-verified (observed).** SQLite WAL + `timeout: 5` + `busy_timeout=5000` (`settings.py:81-96`); `LocMemCache` with "shared cache required before multiple workers" (`:98-105`). Any gunicorn/multi-worker/background-thread proposal still needs cache + concurrency + 90-min-valve analysis or rejection. Upload-validation depth (filename-only per iteration 6) not re-read this pass; carry-over.
8. **Fused-decision spine unchanged (observed).** #53/#98/#54 as ONE decision per ADR-0010, #57 prerequisite, #58 stale, #55/#56/#65 peripheral. Gate traceability gap from iteration 15 (on-disk gate cites `coding-41560047f83c.md`, unreachable from this branch) persists — not re-verified by `ls` this pass, carried as standing finding.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (M0→M4 per iteration 7, Steps 0–4 per iteration 8, queue R1–R5 per iteration 9, HOLD + cumulative per iteration 10, 2/6 → 2.5/6 scorecard per iterations 11–15, C1–C5 per iteration 14).
- **Gate: no edit this pass (10th-iteration duty).** Assessment only — no third flip observed; iteration-15 2.5/6 scorecard carries. Iteration 20 must adopt a human-signed amendment allowing stacked-slice updates (with vendored evidence or exact cross-branch refs) or revert to `HOLD`.
- **Envelope contribution (this pass, no code):** iteration-6 posture verdict re-confirmed — **acceptable for the local synthetic-demo node, not cleared for institutional deployment**. One precision gain: Ollama timeout is 180s (Finding 5), closing iteration-6 open item. All other envelope rows carry forward unchanged.
- **Methodology note for the 100th-iteration final:** this handoff refreshes the "security/deployment/operational constraints" evidence-matrix row — future passes update only file:line cites and the Gap column, never the posture verdict without code evidence.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree? (Carry-over 2→16.) Blocks any future supervisor `READY`.
2. Gate provenance: `498a4df` AND `b22b55b` both flipped the gate off-cycle. Deliberate stacked-slice strategy or accident? Loop rule needs a human-signed amendment at iteration 20. (Carry-over 11→16, confirmed pattern.)
3. Traceability (carry-over 15→16): vendor `coding-41560047f83c.md` + first-slice diff onto the supervisor branch, or record exact cross-branch refs + PR 113 URL in the gate?
4. Agent-ready (carry-over 6→16, narrowed): correct `settings.py:7-10` fail-closed comment to match the fallback code, or add a real startup/check guard failing without `AULALISTA_SECRET_KEY` when `DEBUG=False`? Human call — changes deploy behavior.
5. Agent-ready (carry-over 6→16): `media/` in `package_macos.sh` — purge before packaging or bundle intentionally?
6. Agent-ready (carry-over 3→16, citable as C1): recursive `_norm` on inner proposal text vs outer-keys-only (`staging_validation.py:25-26` vs `:203-205` vs `:232` vs ADR-0010 §Decisión-2)?
7. Agent-ready (carry-over 5→16): duplicate-report surface — review-screen section vs `llm_log` vs backfill output? Assumed review-screen + pre-convert list.
8. Agent-ready (carry-over 7→16): M4 JSON-export artifact shape (per-job dump vs snapshot-table export)?
9. Evidence debt (carry-over 11→16): name the duplicated-cursor pair with current lines or drop the claim from the loop prompt.
10. Missing-sequence: `supervisor-iteration-0001.md` / `-0004.md` never existed; numbering arrives externally. Accept gaps.

## Ranked recommendations

1. At iteration 20, resolve the gate cleanly: adopt the two stacked slices verbatim WITH vendored evidence (or exact cross-branch refs + PR 113 URL) + a clean `updated-tech` base ref + answered picks, or revert to `HOLD` with the 2.5/6 scorecard. Do not let a third off-cycle flip accumulate.
2. Land the five R1 doc-precision patches (C1–C5 from iteration 14) plus the `settings.py:7-10` fail-closed wording fix (Finding 2) as docs-only PR content; backfill wording depends on C1.
3. Upgrade #98 with the iteration-9 §Draft body + iteration-12 triple-join cite + iteration-13/14 `_norm` asymmetry (C1) + iteration-15 A5a/A5b split + this pass's timeout cite (`CHAT_TIMEOUT_SECONDS = 180`) before any coding lane starts; keep #53/#54/#57 without `ready-for-agent`; update #58 epic body docs-only to the fused order.
4. Keep periphery (#55/#56/#65, Dirección A/B #95/#103/#104/#107, #97, multi-worker/TLS/institutional-deploy, prototypes) off the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.
5. Refresh the loop prompt with the triple-join cite table + idempotency cite table + A5a/A5b split + C1–C5 table + this pass's envelope cites (`settings.py:7-23,81-107,118,128-135`; `views.py:125-132`; `urls.py:228-229`; `package_macos.sh` exclusions; `CHAT_TIMEOUT_SECONDS = 180`).

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (this pass: `settings.py:7-23` secrets/hosts, `:55` XFrame, `:81-96` SQLite WAL, `:98-105` LocMemCache, `:107` empty validators, `:118` MEDIA_ROOT, `:128-135` LAN/LLM; `views.py:125-132` teacher gate; `urls.py:228-229` DEBUG-static; `package_macos.sh` exclusion list incl. missing `media/`; `curriculum_import.py` `CHAT_TIMEOUT_SECONDS = 180` + `urlopen` timeout; iteration-15 staging cites carry: convert `views.py:2446-2475` positional `:2456`, template `tutor_import_detail.html:148` `item.index` vs `:157` `item.id`, hash `staging_validation.py:189-208`, `_norm` `:25-26`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the envelopes from iteration 6 (LAN-only HTTP, staff-gated pipeline, sealed cookies, single-process SQLite, no new egress) + iterations 5/7/8 (A1–A9 with A5a/A5b, M0→M4 + rollback, Steps 0–4 S1-fused-with-M3).
- Deploy gate: any deploy-flavored change names `AULALISTA_SECRET_KEY` + `AULALISTA_DEBUG=False` + explicit `AULALISTA_ALLOWED_HOSTS` + `manage.py check --deploy`; no ticket relies on the fail-closed comment as enforcement (Finding 2).
- Queue discipline R1→R2(A5a+A5b)→R3(M4 excluded)→R4; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` in the same PR iff a model/pipeline line moved (rule #58); gate evidence reachable from the gate's own branch.
- No merge, commit, or issue creation by the agent — draft issue text in Markdown only; label changes are human-applied.

## Next move

Next supervisor pass (iteration 17): re-check whether the working tree changed (Phase A–E committed, C1–C5 wording fixed, fail-closed comment fixed, A5b template switched, head past 0029) and whether the gate file moved a third time (a third off-cycle flip forces the rule-amendment question at iteration 20). If moved, verify the touched R/M/S step against the cumulative synthesis + iteration-5 matrix + this envelope; if unchanged, record "no new evidence" and advance the rotating phase (suggested: report-surface pick or M4-export shape, the two least-specified open questions). Checkpoint duties next due at iteration 20 (cumulative deltas + gate review + docs-only PR); final synthesis at iteration 100 — neither is due now.
