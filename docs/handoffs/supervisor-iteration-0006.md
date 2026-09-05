# Supervisor iteration 0006 — security, deployment, and operational constraints

Iteration: 6 | Phase focus: security, deployment, and operational constraints
Branch: `updated-tech` (uncommitted working tree; no commit/merge performed)

`git status --short --branch` at pass time:

```text
## updated-tech...origin/main
 M aulalista/settings.py
 M curriculum/models.py
 M curriculum/views.py
 M docs/DATABASE.md
RM docs/adr/0007-pseudonymous-results-and-classroom-retention.md -> docs/adr/0009-pseudonymous-results-and-classroom-retention.md
 M docs/implementation-current.md
 M docs/teacher-flow.md
R  health/templates/health/local_access.html -> templates/health/local_access.html
?? .DS_Store
?? curriculum/schemas/
?? curriculum/services/
?? curriculum/staging_validation.py
?? docs/.DS_Store
?? docs/adr/0010-staging-relacional-idempotente.md
?? docs/handoffs/
?? scripts/check_migrations.py
?? tests/test_t54_staging_contracts.py
```

Prior memory: `supervisor-iteration-0005.md` (tests/evidence matrix), `-0003.md` (idempotency/ambiguity), `-0002.md` (staging join + relational model), dated handoffs `2026-09-05-01..04`, `cierre-loop`, `loop-implementacion`, `supervisor-bootstrap`. Notes: no `supervisor-iteration-0001.md` / `-0004.md` and no `supervisor-cumulative.md` exist on disk; not due (10th iteration). Working-tree shape is **byte-identical in `git status` to iterations 2, 3, and 5**, and line counts are unchanged (`views.py` 2950 / `models.py` 2038 / `settings.py` 135 / `staging_validation.py` 238). This pass records "no new tree evidence" and delivers the phase-focus artifact: a security/deployment/operations constraint map, not a repeated conclusion.

## Scope

Phase-focus: enumerate every load-bearing security, deployment, and operational constraint a future ready-for-agent ticket must respect — secrets/debug/hosts, authN/authZ, cookies/CSRF, upload handling, LAN-only operation, Ollama egress, SQLite concurrency, cache/process model, packaging — with exact file:line evidence. Spec only — nothing implemented, per loop rules.

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0004-provisional-local-runtime-baseline.md`, `docs/adr/0005-active-session-privacy-surfaces.md`, `docs/adr/0009-pseudonymous-results-and-classroom-retention.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `aulalista/settings.py` (135, full), `aulalista/urls.py:210-229` (DEBUG static tail), `curriculum/views.py:120-249` (`teacher_required`, sealed device cookie, join entry), `curriculum/models.py:1740-1809` (PDF sanitizer + `CurriculumImportJob`), `curriculum/curriculum_import.py:60-119,272-296` (Ollama call site), `scripts/run_wsgi.py` (42), `scripts/verify_local_package.py` (71), `scripts/package_macos.sh` (27), `requirements.txt` (4 pinned), plus read-only greps (secrets/cookies/auth/upload/Ollama) across `curriculum/` and `aulalista/`. Ran `python3 scripts/check_migrations.py` → OK. `pytest` unrunnable here (runtime-only env, no `.venv`), so all test claims are by reading.

## Findings (observed facts vs hypotheses)

