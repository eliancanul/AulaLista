# Closed local-content lists: opt-in implementation v1

The independently frozen source/reference contract is
`session-declarations-literal-recovery-v1.md`. This implementation admits only
that closed-list route. It does not recover dotted-code descriptors or choose
the boundary of an unlabelled explanatory note.

## Existing channel and unchanged default

`extract_declarations(..., literal_recovery=False)` keeps the original default
output exactly. The explicit boolean opt-in adds the compositional local-content
label family and a `literal_recovery` proof sidecar to the existing
`session-declarations.v1` envelope. CLI equivalent: `--literal-recovery`.
No production parser, unit scanner, scaffold grammar, dossier, UI, curriculum
model, predicate, provider adapter or editorial state is changed.

Every new recovered field is one original page-local list, one complete label
and one complete value. It is `contenido`, `abstained/unresolved_scope`, with
`unit=null` and `claim=null`, even beside an existing unit. It never produces an
AtomicClaim or interprets a local code as SEP identity. A five-item list remains
one physical field. Existing complete literals retain their records and claims.

Only known explicit heading/field vocabulary can close the list. Arbitrary
colon-bearing notes, page/window endings, wrapped items, missing punctuation,
mixed markers and nonphysical vertical/control separators do not establish a
closed field. Original rows are checked before whitespace trimming; legal
horizontal indentation, Unicode spelling and CRLF are retained in source slices.

Context must be independently safe: bounded existing metadata, a complete
on-page typed predecessor with a whitespace-only gap, or an unchanged
source-proven context reset. The existing governing-book-project profile may
corroborate a reset only when its original source-prefix guards succeed. A root
line, local header, DATOS GENERALES or field name cannot erase an active example,
nonadoption, quotation, activity or unknown-prose region. Context evidence is not
unit assignment. Open/mismatched source quotation remains unsafe across pages.

The sidecar contains recovered record IDs, method version, exact label/value
UTF-8 SHA256 hashes, a source-backed closing-heading span and source-backed
context references. Primary evidence still uses original Unicode character
offsets and the supplied document hash; UTF-8 hashes are not PDF-byte hashes.
Proof metadata cannot replace full exact label/value evidence.

## Scope audit consumption

Enable the matching `ScopeAuditConfig(..., literal_recovery=True)` to consume
new lists through the existing Mode A. Extraction and audit flags must agree;
a mismatch fails before the provider receives records. ScopeRequest carries the
same boolean for independent current-source reconstruction.

`scripts.anchor_scope_audit.route_record(..., literal_recovery=True)` wraps the
unchanged legacy router only for a freshly re-extracted, exactly matching new
list. The frozen catalogue/router script and structural proof bytes remain
unchanged. The audit entry and replay validator reconstruct current source
admission; forged labels, partial values, altered reasons, foreign hashes,
changed pages/groups and opt-in downgrades cannot authorize a new route.

Packet and response schemas, immutable values, `value_quote=null`, source hashes,
whole-group coverage and atomic validation remain unchanged. A new eligible list
changes its page's group: a saved packet/response omitting it cannot be replayed
as a complete current group. Do not borrow a historical group's success for a
changed run. A validated proposal is still only `needs_human_review`;
`transport_status=accepted` does not mean semantic or curricular acceptance.

## Verification and honest limits

The frozen synthetic stratum has 19 new list opportunities and 18 preservation
literals, plus separately counted challenges and absent documents. Default and
explicit-false outputs were compared against the pre-implementation matcher.
The unchanged scorer measures whole labels/values; list items, safety silence
and unresolved/null scope cannot inflate a positive unit/claim numerator.

The independently authored session-unit opportunity in the preservation stratum
is not recognized by the unchanged unit scanner. Its literal recovery and record
preservation do not resolve that gap; the expected session claim remains
unfulfilled. Inherited raw-value assertions/extras are measured separately and
unchanged, so perfect new-list recall is not perfect overall literal precision.
No reference or scanner was changed to gain credit.

Focused independent regressions cover structural whitespace controls, exact
first-item cropping, polarity/source mutations and stale replay groups. The
prototype deliberately leaves unsupported source layouts uncertain. Synthetic
or exposed-development results do not establish unseen/global interpretation,
teacher validation, pedagogical validity, OCR accuracy or production readiness.

Run the behavioral suite with the repository's installed development environment:

```text
python -m pytest tests/test_session_declarations_literal_recovery*.py tests/test_anchor_scope_audit.py
```

Run the independently frozen reference-only checks separately:

```text
python -m unittest discover -s tests -p test_session_declarations_literal_recovery_reference.py
```
