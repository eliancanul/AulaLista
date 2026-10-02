# Bounded mixed-field audit: prospective v1 contract

Status: **contract only, 2026-10-02**. This document freezes the proposed offline
interface and test plan; it does not implement or enable an auditor. It extends
the detached literal-declaration experiment, not the production interpreter.
No private corpus, final reserve, live model call, publication or pedagogical
validation is part of this cut.

Read alongside `session-declarations-contract.md`,
`anchor-scope-audit-contract.md` and `interpretation-recorded-replay.md`.
ADR-0002 still reserves editorial approval and publication to a human
`EditorialReviewer`.

## 1. Decisions fixed before implementation

1. The input is one **complete, exact, page-local mixed block**, already extracted
   from source: combined label, `kind=null`, `decision=abstained`,
   `reason=combined_label`, `claim=null`. The original label, value, evidence,
   record ID and prior unit metadata are immutable.
2. The auditor describes or proposes an interpretation. It does not turn that
   record into a deterministic typed declaration or create an `AtomicClaim`.
3. V1 cannot assign, replace or infer a unit. A prior session, project or null
   unit is retained as metadata only. It is not a new scope proof. No project
   inheritance, nearest-heading rule or semantic scope audit is introduced.
4. V1 supports `text_generic`, `no_resolvable`, `mixed_preserved` and
   `typed_partition_proposed`. `code_links_proposed` is **reserved and rejected**.
   Code expressions remain literal and are marked `unresolved_reference` when
   identified. They cannot be expanded into absent descriptions or SEP entities.
5. Typed partitioning may be a semantic hypothesis with reportable source
   context or structure. An individual explicit contenido/PDA label is **not**
   required where none exists. A bullet, indentation or ordering alone does not
   establish type. In particular, `*` does not mean contenido and `-` does not
   mean PDA without further evidence; swapping those glyphs cannot be a type
   rule.
6. Transport acceptance verifies identity, shape, literal provenance, coverage
   and observable constraints, **not the truth of the proposed interpretation**.
   Every valid result remains `needs_human_review`, `semantic_validation=false`,
   `production_applied=false`, `claim_emitted=false`.
7. Only bounded `synthetic_test` and `recorded_replay` data providers are allowed.
   No network, vendor SDK, credentials, new LLM call, retry, requested expansion,
   external source-file lookup, dictionary lookup or production write belongs in the module.

## 2. Routing and preservation

The future opt-in auditor runs after the ordinary matcher and mixed-block
preserver (`mixed_fields=True`). Its sidecar must leave their complete serialized output unchanged.
Absent or disabled config makes no provider call and adds no sidecar. Enabled
with no eligible records returns an explicit `no_eligible_records` outcome and
makes no provider call.

Eligible records must have exactly the prior state in §1, one full combined-label
reference and one nonempty complete value reference on the **same page**, plus
any unchanged evidence already attached by extraction. A challenge with only a
label is not an eligible empty block. Empty, partial, cross-page, uncertain-boundary,
quoted/example-only, tabular or unsupported records are not repaired here.
Standalone typed declarations, scope-audit outputs and other abstention reasons
cannot enter by relabelling their prior state.

Recovery ledger rows retain `record_id`, `method`, `label_utf8_sha256`,
`value_utf8_sha256`, the `mixed_field_boundary` source reference and the unchanged
`mixed_field_context` references. A record is eligible only if its complete
recovery row is freshly reconstructed; the sidecar version is
`closed-mixed-fields.v1`. All closure/context proof pages also obey the fixed
context bound below. Absence of a matching ledger row is `missing_complete_value`.

Before replay, a trusted builder reconstructs extraction and eligibility from the
exact pages using the recorded extraction profile. It compares the entire current
base output and complete ordered route with the supplied versions. A valid-looking
caller record, invented completion proof or self-consistent set of caller hashes
is insufficient. The module must not call itself during reconstruction. An
unavailable matcher/profile revision is an explicit rejection, never a fallback
to a different grammar. Existing extractor flags and their values are preserved;
this contract does not silently enable another recovery/scoping feature.

