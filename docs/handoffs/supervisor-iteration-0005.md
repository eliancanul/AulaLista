# Supervisor iteration 0005 — tests, evidence, and acceptance matrix

Iteration: 5 | Phase focus: tests, evidence, and acceptance matrix
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

Prior memory: `supervisor-iteration-0003.md` (idempotency/dedup/ambiguity), `supervisor-iteration-0002.md` (staging join + relational model), dated handoffs `2026-09-05-01..04`, `cierre-loop`, `loop-implementacion`, `supervisor-bootstrap`. Notes: no `supervisor-iteration-0001.md` and no `supervisor-iteration-0004.md` exist on disk; no `supervisor-cumulative.md` exists — not due (10th iteration). Working-tree shape is **byte-identical in `git status` to iterations 2 and 3**: no commits, no reverts, no new relations. This pass records "no new tree evidence" and delivers the phase-focus artifact: a tests↔evidence↔acceptance matrix, not a repeated conclusion.

## Scope

Phase-focus: map every load-bearing architectural claim to (a) the test that pins it, (b) the runnable/reproducible evidence behind it, and (c) the acceptance criterion a future ready-for-agent ticket must assert. Spec only — nothing implemented, per loop rules.

## Files inspected

`CONTEXT.md`, `DESIGN.md`, `AGENTS.md`, `docs/DATABASE.md`, `docs/implementation-current.md`, `docs/teacher-flow.md`, `docs/adr/0010-staging-relacional-idempotente.md`, `docs/evidence-demo.md` (via handoff 03 summary), `docs/qr-lan-test.md` (listed), `docs/handoffs/supervisor-iteration-0002.md`, `docs/handoffs/supervisor-iteration-0003.md`, `docs/handoffs/2026-09-05-03-investigacion-evidencia.md`, `docs/handoffs/2026-09-05-04-techdebt-tests.md`, plus read-only inspection of `curriculum/views.py` (2950 lines; grep + spot lines 2301/2317/2343/2423/2428/2452-2456), `curriculum/models.py` (2038), `curriculum/staging_validation.py` (238, re-read 189-238), `curriculum/services/roadmap_cursor.py` (27), `curriculum/services/results.py` (552), `curriculum/schemas/README.md` + 3 `*.schema.json`, `tests/test_t54_staging_contracts.py` (127, full re-read), `tests/test_t24_database_contracts.py` (152, line count), `tests/test_design_contract.py` (146, read 1-40), `scripts/check_migrations.py` (53). Ran `python3 scripts/check_migrations.py` → OK; `python3 -m pytest --collect-only` → `No module named pytest` (no `.venv` in this environment), so all test claims below are by reading + file inventory (42 `test_*.py` files), not execution. `ls docs/evidence/` → only `t12-network.mmd` + `t13-common-entry-manual-test.md`; `docs/evidence/demo-viernes/` → does not exist (confirms handoff-03 finding 4).

## Findings (observed facts vs hypotheses)

