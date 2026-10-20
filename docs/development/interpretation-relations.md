# Interpretation development: activity → session

This change improves the existing `SessionPlan`, `SessionActivity` and
`AtomicClaim(pertenece_a_sesion)` path. It adds no curricular ontology, UI,
automatic editorial approval, student feature or external model call.

## Deterministic change

- Admit `Sesión N Fecha: …` when a labelled lesson moment corroborates the
  physical block. Date text remains original; no missing day/month/year is filled.
- Admit narrowly corroborated footer continuations: either multiple planning
  metadata labels followed by an explicit activity section on the next page, or
  a dated/time-labelled footer followed by phase, purpose and moment labels.
  The next session/project/general-data block cuts this scope.
- A weekday-only partial date needs richer same-page planning metadata and an
  activity-section label; the weekday alone does not establish a unit.
- Extract top-level listed instructions inside explicit Inicio/Desarrollo/Cierre
  or Tarea sections. Preserve wrapped original text, nested substeps and quoted
  text inside an instruction. Resources, evaluation, quoted examples and metadata
  lists do not become separate activities.
- Carry the open activity-section context through an already admitted immediate
  continuation page. Do not turn an arbitrary list into a session.
- Stop a preceding activity at explicit display subheadings. Recognition of a
  campo label as a display boundary does **not** assign curricular meaning or a
  campo relationship to the task.
- Make `Actividad` a whole word; `Actividades` in a title or wrapped prose is not
  a separate activity. Avoid extracting a second activity from a listed task's
  wrapped mention of the singular word.

The shared structural verifier still uses the segmentation code. Agreement with
it is not independent semantic validation. Teacher/editorial states stay pending.

## Fixed-opportunity evaluation

`scripts/evaluate_activity_session.py` accepts independently authored exact
Unicode spans in unchanged extracted pages. It does not evaluate PDF extraction,
OCR, visual table reconstruction, pedagogical truth or teacher editing time.

Each document has original `pages`, independently assigned `sessions` with
`anchor={page,start,end,quote}`, and fixed `relations` with an `activity` span and
`session_id`. Optional `scored_pages` declares scoring scope while retaining other
pages as context. A `scope_truncated` relation measures only its visible span.

Prediction matching does not import the product session scanner. Evidence must
locate unambiguously in original page text; duplicate occurrences cannot be
resolved using the predicted parent or the gold. Only unique alignment to one
reference opportunity can receive credit. Duplicate guesses make that opportunity
incorrect, even if one guess is right. Unmatched predictions remain extras.

- Fragment association recall: correct activity-fragment → session / fixed N
- Precision: correct associations / asserted predictions, including extras
- Incorrect, omitted and explicitly abstained opportunities remain separate;
  correct + incorrect + omitted + abstained = N
- Full visible activity recovery: the full reference text is retained
- Clean full recovery: full reference text retained without outside contamination
- Text precision: matched non-whitespace source characters / all emitted source
  characters, including extras; completeness and purity are different
- Missing/zero denominators are N/A, never 100%
- Unambiguously out-of-scope context predictions are counted separately; uncertain
  source scope is retained visibly, not silently discarded

A one-token excerpt may align a fragment but cannot earn complete recovery. An
activity plus unrelated resources may be complete but cannot earn clean recovery.
Tests cover both adversarial cases.

### Development results, not held-out performance

Baseline is product commit `c787068014c9ebbe1c7eb1ead341e1182b667c0a`.
Both baseline and candidate use the same evaluator, source pages and frozen
reference per stratum. Private text and reference files are not in this repo.

| Stratum | Fixed N | Baseline correct | Candidate correct | Candidate clean full | Candidate precision |
|---|---:|---:|---:|---:|---:|
| Synthetic labelled activities, 10 documents | 12 | 6 | 12 | 12 | 12/12 |
| Synthetic listed activities, 8 documents | 11 | 1 | 11 | 11 | 11/11 |
| AI-reviewed development A, first 3 pages of 5 sources | 139 | 1 | 139 | 139 | 139/139 |
| AI-reviewed development B, pages 4–6 with pages 1–3 as context | 207 | 0 | 204 | 204 | 204/204 |

