# Recorded interpretation replay: offline review only

`scripts/replay_interpretation.py` replays already-recorded activity/session or
activity/annex JSON responses. It imports no provider, product interpreter,
importer or database and makes no network calls. Its output is a detached proposal
file, never applied to a live dossier. Private recordings and source text do not
belong in this repository; the tests are entirely synthetic.

## Integrity and evidence

The caller supplies exact extracted page strings and their canonical UTF-8 JSON
snapshot SHA256, saved request bytes and expected SHA256, and saved NDJSON stream
bytes and expected SHA256. The source hash identifies the extracted text snapshot,
**not original PDF bytes**. Expected hashes should be retained independently when
preparing a replay. A hash computed now cannot prove a historical pre-run freeze.
The output explicitly distinguishes request hashes recorded before the original
experiment from post-run verification, and treats saved-stream hashes as post-run
integrity bindings. The CLI preserves CRLF bytes and refuses to overwrite outputs.

The request's numbered source pages must exactly match the supplied snapshot's
line contents. Types, document identity, JSON duplicate keys, bounds, output schema,
unsupported tool steps, missing/multiple results and duplicate proposals are
checked. A failed or partial original stream is rejected, never an empty success.
Only one outer JSON Markdown fence is an allowed recorded normalization.

Session proposals retain exact source activity and target-line offsets. Annex
mention quotes must locate uniquely inside the model's supplied activity range;
this uses no gold annotation. A contextual antecedent must have an unambiguous
literal quote and precede the mention. In `recorded-interpretation.v2`, the
target number must also appear with an explicit annex label inside its mention
quote (or antecedent for anaphora), using an independent, integer-only grammar.
Cropped word/number tokens and subnumbering do not establish a target.
All evidence reproduces original source
characters. Ambiguous or malformed responses fail atomically.

These are **provenance checks only**. A literal quote does not establish the right
session, anaphoric meaning, resource necessity, physical sheet availability,
curricular alignment or pedagogical correctness. Non-abstained proposals remain
`needs_human_review`; explicit abstentions retain null targets and
`insufficient_evidence`. Nothing receives automatic editorial approval. The
experimental script does not enable the separate synthetic-only shadow provider.

## Development replay receipt

An offline replay of 15 previously recorded development responses accepted all
15 under the initial v1 provenance contract: 10 activity/session recordings and 5 activity/annex
recordings. The first activity/session stratum contained 139 proposals; the second
contained 346 including its context pages, of which 207 were scored opportunities.
The annex recordings contained 32 proposals. These are validation counts, **not
accuracy**. No additional provider calls were made. Annex request hashes were
recorded after the original run; this limitation remains explicit. This receipt
does not assert that those saved responses have passed the stricter v2 contract.

Independent AI development references remain separate from replay validation.
They are neither teacher validation nor evidence of 90% curriculum-wide reliability.

## Follow-up review repairs

Continuation extraction now uses literal original page slices rather than a
reconstructed cleaned string. Blank lines, CRLF and initial nested-list indentation
remain intact. A nested first line continues the prior activity, and a task that
contains a URL is not discarded as page boilerplate. The already-existing narrow
page-admission boundary is not broadened.

The explicit-annex evaluator is now `activity-annex.v3`. Its frozen reference
hash/denominator are unchanged. An independent small grammar verifies that each
annotated explicit mention contains an annex label and its annotated number.
The `supported` metric means coverage of that checked literal label/number span,
not semantic necessity. Contextual anaphora uses a separate antecedent-aware
contract, and must not be mixed into this explicit-only scorer. The predictor
reads literal activity-annex associations, independently of operational
`requiere_anexo` claims. Old checkouts lacking relationship-specific
`annex_evidence` cannot claim supported provenance through a generic fallback;
earlier cross-checkout support numbers must not be relabelled as v3 results.

## Remaining release blockers

This is a draft research cut. Bounded necessity interpretation separates literal
mentions from affirmative operational use, negated use and uncertainty. Unknown
or conditional discourse remains for human review; no sheet is thereby resolved.
This is a narrow synthetic-tested interpretation, not general Spanish discourse
understanding. A saved LLM judgement alone does not authorize the operational
path. Human curricular validation, production adapter budgets/timeouts and
held-out evaluation remain separate requirements.
