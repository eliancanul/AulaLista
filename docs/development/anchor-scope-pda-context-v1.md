# Prospective Mode A replay of source-proven PDA context recovery

This additive contract is frozen before integrating the new router or making
new external calls. It combines the existing independently frozen scope audit
with `explicit-pda-local-context.v1`. It changes no anchor recognition, physical
identity rule, scope proof, value, wire response schema, claim or scorer.

## Explicit profile and reconstruction

`ScopeAuditConfig`, `ScopeRequest` and the public route add `pda_context=False`.
Only literal booleans are supported. Absent/false preserves old behavior. Enabled
scope audit requires the current base output's `pda_context` sidecar presence to
match the config. The input is reconstructed by running the current extractor
with exactly the `literal_recovery` and `pda_context` options. No old output or
caller-supplied recovery ledger is trusted.

Only an exact reconstructed record whose ID is present in the newly generated
PDA recovery ledger can bypass the old standalone-label geometry veto. The
record must still have kind PDA, one complete source-exact label and one complete
page-local source-exact value, decision abstained, reason unresolved_scope,
unit null and claim null. This is a literal admission only: a descriptor is not
retyped as contenido, a code is not expanded, and no unit is assigned here.
Old local-list recovery remains supported under its own explicit flag and fresh
source reconstruction. It cannot imply or silently enable PDA recovery.

Current complete eligible groups are rebuilt for public replay before any saved
response is accepted. A changed source, option, label/value, reason, group, order
or count rejects the bundle. Adding newly eligible PDA records means that a
prior saved group's smaller record list no longer covers the current group.
There is no subset replay or automatic upgrade of old saved responses.

All anchor checks and negative/context guards remain in force. A model can
select only a source-catalogue anchor already selectable in the supplied current
context. The new grammar does not license nearest-project assignment or transfer
project material to a session. Recovered values are immutable and a proposal
still has value_quote null. Accepted results remain detached review candidates,
semantic_validation false, production_applied false, and emit no AtomicClaim.

## Mixed fields and verification

Mixed-field evidence does not enter Mode A: kind null remains unsupported.
Because mixed recovery preserves every typed record exactly, enabling it cannot
change the scope group's records or route. The separate mixed auditor binds its
complete extraction profile and output instead. Both audits may coexist as
independent sidecars; neither consumes the other's proposal as a proven fact.

Required tests cover default/false compatibility, all four literal/PDA option
pairs, a real recovered synthetic PDA entering and passing the replay pipeline,
source-reconstructed rejection of cropped/forged values and stale profiles,
current group coverage and old missing-record rejection, config mismatch before
provider invocation, combined local/PDA groups, and preservation of both input
records and the legacy route/catalogue. No external call is part of these tests.

New external development requires a separate frozen protocol, exact current
inputs/code/prompt hashes, bounded calls and usage receipts. It cannot inherit an
old recording simply because a previous proposal had the same semantic answer.