There is one packet per page with eligible records. Pages are ascending; records
retain extraction order, including repeated identical text at different physical
positions. The packet contains the whole group, never a sampled subset. All
packets in the request form one atomic bundle.

### Bounded context

For a declaration page `p`, supplied context is exactly page `p` and, if present,
page `p-1`, in ascending order. Physical numbers refer to the supplied ordered
text snapshot, not printed page labels. All existing evidence and prior unit
anchor pages for an eligible record must lie in that fixed context; otherwise
record the route as ineligible with `prior_evidence_outside_context`.

The request can contain 1–6 original pages. The provider receives only prebuilt
packet context, never the whole source window or a filesystem path. The trusted
validator can use the full original window to reconstruct the route. Neither an
LLM request nor a saved response can expand the context. The previous page gives
context, not permission to move a value or change the prior unit.

## 3. Canonical identity and primitives

All object key sets below are exact. All fields are required, including empty
arrays and explicit nulls. Unknown fields, enum values and implicit defaults are
invalid. JSON booleans are not integers. No coercion is allowed.

- `Hash`: 64 lowercase hexadecimal characters; full SHA-256, never truncated
- `Id`: nonempty Unicode string of at most 128 code points, without C0/C1 controls
- `Reason`: nonblank Unicode string of at most 1000 code points
- `Span = {page_number: int, start: int, end: int, excerpt: string}`
- Span offsets are zero-based, half-open indices into the original Python Unicode
  string, not UTF-8 bytes, UTF-16 units or normalized text. Require
  `0 <= start < end <= len(page)` and exact `excerpt == page[start:end]`
- `C(x)`: UTF-8 bytes of JSON with `ensure_ascii=False`, `sort_keys=True`,
  `separators=(",", ":")`, `allow_nan=False`; list order is significant
- `H(bytes)`: SHA-256 of those exact bytes
- `pages_sha256`: H of the original page array encoded as UTF-8 JSON with
  `ensure_ascii=False`, `separators=(",", ":")`. This is an **extracted-text
  snapshot hash**, not an original PDF-byte hash

For this replay profile, original `source_doc_sha256` and `extraction_sha256`
must both equal `pages_sha256`. A different PDF-byte binding requires a future
explicit two-artifact contract, not an exception or hash substitution.

`ExtractionProfile` keys:

```text
{
  contract_version: "mixed-field-extraction-profile.v1",
  matcher_version: Id,
  extraction_code_sha256: Hash,
  mixed_field_recovery_version: "closed-mixed-fields.v1",
  options: {literal_recovery: bool, mixed_fields: true}
}
```

The trusted implementation obtains `matcher_version` from the current detached
extractor and requires the literal recovery version shown above. `options` has
exactly the two keys shown, including `literal_recovery=false` when disabled.
The profile cannot carry callable/import names, paths or arbitrary configuration.
Reconstruction calls `extract_declarations(pages, source_doc_sha256=pages_sha256,
literal_recovery=profile.options.literal_recovery, mixed_fields=True)` with no
scope auditor. It checks the full `mixed_field_recovery` sidecar and recovery
ledger, not just the augmented records. `extraction_profile_sha256 = H(C(profile))`.
`extraction_code_sha256` is H(C of an ordered array of `{path, sha256}` objects),
with paths in lexical order and full file-byte SHA-256 for exactly:
`curriculum/claims.py`, `curriculum/overview_fields.py`,
`curriculum/source_interpreter.py`, `curriculum/source_segments.py`,
`curriculum/vocabulary.py`, `scripts/mixed_field_recovery.py`, and
`scripts/session_declarations.py`. Paths are fixed repository-relative names,
resolved from this module's checkout; no caller-supplied path is read. A missing
source file rejects. This fingerprint covers those seven files, **not** all
transitive dependencies, Python/runtime environment or a historical execution.
Fresh full-output reconstruction remains required. Reading these fixed local
source bytes for the fingerprint is the sole module filesystem operation.

