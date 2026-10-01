# Independent declaration evaluation v1.2

This scorer-only revision follows the frozen matcher/evaluator commit
`bfa5146b94e11c5f9979caa83561f6979f1e50ea`. The original v1.1 scorer, source
reference and strict report remain in that commit; the committed synthetic v1
report is not replaced. No primary reference opportunities or matcher outputs
are changed to improve a score. A later matcher revision requires a separate
commit and evaluation.

## Lossless scope metadata

The reference-level `scope` may be either a nonempty string or a JSON object.
The object is preserved by deep copy in the report, without flattening, renaming
keys, converting it to prose or modifying its source file. It is descriptive
metadata, not permission to discard pages, predictions or opportunities. The
authored documents/spans still determine all fixed scoring denominators.
`reference_kind` is preserved, so supplying an authorized development reference
does not relabel it as synthetic or as teacher gold.

## Strict session claims

The new `strict_session_claims` metric differs from the earlier decision-only
`session_candidates` metric. Its fixed expected denominator contains exactly
the reference declarations whose `expected_decision` is `candidate`.

Credit requires one valid prediction for that opportunity, exact literal type,
label and full value, the correct physical session unit under the existing v1.1
identity rule, coherent continuation/IDs, and the correct affirmative candidate
decision. A wrong parent cannot earn strict credit merely because the source
text and candidate decision were correct.

- Recall: strictly correct session claims / fixed expected session declarations
- Precision: strictly correct session claims / **all** emitted records whose
  decision is `candidate` **or** whose claim is non-null
- Extras, duplicates and malformed asserted records remain in the precision
  denominator; they cannot earn numerator credit
- Correct, incorrect, omitted and explicitly abstained positive opportunities
  partition the fixed positive denominator
- A zero emitted denominator gives N/A precision, not 100%

`strict_session_claims.incorrect` counts **reference opportunities that did not
receive a strictly correct response**, not false emitted claims. For example,
an incomplete abstained response can fail recovery while emitting no claim at
all. `explicit_abstentions` in that positive partition requires a complete
literal abstention; it is narrower than the presence of any abstained response.
Read precision against `emitted_claim_records` to distinguish false assertions
from missed or incomplete recovery. Do not report `incorrect` as a false-positive
claim count.

Additive scorer revision v1.2.1 exposes these distinctions in a separate,
non-additive `strict_session_claim_diagnostics` group. `wrong_emitted_claim_records`
is emitted claims minus strictly credited claims **under the supplied reference**.
`response_abstention_opportunities` counts positive opportunities that received a
valid, physically localized abstained response, including those missing complete
literal value recovery. Neither diagnostic changes the positive partition or
adds credit to recall. All v1.2 fields and their values are retained.

The existing detection, unit, unresolved-scope, joint and decision metrics remain
available; their meanings are not silently changed by this stricter metric.

## Challenge diagnostics versus legacy matching

`legacy_challenges_v1_1` preserves the original strict challenge outcome. The
old `challenges` key remains only as a compatibility alias to that legacy group.
Its historic `invalid_records` includes a label-span disagreement with the
reference; it must not be described as the number of malformed output records.

New diagnostics distinguish record validity from reference alignment:

- `challenge_opportunities_v1_2`: fixed challenge denominator, candidate/claim
  assertion, no-claim safety, unknown safety, explicit abstention, silence,
  label-span mismatch, multiplicity, malformed record and invalid provenance
- `challenge_records_v1_2`: emitted record counts, asserted records, malformed
  records, invalid provenance, explicit abstained records, exact/mismatched label
  spans and duplicate IDs; each physical output record is counted once in this
  record-oriented group even if it overlaps multiple reference challenges

These flags are not all mutually exclusive. For example, two valid abstentions
can make one opportunity multiple while emitting no claim. A literal abstention
whose label is wider than the reference may have a span mismatch without being
a malformed record. A missing output is silence, never explicit abstention.
An unlocatable or invalid-provenance output leaves safety unknown rather than
manufacturing a safe outcome.

The v1.2.1 safety repair considers the conservative union of label locators in
both each record and its `AtomicClaim`. Contradictory claim evidence must not
hide a possible assertion against a challenge behind a record located elsewhere.
If a malformed asserted claim cannot be safely localized, challenge safety is
unknown, never safe silence. This repair affects the new safety diagnostics;
legacy alignment and strict positive matching retain their earlier contract.

No-claim safety means that no affirmative candidate/claim was emitted for the
challenge under that validity/localization check. It is neither proof of correct
curricular interpretation nor a positive-recall success. Challenge safety,
explicit abstention, silence and strict positive claim recovery stay separate.

## Comparable replay

For a scorer comparison, call each version's `evaluate(reference, predictor)`
with a predictor that returns the **same saved detached outputs**, keyed by
document ID. Retain the original input/reference bytes and their hashes.
This avoids changing extraction while comparing scoring policies. Only outputs
already authorized for that task may be supplied. The public reproduction uses
the unchanged synthetic fixture and frozen bfa5146 matcher; no private reference
or final reserve is included here.

All numbers remain development evidence. No model/API cost, PDF/OCR accuracy,
teacher validation, SEP alignment or 90% global reliability is established.