1. **Fail-closed comment overclaims; code always supplies a default key (observed, precision fix needed).** Fact: `settings.py:7-13` comments that "Con DEBUG=False y sin SECRET_KEY, Django debe fallar en check", but `SECRET_KEY = os.environ.get("AULALISTA_SECRET_KEY", "aulalista-t01-local-development-only")` unconditionally falls back — there is no code path that fails without the env var. `DEBUG` defaults `True` (`:14-18`), `ALLOWED_HOSTS` defaults `"*"` (`:19-23`). Local-node posture is acceptable and honestly commented ("solo para desarrollo local"), but the fail-closed sentence is aspirational, not enforced. Any ticket copying the comment as a guarantee will mislead.
2. **No transport/hardening settings exist — correct for HTTP LAN, must stay documented as a constraint (observed).** Fact: grep finds zero `SECURE_*`, `SESSION_COOKIE_*`, `CSRF_COOKIE_*`, `SECRET_FALLBACKS` in settings; `AUTH_PASSWORD_VALIDATORS = []` (`settings.py:107`); only `XFrameOptionsMiddleware` (`:55`). Device cookie is `httponly=True, samesite="Lax"`, no `Secure` (`views.py:173-176`) — correct for a `http://192.168.x` LAN node where `Secure` would break the flow, but it pins the deployment to LAN-only HTTP. Institutional deploy behind TLS/reverse-proxy is an unscoped future, not a current capability.
3. **AuthN/authZ shape verified, no bypass found (observed).** Fact: `teacher_required` (`views.py:125-142`) gates teacher ops on authenticated + `is_staff` + `is_active`, else redirect-to-login or 403; ownership scoping at `models.py:2015,2022-2030`; session-sensitive routes require the preparing teacher (ADR-0009 §6); mutations use `require_POST`/`require_http_methods` throughout (`views.py:33,225,440,477,1099,1150,1171,1319,1399,1460,1492,2747,2789,2848`); zero `csrf_exempt` hits repo-wide; projection surface is deliberately unauthenticated showing only count/QR/link per ADR-0005 §2. Inviolable contracts hold in code, not just docs.
4. **Upload hardening is filename-only (observed, gap for a future ticket).** Fact: `curriculum_import_pdf_path` sanitizes stem (NFKC, whitespace collapse, strip emoji/control, truncate, `curriculo` fallback) at `models.py:1740-1757`; `pdf = FileField(upload_to=...)` at `:1786-1789`. No MIME-type, magic-byte, or size-cap check was found in the inspected range/grep. Hypothesis: acceptable for a staff-only local upload, but a ticket should state the assumption explicitly (staff-only, local disk) rather than leave it implicit.
5. **Packaging ships `media/` but excludes `db.sqlite3` (observed, privacy-relevant).** Fact: `scripts/package_macos.sh:12-25` excludes `.git/.venv/pytest_cache/__pycache__/db.sqlite3*/staticfiles/dist` but does **not** exclude `media/` — teacher-uploaded curriculum PDFs under `curriculum_imports/` travel inside `aulalista-local.tar.gz`. `MEDIA_ROOT` is env-overridable (`settings.py:118`). For a synthetic-demo node this is benign; before any real-teacher packaging run, the spec must say whether `media/` is purged or intentionally bundled.
6. **Ollama egress is server-side but env-pinned, not user-pinned (observed, low SSRF).** Fact: `curriculum_import.py:72` resolves `AULALISTA_OLLAMA_URL` from settings/env (default `localhost:11434`); `urllib.request.urlopen` at `:272-296` with `# noqa: S310 - local trusted service`. Only teacher-triggered staging calls it; student/grading/publishing never touch LLM (matches `implementation-current.md`). Risk is operator-misconfiguration, not student input. Note: no timeout value was verified in the read window — a ticket touching this path should cite it.
7. **LAN-only operation is correctly explicit (observed).** Fact: `AULALISTA_LAN_URL` explicit, never auto-detected (`settings.py:128-130`); QR/URL surfaces reuse the same join link; `urls.py:228-229` serves staticfiles only under `DEBUG`; `run_wsgi.py:18` defaults `--host 0.0.0.0` with an explicit loopback opt-out comment; `verify_local_package.py` probes loopback only (`127.0.0.1`, ephemeral port, `/student/`). `DESIGN.md` bans CDN/WAN/fetch for the local flow. No ticket may claim auto-discovery, public DNS, or WAN operation.
8. **Single-process/single-node limits are honest and load-bearing (observed).** Fact: SQLite WAL + `timeout: 5` + `busy_timeout=5000` (`settings.py:81-96`); `LocMemCache` with "shared cache required before multiple workers" comment (`:98-105`); `run_wsgi.py` is `ThreadingMixIn` over stdlib wsgiref (threads, one process); `implementation-current.md:112-117` bounds T10 (30 sequential, p95 <2s) and records `database is locked` on concurrent writers as a non-hidden limit. ADR-0004 keeps SQLite until a measured 30-client loss. Consequence: any ticket proposing gunicorn workers, multi-node, or background LLM threads must carry a cache + SQLite-concurrency + 90-min-valve (`DATABASE.md` progress section) analysis, or be rejected.
9. **Dependency surface is minimal and pinned (observed).** Fact: `requirements.txt` = 4 lines (Django 5.2.9, Wagtail 7.4.3, pypdf, segno); pytest confined to `requirements-dev.txt` per `DATABASE.md` conventions; `requirements.lock` hash-pinned exists. No new dependency may enter the staging/security path without invalidating the offline story.
10. **Stale-number hazard persists (observed, carry-over 2→3→5).** The loop prompt's cites (`views.py:2875-2876,2959-2960`, `views.py:3504`, `models.py:1998`, `models.py:1125-1127`) remain pre-shrink numbers. Current cites are §Files-inspected lines above. Every future ticket must cite current lines.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (double-write → backfill with ambiguous report → new-read → drop JSON writes). This phase adds the deployment/security envelope that change must fit inside: LAN-only HTTP, staff-gated pipeline, sealed device cookies, explicit LAN base, single-process SQLite, no new egress, no `media/` leakage.
- Security posture verdict: **acceptable for the local synthetic-demo node, not cleared for institutional deployment.** The gaps (default SECRET_KEY fallback, `ALLOWED_HOSTS=*`, empty password validators, no cookie `Secure`, filename-only upload validation, `media/` in tarball) are all consistent with a MacBook-Air LAN demo and all documented in code comments — but the fail-closed comment (finding 1) must be corrected before anyone relies on it, and the deploy gate (`AULALISTA_SECRET_KEY` + `AULALISTA_DEBUG=False` + explicit hosts, plus `manage.py check --deploy`) must be a named acceptance item on any deploy-flavored ticket.
- Methodology note for the 100th-iteration final: this handoff is the "security/deployment/operational constraints" row of the evidence matrix — future passes update only file:line cites and the Gap column, never the posture verdict without code evidence.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree on `updated-tech`? Supervisor cannot commit. (Carry-over 2→3→5→6.)
2. Agent-ready: correct the `settings.py:7-10` fail-closed comment to match the code (warn, not fail), or add a startup/check-time guard that actually fails without `AULALISTA_SECRET_KEY` when `DEBUG=False`? Changes deploy behavior — human call. (New this pass.)
3. Agent-ready: `media/` in `package_macos.sh` — purge before packaging or bundle intentionally? Privacy-relevant once real teacher PDFs exist. (New this pass.)
4. Agent-ready: upload validation depth (MIME/magic/size) — state staff-only/local-disk assumption, or add checks? (New this pass.)
5. Missing-sequence: `supervisor-iteration-0001.md` and `-0004.md` do not exist; numbering arrives externally. Confirm counter source or accept gaps? (Carry-over 5→6.)