A future `pda_context`/descriptor option requires an amended profile and fresh
bindings; an enriched output cannot masquerade as the v1 base by removing or
ignoring unknown fields. Unknown keyword/profile options are never forwarded.

`PriorRecord` is an exact deep copy of the base extractor record, with keys
`id, kind, decision, reason, unit, evidence, claim`. Its required state is in §1.
`unit` is null or exactly `{id, kind: "session"|"project", anchor}`. Each prior
source reference has exactly `document_sha256, page_number, printed_label,
excerpt, region, role`, where `region={kind:"text_offsets",start,end}` and its
hash/offsets/quote are checked against original pages. Existing roles and
`printed_label` values are retained without normalization, not supplied by the
model. The prior unit anchor is validated even if it is not repeated in evidence.

For each routed record, compute the following identity **from reconstructed
source-bound inputs**, not from model echoes:

```text
record_binding_sha256 = H(C({
  contract_version: "mixed-field-record-binding.v1",
  document_id: Id,
  pages_sha256: Hash,
  extraction_profile_sha256: Hash,
  prior_record: PriorRecord
}))
audit_record_id = "mixed:" + record_binding_sha256
```

`audit_record_id` is a separate 70-character identity. Keep the prior short record
ID unchanged; it is not sufficient as the audit binding. A duplicate physical
record or repeated audit ID invalidates the route. A collision in prior short IDs
is reported rather than merging physical occurrences. Full evidence, values and
unit metadata are covered by the binding.

## 4. Exact request, packet and recording schemas

The proposed Python integration is exact and optional:

```text
MixedFieldAuditConfig(document_id: str, provider=None, enabled: bool=False,
                      literal_recovery: bool=False)
MixedFieldRecording(packet_bytes: bytes, packet_sha256: str,
                    response_bytes: bytes, response_sha256: str,
                    model_as_recorded: str="synthetic-test-only",
                    request_hash_timing: str="post_run_verification")
RecordedMixedFieldProvider(recordings: tuple[MixedFieldRecording, ...])
    kind = "recorded_replay"
    propose(packets: tuple[dict, ...]) -> list[MixedFieldRecording]
audit_mixed_fields(*, pages, declarations, config) -> MixedAuditSidecar
build_mixed_audit_request(*, pages, declarations, config) -> MixedAuditRequest
replay_mixed_field_audit(*, request, recordings) -> MixedAuditSidecar
```

The extractor parameter is `mixed_audit=None`. Its hook adds `mixed_field_audit`
only for an enabled config, after mixed-field preservation and before the legacy
scope auditor, using the complete pre-audit output as `declarations`. The mixed
auditor rejects an input already containing either audit sidecar; it never strips
unknown enrichment. Reconstruction passes no audit configuration.
`config.literal_recovery` must match that output and reconstruction exactly.
Calling the auditor directly with disabled config is invalid; the wrapper owns
disabled no-op behavior. `provider.kind` admits exactly `synthetic_test` or
`recorded_replay`; providers are explicitly trusted local code returning saved
or synthetic bytes, not a sandbox that can prove a malicious callable is offline.
The provided recorded adapter performs no I/O. No live provider is implemented.

The internal trusted request is not an LLM response:

```text
MixedAuditRequest = {
  contract_version: "mixed-field-audit-request.v1",
  document_id: Id,
  pages: [string],
  pages_sha256: Hash,
  extraction_profile: ExtractionProfile,
  base_output_sha256: Hash,
  route: [RouteEntry],
  packets: [Packet]
}
RouteEntry = {
  prior_record_id: Id,
  eligible: bool,
  reason: "eligible_mixed_block"|"not_mixed_record"|"missing_complete_value"|
          "prior_evidence_outside_context"
}
Packet = {
  contract_version: "mixed-field-auditor.v1",
  profile: "partition_only",
  group_id: Id,
  document_id: Id,
  pages_sha256: Hash,
  extraction_profile_sha256: Hash,
  base_output_sha256: Hash,
  records: [PacketRecord],
  context_pages: [{page_number: int, text: string}],
  allowed_page_numbers: [int],
  expansion_used: false,
  dictionary: null
}
PacketRecord = {
  audit_record_id: Id,
  record_binding_sha256: Hash,
  prior_record: PriorRecord,
  label_span: Span,
  immutable_value_span: Span
}
Recording = {
  packet_bytes: bytes,
  packet_sha256: Hash,
  response_bytes: bytes,
  response_sha256: Hash,
  model_as_recorded: Id,
  request_hash_timing: "pre_run_retained"|"post_run_verification"
}
```

