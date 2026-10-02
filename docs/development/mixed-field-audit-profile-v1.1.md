# Mixed-field audit extraction-profile amendment v1.1

Prospective freeze, 2026-10-02. Written **before** implementing or testing joint
PDA-context/mixed/literal replay. Governs only the additions below to
`mixed-field-audit-contract-v1.md`, whose retained SHA-256 is
`9bf25e4d3d2567cc9168c208009cc997a38ac019ef7d6c4a7084c00f4b247686`.
That original contract remains unchanged. This amendment authorizes no external
provider call, publication, private/final-corpus access or semantic acceptance.

## Exact amended profile and entry point

```text
ExtractionProfile = {
  contract_version: "mixed-field-extraction-profile.v1.1",
  matcher_version: Id,
  extraction_code_sha256: Hash,
  mixed_field_recovery_version: "closed-mixed-fields.v1",
  pda_context_recovery_version: "explicit-pda-local-context.v1",
  options: {literal_recovery: bool, mixed_fields: true, pda_context: bool}
}
MixedFieldAuditConfig(document_id: str, provider=None, enabled: bool=False,
                      literal_recovery: bool=False, pda_context: bool=False)
```

All profile and option keys remain exact and required, even for false options.
The new config parameter is last; existing positional argument meanings do not
change. `pda_context` is strictly a boolean, never inferred from source contents,
from a provider answer or from the presence/absence of a sidecar supplied by the
caller. Omitted options, aliases, unknown enrichment and implicit defaulting of a
saved profile fail closed.

The new detached sidecar version is `mixed-field-audit.v1.1`. Request version
`mixed-field-audit-request.v1`, packet/response version `mixed-field-auditor.v1`
and their schemas remain unchanged because record semantics and transport shape
are unchanged; the required profile hash distinguishes the new extraction state.
`extraction_profile_sha256` and record/packet/result identities are recomputed from
the complete new profile. `code_links_proposed` is still unsupported.

## Exact reconstruction and source fingerprint

Reconstruction calls only:

```text
extract_declarations(
  pages,
  source_doc_sha256=pages_sha256,
  literal_recovery=profile.options.literal_recovery,
  mixed_fields=True,
  pda_context=profile.options.pda_context
)
```

No audit configuration is forwarded. An unavailable flag/module/version rejects;
there is no retry with fewer kwargs or enriched-output compatibility fallback.
The base includes the entire exact result of this call, including both recovery
ledgers when enabled, their original records and limits. Caller output that was
made with a different flag combination, contains an audit sidecar, or has a
missing/edited recovery ledger cannot pass by stripping keys or recomputing
provider hashes. Both true and false `pda_context` inputs are bound explicitly.

The fingerprint is H(C of the sorted array of `{path, sha256}` with full byte
hashes for exactly these **nine** repository-relative source files):

- `curriculum/claims.py`
- `curriculum/overview_fields.py`
- `curriculum/source_interpreter.py`
- `curriculum/source_segments.py`
- `curriculum/vocabulary.py`
- `scripts/anchor_scope_catalogue.py`
- `scripts/mixed_field_recovery.py`
- `scripts/pda_context_recovery.py`
- `scripts/session_declarations.py`

The anchor catalogue is added because the mixed recovery module imports its
source-only context guards. The PDA recovery module is added because this
amendment explicitly admits that postprocessor. Each path is fixed by the local
implementation, never selected by input. Missing files reject. This is an explicit
source-set fingerprint, not a claim to cover every transitive dependency or the
runtime environment. Full current-output reconstruction remains an independent
required check. A change to a newly included source invalidates old profile hashes
even if `session_declarations.py` did not change.

## Boundaries retained

The PDA postprocessor's output is not an additional source of mixed-field
eligibility. Only the original complete mixed-block route may enter this auditor.
A newly recovered typed PDA remains outside that route. Its source text and
presence are bound in the base output, but this amendment grants no new unit,
claim, code link, dictionary, continuation, scope proof or typing authority.
Prior session/project/null unit metadata stays unchanged. All partition, context,
coverage, review-only state, byte transport, provider and atomicity rules of v1
continue unchanged.

A v1 recording is retained as v1 data and is **not** upgraded by assuming
`pda_context=false`, adding a new source digest or rewriting a request. The current
v1.1 replay rejects an old profile/version/hash. Replaying a historical v1 bundle
requires its matching original implementation and original source-bound inputs;
it must not be reported as evidence for the integrated v1.1 configuration.

## Prospective test gate

Before claiming joint compatibility, run all four combinations of
`literal_recovery` and `pda_context` with `mixed_fields=True`, against actual
source-first extraction. Require full equality of the base after audit for each
combination, the exact profile/options and zero calls outside the local provider.
Add these negatives:

- Cross-replay between the four profiles, even when recovered mixed text is the
  same; a changed flag/profile hash must invalidate recordings
- Missing new option, bool/int confusion, stale v1 profile, unknown kwargs and
  wrong PDA-version/source digest
- Source-set mutation in either PDA recovery or the anchor catalogue without
  editing the extraction hook; the fingerprint must change
- Injecting, omitting or changing the PDA recovery sidecar or one of its proofs
- Offering a newly recovered typed PDA as a mixed packet record
- Enabling either pre-existing scope audit or mixed audit during reconstruction
- Atomic rejection of a stale packet among otherwise valid joint-profile packets

Run the complete mixed, PDA-context, literal, scope and recorded-transport focused
suites, then the repository checks required by the integration owner. Report
actual counts and omitted/failed stages. A passing mechanical integration does
not show semantic accuracy and must not be called PDA-safe or production-ready.