## Ranked recommendations

1. Wire the duplicate report into the three pipeline touchpoints (post-generate append guard, pre-topup count, pre-convert list) as **report + human confirm** per ADR-0010, inside the envelope above: staff-only surfaces, no new egress, single-process safe, `scripts/check_migrations.py` + `makemigrations --check` green. Acceptance: iteration-5 matrix rows A2+A3+A4+A8.
2. Convert-path `activity_id` switch (`views.py:2455-2456` → resolve via `_activity_id`, reusing `views.py:2301-2304`) as strict prerequisite to any dedup UI. Acceptance: iteration-5 row A5.
3. Precision patch (docs + comment only, no behavior change): fix `settings.py:7-10` fail-closed wording to match the fallback code, canonicalize the three stale `schemas/v1` wordings (`models.py:1875`, `schemas/README.md:3`, loop-implementacion handoff), and document the `media/`-in-tarball + filename-only-upload assumptions. Acceptance: iteration-5 rows A1+A4 + prompt-number hygiene gate.
4. Update #58 order to the fused sequence (#57 prerequisite → fused #53/#98/#54 → periphery #55/#56/#65).
5. Keep periphery (#55 streaming, #56 landing, #65 half-life), multi-worker/TLS/institutional-deploy proposals, and prototypes/`evidence/demo-viernes/` out of the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (`settings.py:7-23,81-105,107,118,128-135`, `views.py:125-142,158-220,225-249`, `models.py:1740-1809,2015-2030`, `curriculum_import.py:71-76,272-296`, `scripts/run_wsgi.py`, `scripts/package_macos.sh:12-25`, `scripts/check_migrations.py`, `staging_validation.py:55-78,189-238`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims) and the deployment envelope (LAN-only HTTP; explicit `AULALISTA_LAN_URL`; no CDN/WAN/fetch; no `csrf_exempt`; POST+CSRF mutations; projection shows count/QR/link only; device cookie `httponly`+`Lax`, no `Secure` unless the transport story changes).
- Deploy gate: any deploy-flavored change names `AULALISTA_SECRET_KEY` + `AULALISTA_DEBUG=False` + explicit `AULALISTA_ALLOWED_HOSTS` + `manage.py check --deploy`; no ticket relies on the current fail-closed comment as enforcement.
- Tests/evidence: name exact files (t15/t16/t19/t20/t22/t24 + `test_t54` + `test_design_contract.py` as applicable), not a global count; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` updated in the same PR (rule #58); no physical-LAN or concurrent-write claims.
- Branch stays `updated-tech`; no merge, commit, or issue creation by the agent — draft issue text in Markdown only.

## Next move

Next supervisor pass (iteration 7): re-check whether the working tree changed (committed, hash wired into views, convert switched to `activity_id`, `settings.py:7-10` wording fixed, or relations added). If wired, verify the three touchpoints + report surface + deployment envelope against the iteration-5 matrix and this constraint map; if unchanged, record "no new evidence" and advance the rotating phase. Checkpoint duties: cumulative synthesis at iteration 10, final synthesis at iteration 100 — neither is due now.