`base_output_sha256 = H(C(base_output))` covers the full freshly reconstructed
base output before any audit sidecar. Route has one entry for every base record,
in base order. Eligibility reasons are deterministic routing results, not model
abstentions. Non-mixed takes priority, then missing complete value, then missing
context support. Structurally invalid source/base/profile inputs reject the whole
request instead of being labelled ineligible.

`group_id` is `mixed:p` followed by the positive decimal declaration page without
leading zeroes. It is a packet identifier, not a semantic unit. Packet records and
span projections must equal the corresponding fresh route group exactly.
`allowed_page_numbers` equals the exact `context_pages` numbers, not all pages
in the trusted source window. Context text must equal original pages byte-for-byte
when encoded as UTF-8. `dictionary=null` is required in v1.

Packet bytes are exactly `C(Packet)`. Responses echo their exact packet byte
hash. The replay caller retains the expected packet and response hashes separately
from parsed contents. A computed-now digest proves current integrity, not a
historical pre-run freeze, provider identity or model authenticity.
`model_as_recorded` is descriptive saved metadata only. Request-hash timing is
reported honestly; it is never inferred from the timestamp in a filename.

The data provider accepts an isolated deep copy of the ordered packets and
returns one `Recording` per packet, in the same order. It receives no gold,
expected class/type, semantic reference, private corpus or source outside those
packets. Validation uses original trusted inputs, not a provider-mutated copy.
No automatic prompt/model generation or live adapter is authorized by this schema.

## 5. Exact response and partition schema

```text
Response = {
  contract_version: "mixed-field-auditor.v1",
  group_id: Id,
  packet_sha256: Hash,
  action: "report",
  record_decisions: [RecordDecision],
  requested_pages: [],
  reason: Reason
}
RecordDecision = {
  audit_record_id: Id,
  record_binding_sha256: Hash,
  status: "observed"|"abstained"|"proposed",
  interpretation: "text_generic"|"no_resolvable"|"mixed_preserved"|
                  "typed_partition_proposed",
  partition: [Segment],
  reason: Reason
}
Segment = {
  span: Span,
  disposition: "typed_proposal"|"preserved_untyped"|
               "unresolved_reference"|"formatting",
  proposed_kind: "contenido"|"pda"|null,
  basis: "semantic_context"|"reported_structure"|"none",
  evidence: [Support],
  reason: Reason
}
Support = {
  role: "semantic_context"|"structural_context",
  span: Span
}
```

Decisions cover **every packet record exactly once and in packet order**, even
when all abstain. Empty decisions, a missing record, duplicated records, extra
records and whole-packet silence are not abstention. There is no successful
`action=abstain` shortcut which hides per-record coverage.

### Decision meanings and exact combinations

- `text_generic` → `status=observed`; no typed segment. Records an interpretation
  that the supplied text does not yield a differentiated contenido/PDA proposal.
  It does not assert that the source lacks curricular information or that its
  content is pedagogically generic
- `no_resolvable` → `status=abstained`; no typed segment. An explicit, source-bound
  refusal to type the block under current evidence. A syntactically valid result
  can abstain even if a reference later finds a resolvable interpretation
- `mixed_preserved` → `status=observed`; no typed segment. Preserves a heterogeneous
  or possibly mixed block without proposing its internal type assignment. The
  combined label alone is not proof that both types actually occur