Synthetic baseline listed-activity count is also unchanged by the dated-header
repair. Development A baseline has 3 extras and 138 omissions; development B
baseline has 2 extras and 207 omissions. Candidate B has 3 omissions and no extras;
these are continued list items on the next page without a new moment label, outside
the conservative continuation admission. Neither candidate has explicit
abstentions in these strata; omission is not reported as abstention.

References A and B were frozen before the coordinator inspected their respective
product outputs. The coordinator used AI review, knew aggregate earlier findings
and the dated-header hypothesis, and is **not** a human teacher annotator. Sources
are already exposed development material from a related format family. The second
reference was built after reviewing implementation hypotheses; it is not a blind
holdout. A includes one frontmatter-only negative source; B includes one final
activity whose unseen continuation is outside its input scope. These results do
not establish 90% reliability for a curriculum, a new document family, untested
relationships or the separate final reserve.

The original frozen evaluation campaign and its baseline snapshots were not
modified. No withheld/final-reserve document was inspected.

### Reproduction using public synthetic text

```sh
python scripts/evaluate_activity_session.py
python scripts/evaluate_activity_session.py --reference tests/fixtures/interpretation/activity_session_bullets_v1.json
python scripts/evaluate_activity_session.py --product-root /path/to/unchanged/baseline
python -m pytest -q tests/test_activity_session_evaluation.py tests/test_dated_sessions_development.py tests/test_listed_activities_development.py tests/test_interpretation_shadow.py
```

Frozen synthetic SHA256 values:
- labelled: `9fb8fdc7595e24c065bfba0f8babd833d74f2eae208f2f228aaa4c8055a8b347`
- listed: `79eebb377323b3a060f5243cd9d80fa459e956a774781c1937d16b84d59399b6`

## Optional LLM boundary: synthetic shadow only

`curriculum/interpretation_shadow.py` defines a provider-neutral request/response
boundary. It is **not wired into the importer** and is disabled by default. This
version only executes an explicitly supplied `kind='synthetic_test'` test double.
An external provider is rejected even if enabled. There is no SDK, credential,
vendor choice, API call, payment, model-generated evaluation result or PDF upload.

The request contains original extracted pages **and** current claims so a future
model could find omissions rather than merely reformat existing output. The
response may propose existing `es_entidad=session` and `pertenece_a_sesion` claims,
with exact evidence and relationship-context spans. It binds both source and
extraction hashes. Unsupported predicates, dangling entities, fabricated quotes,
unknown fields, malformed or excessive output reject the response atomically.

Each proposal preserves explicit/inferred/abstained basis, rationale and alternate
session targets. An abstained relation has a null target. Every non-abstained
proposal remains `needs_human_review`; provenance validation never turns it into
`backed` and no model-supplied confidence is accepted. Live dossier inputs are
copied and never mutated.

Bounds: maximum input/output characters and claim count; no silent truncation;
one attempt by default and at most two attempts for the explicit synthetic
retryable failure. A future authorized network adapter must enforce the deadline
and monetary/token budget at transport level: the current post-return deadline
check alone cannot interrupt a blocking provider. No external adapter should be
enabled until that enforcement, specific data-transmission permission and provider
selection exist. Synthetic cost and provider latency are N/A (`None`), not zero.
Outcome status, attempts and sanitized error codes can be logged; source quotes,
provider exception strings and complete claims must not become telemetry.

A later rules/LLM/hybrid comparison must reuse fixed references, preserve omissions
and abstentions, report actual model/version/prompt, real usage and cost only when
called, and obtain an independent human reference before claiming teacher savings
or pedagogical correctness.

## Reference disputes discovered during comparison

See [reference challenges](interpretation-reference-challenges.md). In particular,
an empty date does not make session existence pedagogically false, and the frozen
labelled-activity/substeps fixture does not annotate the entire task. Its strict
score is a contract test, not an absolute semantic truth or a fair unqualified
ranking of rules against LLM interpretation. The primary fixture hashes and
opportunity counts are unchanged.

## Offline replay and bounded annex necessity

See [recorded interpretation replay](interpretation-recorded-replay.md) for the
detached v2 provenance contract, literal continuation repairs, independent v3
explicit-annex scoring and the distinction between textual mentions and
operational requirements. Historical development results above are not a new
measurement of this incremental cut.
