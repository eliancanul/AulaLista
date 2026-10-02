# Prospective current-profile binding for PDA scope replay

This amendment is frozen before its implementation and before any current
provider call. The wire key schema stays `anchor-id-auditor.v1`; this change
constrains the otherwise opaque group identity only in the new PDA opt-in.

For `pda_context=True`, `group_id` must equal the deterministic current-group
identity returned by the trusted runtime. It has reserved prefix `scope-current:`
and binds a canonical hash of document ID, extracted source hash, declaration
page, all literal/PDA/governing-project flags and an explicitly listed source-code
fingerprint. Response already echoes this ID. A legacy group with an arbitrary
ID cannot be silently upgraded to the new profile. With `pda_context=False`,
the reserved prefix is rejected, so a current PDA recording cannot be downgraded.

The fingerprint covers session_declarations, pda_context_recovery,
anchor_scope_audit, anchor_scope_catalogue, source_segments, overview_fields,
source_interpreter, claims and vocabulary. It is not described as the whole
Python dependency graph or a container image. Code, flag or source changes
invalidate these new current IDs even when the resulting group happens to be
lexically identical. No profile string supplied by the caller is trusted.

Old `pda_context=False` recordings keep their original opaque IDs and legacy
behavior. In particular, this amendment does not retroactively claim universal
option/code binding for old local-list-only or default recordings. The new
current study enables PDA context throughout and therefore always uses the
stronger identity. It never reuses an old response.

Before returning no_eligible_records or invoking any provider, scope audit must
reconstruct the current full eligible groups and validate their ordered coverage.
Missing, duplicated, reordered or emptied caller groups cannot bypass that check
or spend a provider invocation. Final replay independently repeats reconstruction
and group/response identity checks. Provider metadata exceptions are sanitized;
there are no retries, source repair, partial releases or authority changes.