- `typed_partition_proposed` → `status=proposed`; at least one nonempty typed
  segment. One proposed kind is sufficient; do not manufacture the other to make
  the label's two words appear satisfied. Other segments can remain untyped or
  unresolved. This is a proposed content distinction, not a literal typed claim

Every combination not specified above is invalid. None asserts session
membership. Classification explanations are model-authored hypotheses and must
not appear as source quotes, accepted facts, new label evidence or policy.

### Exhaustive partition ledger

For a value span `[a,b)` on page `p`, require a nonempty ordered partition whose
first segment starts at `a`, last ends at `b`, every adjacent pair satisfies
`left.end == right.start`, and all segments have page `p` and positive length.
All segment quotes are exact source slices. Their direct concatenation must equal
the entire immutable value exactly, including bullets, blank lines, CRLF,
indentation, punctuation, NFC/NFD differences and supplementary Unicode points.
Do not trim, reorder, normalize, paraphrase, deduplicate or add a separator.

This partitions the **whole value**, not a model-selected subset of "applicable"
text. Uninterpreted prose is `preserved_untyped`; a code/reference expression is
`unresolved_reference`. Both remain visible in the ledger. Only a segment made
entirely of characters from `" \t\r\n"` can use `formatting`. Bullets, list numbers,
labels and punctuation cannot be hidden as formatting; attach them to a content
segment or preserve them as untyped/reference text. There is no deletion or
exclusion disposition. These rules make omissions mechanically visible without
assuming that punctuation determines semantics.

`typed_proposal` requires a nonnull proposed kind, non-`none` basis and 1–16
support spans. At least one support has the role corresponding to its basis and
contains substantive text (at least one Unicode letter or number) beyond a bare
bullet/indentation. Evidence can include the segment itself and exact supplied
context; it does not require a nonexistent typed inner label. A structure-based
proposal must describe the observed context and why it is a **hypothesis**, not
claim that a marker supplies curricular type. `semantic_context` may explain the
meaning of the quoted text; that explanation is never mechanical proof of type.

All non-typed dispositions require `proposed_kind=null`, `basis=none`,
`evidence=[]`. Support spans are source-bound within the fixed packet context,
nonduplicated and ordered by `(page_number,start,end,role)`; they need not partition
or be disjoint from the segments. A raw `*` or `-` alone fails the substantive
support test. An explanation asserting that a glyph automatically establishes a
type violates the semantic contract even if unrelated quoted text makes transport
valid; the source-only semantic evaluation must expose this remaining risk.

Identified code expressions must remain `unresolved_reference`; never type a code
alone, infer an expansion from memory or attach a catalogue identity. The v1
validator has no universal code-meaning grammar: exact source coverage does not
prove that every reference was recognized. Missed codes and false type proposals
are measured against the separate source-only reference, not reclassified as
transport failures after observing its answers.

## 6. Validation, limits and atomic release

Future public replay entry validates, in order:

1. Bounded source/profile inputs and current exact source binding
2. Fresh base output, eligibility, record IDs and complete packet manifest
3. Provider kind; record count/order; raw packet/response hashes; strict decoding
4. Exact packet keys, source slices, record bindings, context and no expansion
5. Response keys, packet echoes and complete ordered decision coverage
6. Decision combinations, partition coverage, literal supports and fixed limits
7. Only then construct detached results and their deterministic IDs

Use `decode_recorded_json` for byte transport, with its duplicate-key, nonfinite,
strict UTF-8, depth and Unicode-surrogate checks. Packets disallow fences and must
also satisfy canonical byte equality. Responses admit strict JSON or precisely
one outer JSON fence as supported by that function; record that normalization.
Arbitrary prose, multiple fences/results, tool instructions or repaired JSON fail.

Fixed v1 limits (exceeding any is an explicit rejection, never truncation):

- 1–6 source pages; at most 2,000,000 total source Unicode code points
- At most 2,000 base records and 2,000 eligible records; at most 6 packets
- At most 262,272 bytes per canonical packet and per raw response
- At most 128 segments per decision and 16 supports per typed segment
- JSON depth at most 64; IDs and reasons bounded as in §3
- One local provider invocation per eligible bundle; no retry or context expansion

