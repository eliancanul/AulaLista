# Offline anchor scope audit candidate contract

Prospective contract, 2026-10-02. Extends `recorded-interpretation.v2` offline;
no production rollout, semantic acceptance, curricular approval or new ontology.

## Boundary and state

`extract_declarations(..., scope_audit=config)` runs the ordinary literal matcher
first. Absent config or `enabled=false` returns the existing output unchanged,
without calling the injected provider. Enabled execution adds only a detached
`scope_audit` sidecar. It never changes records, evidence, values, units or claims.
Only `synthetic_test` and `recorded_replay` providers execute. No vendor SDK,
credentials, network adapter, new model call, retries or context expansion.

The route admits only `decision=abstained`, `reason=unresolved_scope`, `unit=null`,
`claim=null`, kind contenido/pda, one literal complete label and one already
extracted page-local immutable value. Mode b and literal_only are unsupported.
Confirmed units and deterministic candidates cannot be routed.

Successful validation creates `decision=candidate`, `state=needs_human_review`,
`transport_status=accepted`, `semantic_validation=false`, `production_applied=false`.
Accepted describes only transport/identity/provenance. No accepted curricular
claim, dossier write or human acceptance is created. Abstention emits no candidate.
Silence, malformed output or stale source emits no candidate and sanitized errors.
Validation is atomic for the recording bundle: errors release no valid subset.

## Inputs and hashes

Python Unicode offsets are zero-based half-open; excerpts equal exact source
slices. No normalization, text repair, PDF extraction or corpus fixtures.
Document hash is SHA-256 of ordered pages as UTF-8 compact JSON with
ensure_ascii=false; it is not PDF bytes. Current declaration source and extraction
hashes must both match those pages.

Source-only `anchor-catalogue.v1` grammar is reused from the closed study.
Physical ID is `anchor:` plus SHA-256 of sorted compact JSON containing exactly
document_id, document_sha256, page_number, start, end, kind and excerpt_sha256.
Repeated headings stay distinct physical occurrences. Ambiguous/reference-only
headings cannot be selected. Complete canonical catalogue and supplied pages,
packet bytes and response bytes have retained expected SHA-256 bindings.

Default catalogue input is this document. Historical replay may supply bounded
original source-windows JSON with its expected byte hash to reconstruct an
original multi-document catalogue. Current document and exact pages must occur
exactly once. Extra source metadata is hashed, never interpreted as instructions.

## Provider and recording schemas

`ScopeRequest` contains document_id, exact pages, current source/extraction hashes,
source-only catalogue and eligible mode-a records grouped by declaration page.
Provider returns a list of `ScopeRecording` with packet_text, packet_sha256,
response_bytes, response_sha256 and model_as_recorded. These are saved data,
not instructions or authorization. Provider receives isolated copies.

Packet keys are exactly contract_version (`anchor-id-auditor.v1`), group_id,
document_id, document_sha256, catalog_sha256, records, context_pages,
allowed_page_numbers and expansion_used=false. Every record must equal a freshly
routed mode-a counterpart. One packet per eligible declaration page, complete
coverage in current order. Context is exactly that page and its previous page.
Allowed pages are the bounded source window (1–6). group_id is opaque, never a
unit or scope fact.

Response keys are exactly contract_version, group_id, catalog_sha256, action,
record_decisions, requested_pages and reason. Only propose or abstain;
requested_pages=[] always. Decision keys are exactly record_id, status,
anchor_id, value_quote and reason. Only proposed/abstained. Proposed requires
value_quote=null and one selectable same-document catalogue anchor with all
support pages supplied. Abstained requires anchor_id=null, value_quote=null.
Propose requires complete ordered coverage and at least one proposal. Abstain
requires empty decisions. Reasons are nonempty and at most 1000 characters.

Strict UTF-8 JSON or one precisely delimited outer JSON fence is admitted and
normalization recorded. Duplicate keys, nonfinite numbers, unpaired Unicode
surrogates, excessive depth/size, arbitrary prose/fences, null, omissions and
unsupported fields fail closed. Existing replay handles byte transport; scope
module validates schema and current source bindings.

## Semantic limits and verification

Anchor identity and literal provenance are not semantic proof of belonging.
Reject observable contradictions: later/distant anchors, intervening units or
reset barriers, ambiguous blocks, reference headings, missing support and
repeated same-literal headings. No nearest-project or proximity correction.
Plausible mistakes without an observable contradiction remain review candidates.

Synthetic negatives cover unknown IDs, changed hashes/source, other session or
project, ambiguous blocks, null/silence, format and prompt injection. Private
historical outputs stay private; PDF/gold values never become committed fixtures.
Actual end-to-end counts must be measured; study 16/16 poshoc is not automatically
a pipeline metric. Full repo checks and independent review precede a clean local
commit. Publication is a separate parent decision.

### Barrier clarification before final implementation verification

Unknown/bare/wrapped session and project heading cues veto an earlier scope
without creating new units. One literal two-line metadata continuation is exempt:
`Tema de la` immediately followed by `sesión:` (horizontal spacing/case only).
The preceding line may begin with the literal `Fecha:` and a calendar day
(1–31, optional weekday), then `Tema de la`; no arbitrary prefix is exempt.
It is the existing theme-of-session metadata label, not a new numbered session.
No title/number similarity or proximity exception is introduced. Only text
strictly between the selected anchor end and declaration start is inspected.
The replay entry independently reconstructs the catalogue and current matcher
route and checks group order, including dictionary insertion order.

### Additional synthetic safety guards

Catalogue bytes and the original recognition grammar remain reproducible. Scope
validation adds only conservative vetoes: control/nonphysical vertical separators
inside a selected heading, and dated-session corroboration whose activity moments
occur only in quoted/example/citation context. These narrower guards do not add
heading admissions, alter literals or make a semantic assignment.


Quote/example safety retains state across the supplied pages. For classification
only, adjacent supplied pages without a final CR/LF get one virtual newline;
existing line endings and blank paragraphs are preserved. No virtual character
is used in evidence, catalogue identity, hashes or value offsets. Hidden pages
outside the supplied context do not become discourse evidence.
