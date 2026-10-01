# Detached declaration serialization clarification

The original frozen reference and its denominators remain unchanged. This
clarifies two output details left implicit in the original prose, after initial
matcher invariant tests but **before the first matcher/evaluator comparison**.
No previously produced file is rewritten or silently normalized by evaluation.

- `unit.id` is already namespaced (`session:p1_s1`, `project:p1_o1`). A candidate
  claim's `subject` equals `unit.id` exactly. A second `session:` prefix is invalid.
- `AtomicClaim.page_number`, `.region` and `.excerpt` are the legacy primary
  **value** reference. `.object_value` equals that same literal value. The
  candidate retains separate exact `label`, `value` and `unit_anchor` evidence,
  plus `unit_continuation` when required. These primary fields never substitute
  for the label or unit evidence.
- The independent evaluator validates this shape. It must reject an inconsistent
  subject or primary reference; it must not repair one from source or gold data.
- The matcher reuses product structural scanning to propose physical anchors.
  Agreement with that scanner is not independent validation. The independent
  evaluator's reference validation and scoring do not import that scanner.

These are experimental serialization rules only. No production field,
canonical predicate, dossier, editorial gate or `make_claim_id` is changed.