A large original page may exceed the packet limit even within the source limit;
report that fact and reject the bundle. Do not crop the page, split an atomic page
group, silently omit records or try another model. Network timeout/budget policy
is outside this offline module because it cannot make network calls.

Any malformed/stale/contradictory packet or response, missing recording, provider
exception, false hash, out-of-context evidence or invalid segment invalidates the
**entire bundle**. Release no valid subset, no typed candidates and no accepted
observations/abstentions. Sanitized error codes and trusted coverage counts may be
retained. Source/provider free text, tokens, stack traces and arbitrary exception
messages must not leak through errors. Keep the original base output intact.

## 7. Exact detached sidecar and lifecycle

```text
MixedAuditSidecar = {
  version: "mixed-field-audit.v1",
  status: "no_eligible_records"|"review_only_results"|"invalid",
  pages_sha256: Hash|null,
  extraction_profile_sha256: Hash|null,
  base_output_sha256: Hash|null,
  route: [RouteEntry],
  coverage: {
    eligible_records: int,
    expected_packets: int,
    received_packets: int,
    accepted_records: int,
    typed_proposal_records: int,
    explicit_abstention_records: int
  },
  results: [Result],
  errors: [Id],
  provider_attempts: 0|1,
  external_calls: 0,
  semantic_validation: false,
  production_applied: false,
  claim_emitted: false
}
Result = {
  proposal_id: Id,
  audit_record_id: Id,
  record_binding_sha256: Hash,
  prior_record: PriorRecord,
  immutable_value_span: Span,
  prior_unit: {id: Id, kind: "session"|"project", anchor: SourceReference}|null,
  unit_policy: "preserve_prior_metadata_only",
  decision: RecordDecision,
  state: "needs_human_review",
  transport_status: "accepted",
  semantic_validation: false,
  production_applied: false,
  claim_emitted: false,
  receipt: {
    packet_sha256: Hash,
    response_sha256: Hash,
    model_as_recorded: Id,
    request_hash_timing: "pre_run_retained"|"post_run_verification",
    normalization: null|"single_outer_json_fence"
  }
}
```

`proposal_id = "mixed-result:" + H(C({audit_record_id, packet_sha256,
response_sha256, decision}))`, with the four keys exactly as shown. Even observed
and abstained results have an ID for review/audit; its name grants no candidacy.
`SourceReference` is the exact prior reference shape in §3.
`prior_unit` is copied from the immutable prior record, never from a response.
No model-facing `unit`, `anchor_id`, `scope`, `claim`, `confidence`, accepted state,
code link or replacement value field exists. Unknown attempts to add them reject
rather than being ignored. `state` and safety flags are validator constants.

`no_eligible_records` has empty results/errors, zero expected/received packets,
zero accepted/typed/abstention counts and zero attempts. `review_only_results`
requires every expected record; accepted count equals eligibility, with separately
counted observed, proposed and abstained decisions. `invalid` has empty results
and zero accepted/typed/abstention counts. Coverage is always produced by trusted
code; received packets is only the actual recording count, not successful coverage.
Before a trustworthy route exists, hashes are null and route/counts are empty/zero.
After successful reconstruction, retain verified hashes/route/denominators even
if provider or response validation later fails. Do not convert an invalid response
into `no_resolvable`.

The sidecar is not accepted curricular data and must not be counted as typed
session candidates by the existing literal scorer. If a later user-facing review
shows it, original and proposed text must be separately inspectable and the prior
null/project scope must remain visible. Any eventual human acceptance workflow
requires a separate contract and existing editorial authorization.

## 8. Independent reference and reporting

The upstream literal freeze is
`tests/fixtures/interpretation/session_declarations_mixed_fields_v1.json`.
Its source-only spans/expected extraction behavior are frozen independently of
this auditor; cite its actual retained digest when available. Do not invent a
hash or reuse its literal-detection score as semantic accuracy.