1. **Tree unchanged — all iteration-2/3 line cites still current (observed).** Fact: `wc -l` gives `views.py` 2950 / `models.py` 2038 / `staging_validation.py` 238 — identical to iteration 2. `group_by_subtopic` still exact-`==` at `staging_validation.py:72-78`; producers still write title keys (consumers at `views.py:2343-2346,2423-2428` delegate to the helper); convert still positional `job.activities[int(index)]` at `views.py:2456` while remove uses `_activity_id` at `views.py:2301-2325`; `find_duplicate_groups`/`activity_content_hash` still zero call sites outside `staging_validation.py` + `test_t54` (grep confirms: only `views.py:2343,2423` import `group_by_subtopic`, never the hash/dedup pair). No drift to correct.
2. **Acceptance-matrix core (observed, the phase deliverable).** Table in §Decisions maps: title-join → no regression test pins removal (only `test_t54` pins the transitional helper + hash); idempotency key → `test_t54:108-116` pins hash, `test_t54:119-127` pins report-only; convert positional hazard → no dedicated test (gap); N+1 → claimed fixed at `models.py:1129-1146` but no named perf test cited in handoffs (gap: needs explicit t-ticket ref); cursor dedup → 7 call sites via `roadmap_cursor.py` (27 lines), no test name cited (gap); schemas v1 → `test_t54:55-105` pins runtime `full_clean`, `test_t24` (152 lines, 4 tests per handoff 04) pins legacy contracts; #57 → `scripts/check_migrations.py` green this pass (evidence, re-run OK).
3. **Test runner is not reproducible in this environment (observed).** Fact: `requirements.txt` = runtime only (Django/Wagtail/pypdf/segno); pytest lives in `requirements-dev.txt`; `python3 -m pytest` fails here. `docs/implementation-current.md:111` claims "238 pruebas" and handoff 04 counts "41 ficheros / 268 funciones"; this pass inventories 42 `test_*.py` files. Contradiction is apparent, not real: different counting methods (suite total vs `def test_` grep) and an unverifiable total without a runner. Acceptance criteria must therefore name exact test files, not a global count.
4. **Evidence gaps confirmed unchanged (observed).** Fact: `docs/evidence/` still has only the `.mmd` diagram + T13 manual checklist (T13 fields empty per handoff 03); `demo-viernes/` still absent; physical LAN test (`docs/qr-lan-test.md`, T13 two-browser WAN-off, T12 `false` physical flag) still spec-only. `docs/implementation-current.md:112-117` honestly bounds T10 (30 sequential, p95 <2s) and the `database is locked` writer limit — that honesty is the correct baseline; no ticket may claim concurrent-write support.
5. **Stale-number hazard persists (observed).** The loop prompt's own cites (`views.py:2875-2876,2959-2960`, `views.py:3504`, `models.py:1998`, `models.py:1125-1127`) remain stale pre-shrink numbers. Iterations 2–3 already published the current cites; any new ticket that copies the prompt numbers verbatim will misdirect the agent. The acceptance criteria below therefore carry a "cite current lines" gate.
6. **Overlap double-count hazard still unspecced in code (observed, carry-over).** `test_t54:126-127` asserts `exact == [[0,1]]` *and* `same_title_diff_content == [[0,1,2]]` — exact membership inside the ambiguous window is by design, but no presentation rule exists in code or `docs/DATABASE.md`. Hypothesis (unchanged from iteration 3): one merged section per title-key with per-pair badges.
7. **Canonicalization depth still under-specified (observed, carry-over).** `activity_content_hash` (`staging_validation.py:189-208`) normalizes only the two title strings via `_norm`; inner proposal text is byte-compared after `sort_keys`. Whitespace-only retries land in `same_title_diff_content` (safe but noisy). No decision recorded since iteration 3 — still needs an explicit ticket-level pick before backfill (hash values change either way).
8. **Schema-path wording still stale (observed, carry-over).** `models.py:1875` says `curriculum/schemas/v1`, directory is flat (`curriculum/schemas/*.schema.json`, no `v1/`); `schemas/README.md:3` says "`v1/` plano en esta carpeta" (ambiguous). Docs-only, still deferred per loop discipline.

## Decisions (spec only)

- The single #1 architectural change is unchanged: **ADR-0010 relational staging with idempotency** (double-write → backfill with ambiguous report → new-read → drop JSON writes). This phase adds the missing acceptance matrix so the fused #53/#98/#54 ticket is verifiable test-by-test instead of claim-by-claim.
- Acceptance-matrix (claim → pinning test → evidence → gap):

| # | Claim / invariant | Pinning test (must stay green) | Evidence artifact | Gap / ticket gate |
|---|---|---|---|---|
| A1 | Title join is transitional, `_norm` wins on migration | `test_t54` helper paths + t15/t16/t19/t20/t22 | `staging_validation.py:55-78`; `views.py:2343-2346,2423-2428` | No test asserts join removal; ticket must add relational-read test at migration time |
| A2 | Idempotency key excludes editorial state | `test_t54:108-116` | `staging_validation.py:189-208` | Zero pipeline call sites — ticket must wire 3 touchpoints as report+confirm |
| A3 | Duplicates reported, never silently merged | `test_t54:119-127` | `staging_validation.py:211-238` | Overlap presentation rule missing; ticket must spec merged-section + badges |
| A4 | Runtime schema enforcement (not test-only) | `test_t54:55-105` (`full_clean`); `test_t24` legacy | `curriculum/schemas/*.schema.json` + `models.py:1874-1896` | `save()` deliberately skips `clean()` (partials) — ticket must keep that contract |
| A5 | Convert path resolves stable identity | — (none found) | `views.py:2452-2456` positional vs `views.py:2301-2325` id-based remove | Ticket must switch convert to `_activity_id` BEFORE any dedup UI |
| A6 | No N+1 on snapshot resolution | — (needs named test ref) | `models.py:1129-1146` (`in_bulk`, fail-closed) | Ticket must cite the perf/regression test that pins this |
| A7 | Single cursor implementation | — (needs named test ref) | `roadmap_cursor.py` (27) + 7 call sites | Ticket must cite the cursor regression test |
| A8 | Migration anti-collision | `scripts/check_migrations.py` (re-run OK this pass) + `makemigrations --check` | linear numbering (handoff-04: 0001–0029) | Must run in-ticket; pytest unrunnable here so CI is the verifier |
| A9 | Design/privacy contracts hold | `test_design_contract.py` + t08/t09/t13/t14/t86 | `DESIGN.md` tokens/states; T13 checklist (empty); LAN spec-only | No ticket may claim physical-LAN or concurrent-write support (T10 bound + `locked` finding stand) |

