# Pre-output evaluation amendment v1.1

This explicit amendment preserves the original contract/reference commit
`015a6cc4ef617282815e0c817ac216a11449f549` and unchanged fixture SHA256
`3c7a9aedf5be30b8755d12e6567d154b5d54859d1ff0a868727b8576060201f5`.
It is recorded before the first execution or inspection of matcher outputs.
The matcher source was drafted, but no output was used to establish this rule.

## Unit identity versus anchor completeness

An independently authored unit anchor may contain only its identifying label
(`Sesión N`), while extraction retains a whole literal header and title. Physical
identity must not depend on whether the annotator included that optional title.

Identity still requires the same unit kind, page and exact start. An anchor with
a different end may identify the same occurrence only when both reference and
prediction retain the entire source identifier: a numbered session label and
its complete integer token, or the complete project label through its colon.
One anchor must be the literal prefix of the other. The longer anchor must end
within that physical header line, before CR/LF, and cannot intersect another
annotated unit, declaration label or challenge. Cropping `Sesión 10` to
`Sesión 1`, cropping away the number, or selecting the whole page cannot earn
unit credit. Unsupported header shapes require exact anchor equality rather
than speculative normalization. This small checking grammar is independent of
the product scanner and matcher.

Report exact equality of anchor spans separately from identity correctness.
Detection of the declaration still requires exact label/value/type; this
amendment does not relax declaration recovery or allow textual contamination.

## Source and reporting boundaries

The evaluator preserves the supplied `reference_kind` and `scope` verbatim in
its aggregate report. An external reference path is accepted only when its use
is separately authorized. Having a CLI parameter does not authorize reading a
private corpus or final reserve. Default reporting contains counts and IDs, not
source quotations. Synthetic and later authorized development strata stay
separate, and neither is teacher gold or evidence of 90% global reliability.