Before writing the semantic predictor or tuning prompts, freeze a **separate
synthetic source-only interpretation reference**, its SHA-256 and denominators.
Reference authoring/scoring must not import the future auditor, provider, matcher
or their expected outputs. Annotators see original pages and the declared task,
not model predictions. Independent validation verifies exact spans, source hashes,
complete block opportunity inventory and partition coverage before scoring.
Multiple acceptable interpretations or genuinely unresolvable cases are recorded
explicitly, rather than treating one fluent rationale as ground truth.

Keep at least these reports separate:

1. Upstream literal opportunities: exact whole-block recovery, partial/contaminated
   values, omission, duplicate and extra detections. Audit cannot earn recovery
   credit for a missing input block
2. Routing and transport: eligible/ineligible counts and reasons, expected/received
   packets, fully accepted bundle, invalid bundle and silence/missing decisions.
   Provider invocation count and zero external calls are operational measurements
3. Block interpretation on the fixed source-only opportunity denominator: correct
   observed/proposed/abstained class, wrong class, invalid and omitted. Report
   typed coverage and explicit abstention separately; silence never earns
   abstention credit, even if it avoids a false typed output
4. Segment proposals: exact boundaries, proposed-kind correctness and source
   coverage, with typed false positives, untyped content, unresolved references,
   missed references and over-segmentation visible. Type accuracy is measured only
   by the independent reference, never by exact-quote/transport acceptance
5. Joint block + partition/type performance, and exact whole-block success.
   A one-token correct proposal cannot make a mostly omitted or mistyped block
   count as fully interpreted. Report acceptable alternative partitions explicitly
6. Negative/generic/code-only blocks: false typed proposals per fixed negative
   denominator; `text_generic`, `mixed_preserved`, explicit `no_resolvable`,
   silence and invalid responses remain distinct
7. Governance invariants: zero changed original bytes/spans/units/claims,
   zero new `AtomicClaim`s and all review-only safety flags. Report this separately
   from the number of semantically false typed proposals

**Zero emitted AtomicClaims is not zero false type proposals.** Likewise zero
typed candidates caused by silence or universal abstention is not type accuracy.
Missing/zero denominators are N/A. Accepted transport is neither curricular truth,
teacher validation, production readiness, OCR validation nor general reliability.

## 9. Implementation-ready test plan

All cases are synthetic and source-only. Freeze fixtures and references first;
implement the parser/replayer in a separate module only after review of this
contract. Suggested files: `scripts/mixed_field_audit.py` and
`tests/test_mixed_field_audit.py`; no runtime edits are made by this document.

### A. Admission and compatibility

- Default/disabled mode is serialized-byte equivalent to the base output; zero calls
- No eligible blocks returns `no_eligible_records`; label-only combined challenges
  remain ineligible, not successful zero-length audits
- Genuine complete mixed value routes once; standalone typed, unrelated abstained,
  quoted/example, partial and tabular records cannot be made eligible by payload edits
- Preserved unit variants session/project/null remain exactly unchanged; null does
  not block textual hypotheses, and project metadata never becomes session scope
- Every prior evidence page must be supplied; missing distant proof yields an
  explicit ineligible route without enlarging context
- Profile/version/code-fingerprint mismatch, unknown option, omitted false option, wrong option
  types or forged/enriched base output reject before provider use

### B. Valid interpretations and semantic risk

- All four exact classes, all-abstained multi-record packet and mixed-status packet
- Partial typed partition plus preserved-untyped text; only one proposed kind;
  no manufactured counterpart to match a combined label
- Pure codes and text-plus-code segments stay `unresolved_reference`; no definitions
  are invented. Wrongly typed codes count as semantic errors even without a claim
- Paired examples reverse `*`/`-`, use the same glyph for both content kinds, change
  order/indentation, and contain misleading verbs/nouns; compare against independent
  source meaning. Glyph-only support rejects; plausible wrong semantics may pass
  provenance but must fail the source-only semantic evaluation
- Structure/meaning support without an explicit inner label is permitted as a
  review hypothesis, never as proof that the source declared a deterministic type