- Methodology note for the 100th-iteration final: this matrix is the "evidence matrix" row — each future pass should update only the Gap column with a file:line citation, never rewrite the claim column without code evidence.

## Open questions

1. Human: review/commit the uncommitted Phase A–E tree on `updated-tech`? Supervisor cannot commit. (Carry-over 2→3→5.)
2. Agent-ready: recursive `_norm` on inner proposal text vs documented byte-comparison noise? Changes hash values — must be decided before backfill. (Carry-over 3→5.)
3. Agent-ready: duplicate-report surface — review-screen section vs `llm_log` entry vs backfill-command output? Draft spec (iteration 3) proposes review-screen + backfill command; human preference unconfirmed.
4. Missing-sequence: `supervisor-iteration-0001.md` and `supervisor-iteration-0004.md` do not exist; iteration numbering arrives externally (this pass told "Iteration: 5"). Should the next prompt re-confirm the counter source, or is the gap expected (e.g. failed/aborted passes)?

## Ranked recommendations

1. Wire the duplicate report into the three pipeline touchpoints (post-generate append guard, pre-topup count, pre-convert list) as **report + human confirm** per ADR-0010; exact collapses only with explicit confirm, ambiguous always side-by-side. Includes backfill command spec (recalculate hash, assign collision-free `hex8` to id-less rows, emit per-job ambiguous report, never touch `selected`/state/editorial decisions). Acceptance: matrix rows A2+A3+A4+A8.
2. Convert-path `activity_id` switch (`views.py:2452-2456` → resolve via `_activity_id`, reusing `views.py:2301-2304`) as strict prerequisite to any dedup UI. Acceptance: row A5 (new test: reorder-between-render-and-POST converts the intended draft).
3. Pin hash canonicalization depth + `_norm`-wins rule in ADR-0010 §2–§3 and `docs/DATABASE.md` in the same PR (rule #58). Acceptance: rows A1+A2 with updated hash fixtures.
4. Update #58 order to the fused sequence (#57 prerequisite → fused #53/#98/#54 → periphery #55/#56/#65) and fix the three stale `schemas/v1` wordings (`models.py:1875`, `schemas/README.md:3`, loop-implementacion handoff). Acceptance: row A4 + prompt-number hygiene gate.
5. Keep periphery (#55 streaming, #56 landing, #65 half-life) and prototypes/`evidence/demo-viernes/` out of the staging critical path; physical-LAN and concurrent-write claims stay out of every ticket until T13/physical runs exist.

## Ready-for-agent acceptance criteria (next ticket draft, not created)

- Cite current lines (`staging_validation.py:55-78,189-238`, `views.py:2301-2325,2343-2346,2423-2428,2447-2474`, `models.py:1129-1146,1874-1896`, `test_t54_staging_contracts.py:55-127`, `scripts/check_migrations.py`), never the prompt's stale pre-shrink numbers.
- Preserve inviolable contracts (human EditorialReviewer publishes; teacher activates; AI proposes only; immutable SHA256 snapshots; synthetic DemoPackage with zero pedagogical claims).
- Dedup behavior: retry of identical content appends nothing without human confirm (or collapses with explicit confirm — ticket must pick one); `exact` deduplicable only with confirm, `same_title_diff_content` side-by-side, never silently merged; backfill recalculates `content_hash`, assigns collision-free `hex8` where absent, reports ambiguities, never touches `selected`/state/editorial decisions.
- Presentation rule for overlap: one section per `(topic, sub, title)` key with per-pair `exact`/`ambiguo` badges; no double-counting across the two lists.
- Tests/evidence matrix: name exact files (t15/t16/t19/t20/t22/t24 + `test_t54` + `test_design_contract.py` as applicable), not a global count; `scripts/check_migrations.py` + `makemigrations --check` clean; `docs/DATABASE.md` updated in the same PR (rule #58); no physical-LAN or concurrent-write claims.
- Branch stays `updated-tech`; no merge, commit, or issue creation by the agent — draft issue text in Markdown only.

## Next move

Next supervisor pass (iteration 6): re-check whether the working tree changed (committed, hash wired into views, convert switched to `activity_id`, or relations added). If wired, verify the three touchpoints + report surface + matrix Gap column against this spec; if unchanged, record "no new evidence" and either draft the ADR-0010 §2–§3 precision patch (canonicalization depth + report surface + backfill artifact) or advance the rotating phase. Checkpoint duties: cumulative synthesis at iteration 10, final synthesis at iteration 100 — neither is due now.