- Generic/indeterminate text, ambiguous layout and an available but wrong semantic
  proposal distinguish correct abstention, weak coverage and false typed output

### C. Exhaustive source partition

- Multiline, CRLF, blank lines, tabs, accents, NFC/NFD and emoji retain exact slices
- Repeated same text on the same/different pages yields distinct bound records
- Reject omitted prefix/suffix, internal gap, overlap, reversed/out-of-order range,
  zero-length span, duplicate span and foreign-page segment
- Reject paraphrase, accent repair, inserted separator, whitespace normalization,
  UTF-8-byte/UTF-16-offset confusion and quote taken from another occurrence
- Reject hidden punctuation/code/content under `formatting`; only the exact four
  formatting characters are allowed. Preserve a bullet/code as literal material
- Typed segment needs nonnull kind, compatible basis and substantive exact support;
  non-typed segment cannot carry a kind, hidden support or semantic basis

### D. Identity, coverage and atomic adversaries

- Change one character of source, value, label, unit anchor, prior reason, evidence,
  profile or extraction flags; reject even if provider recomputes its own hashes
- Swap same-literal records, document IDs, record bindings, packets or responses;
  shorten a hash, reuse another request's response or alter raw bytes after hashing
- Omit/duplicate/reorder/add a packet or decision; inject an unrouteable record;
  reject the whole bundle, including an otherwise valid preceding packet
- Empty provider return, null response, timeout-like provider exception, empty
  decisions and all-whitespace bytes are invalid/silence, never explicit abstention
- Provider mutates packets, context, unit metadata or request copy; original inputs
  and subsequent validation are unchanged
- Direct replay with hand-built request must independently reconstruct the route;
  bypassing the high-level extraction wrapper grants no additional trust

### E. Schema, boundaries and injection

- Reject duplicate JSON keys, NaN/Infinity, booleans as offsets, null objects,
  unpaired surrogates, invalid UTF-8, unsupported fields/enums and excessive nesting
- One supported outer response fence records normalization; arbitrary prose,
  additional results/fences, packet fences and noncanonical packet bytes reject
- Test exactly-at-limit and one-over-limit for source, packet/response bytes,
  records, segments, supports, IDs, reasons and depth; no cropping or second attempt
- `requested_pages` nonempty, alternate profile/dictionary, `code_links_proposed`,
  external tools/URLs, scope assignment, new confidence/accepted state or claim
  fields reject; zero network/SDK/source-data-file reads. Fixed local code
  fingerprint reads are separately allowed and cannot be redirected by input
- Instructions embedded in source, rationale or `model_as_recorded` remain data;
  they cannot change flags, schemas, output destinations, review state or authority
- Error output is sanitized and contains no source, provider secret or stack trace

### F. Verification gate

Run the focused synthetic tests, existing literal-declaration/scope/replay tests,
full repository checks and independent code review after implementation. Assert
no production imports/writes, calls or changes to frozen existing fixtures. Record
actual measured counts and known limitations. A local test pass does not authorize
provider calls, publication, private/final evaluation or stronger reliability claims.

## 10. Deliberately deferred code-link extension

A future v2 may admit `code_links_proposed` only after a separately frozen
source-first dictionary contract, fixtures and independent evaluation. It must
bind every code occurrence and definition by same-document full hashes and exact
spans, retain original expressions, establish explicit applicability/scope from
source, and reject duplicated/conflicting/missing definitions, cross-document
lookups, project-to-session inheritance and ambiguous references. A lexical code
match or label containing `PDA` is not a dictionary or scope proof.

V2 will need exhaustive expression coverage, local symbol identity distinct from
SEP identity, contextual evidence for occurrence-to-definition association,
review-only typed links, atomic rejection and a source-only semantic metric. It
must not quietly enable new scope inference. V1's `dictionary=null` and unsupported
`code_links_proposed` response are intentional fail-closed boundaries; preserving
an unresolved reference is a valid v1 result, not a successful resolution.
