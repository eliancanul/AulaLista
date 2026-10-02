# Dotted-descriptor PDA context: implementation and measured limits

The source-first contract is `session-declarations-pda-context-v1.md`.
The original synthetic fixture was frozen before implementation at SHA-256
`b3c87fe0af0d7bdc1cfb556e802dee22177b3625a7986c9b31eaf0a483f96cf1`.
An independently authored, expectation-preserving typography supplement adds a
single physical formatting hyphen to structural coded PDA labels. Its SHA-256 is
`7ffc16f2e399f47a5b9bccf801a6fe6f63a5c7b44dce0ae8535ff404106ef26b`.
Neither reference was changed to match predictions. The supplement has 151
insertions across 113 of 132 documents, with all spans remapped and verified.

## Detached interface

`extract_declarations(..., pda_context=True)` invokes
`scripts.pda_context_recovery.py` after legacy extraction. The CLI option is
`--pda-context`. `False` remains the default and must be an actual boolean.
No product parser, unit scanner, scope grammar, evaluator, prior fixture, model,
database, provider transport or editorial state is changed.

Only a legacy `pda/abstained/label_mention` record without a value or claim can
change. Its existing physical ID and exact label are retained. It gains a full
page-local value, `reason=unresolved_scope`, `unit=null` and `claim=null`.
All other records, ordering, prior values and claims are preserved exactly.
Descriptors are source context, never promoted to Contenido or field identity.

The `pda_context` sidecar records the method
`explicit-pda-local-context.v1`, label/value UTF-8 hashes and exact source-backed
descriptor, campo-text and closing-boundary references. If a new unit cuts the
region before page end, its real source span is the boundary witness. A true
page ending has `boundary=null` and `boundary_kind=page_end`. Newlines, source
spelling and Unicode offsets are never normalized. NFC is used only in the
comparison copy for canonical campo text.

Source-only safety checks preserve horizontal versus physical/control
boundaries, strict paired quotation including single/curly quotes, active
example/nonadoption context, typed/structural interruptions and incomplete
predecessors. Explicit examples, activity headings and nonadoption in values
cannot become affirmative evidence. Nested descriptors/campos cannot become
wrapped description text. The bounded lookahead checks a complete next PDA
value before a descriptor or campo can close the preceding value.

The existing scope-audit contract deliberately rejects this sidecar before any
provider call (`pda_context_scope_audit_unsupported`). A subsequent integration
must reconstruct the opted-in source state and current whole groups; old
recordings cannot establish a new group's scope. This cut does not implement
or claim such a scope decision.

## Separate measured denominators

The original synthetic reference has 132 documents, 64 literal PDA opportunities
and 104 challenges. Default extraction detects 46/64; the opt-in detects 49/64.
Only three of those are new recoveries: many source opportunities already had
unmarked labels, whose legacy behavior must remain unchanged. The independent
reference also intentionally exposes old boundary/scope/safety limitations.

The marked supplement has the same independently authored 64 opportunities and
104 challenges. Exact literal recall is 0/64 before and 60/64 after; all 60
recovery-ledger values match their full authored label/value pair and no new
recovery is asserted on a challenge or extra. Four conservative gaps remain:

- A multiple-complete-sentence wrapped value rejected by the unchanged literal
  boundary grammar
- A project heading not recognized as a reset by the unchanged unit scanner
- Two literals after an unresolved earlier Contenido block, whose ambiguity is
  deliberately not repaired or used as permission to resume recovery

The marked supplement already had five incorrect legacy literal assertions.
They remain untouched. Consequently, whole-output precision is 60/65 (92.31%),
not 100%; the new-recovery ledger's precision is 60/60. The original stratum's
inherited assertions are also reported by the unchanged scorer, not suppressed.
Neither fixture offers new session-claim opportunities.

A separate exposed-development comparison reuses exact six-page windows from
five authorized sources and unchanged frozen references. The primary reference
hash is `88267ce7c24022cfa7dfff978e54181c7a55f4a6a3ddcdb47953fc9d101dc8d3`.
The opt-in recovers 13 previously missing full PDA literals. Primary literal
recall rises from 22/36 to 35/36 (97.22%), and the alternate boundary-sensitivity
reference rises from 22/35 to 35/35 (100%). Both outputs retain literal precision
100%, with zero extras or duplicates. Deterministic joint detection/unit stays
14/36 and 14/35, respectively. No descriptor becomes a Contenido and no session
claim is added. These numbers do not establish 90% reliable joint interpretation,
held-out accuracy, teacher validation, SEP alignment or production readiness.

## Reproduction

Run reference-only checks independently:

    python -m unittest discover -s tests -p 'test_session_declarations_pda_context*_reference.py'

Run behavioral/default/scope regressions:

    python -m pytest -q tests/test_session_declarations*.py tests/test_anchor_scope_audit.py

Run the full repository suite and application checks:

    python -m pytest -q
    python manage.py check

Adversarial regressions include polarity after punctuation without whitespace,
quote-led/late-example values, single and curved quotation across pages, control-
only physical rows, inline fake resets, nested descriptor/campo rows, incomplete
previous values, correct region-boundary witnesses, compositional flags and CLI
exclusive output. All preexisting helper ASTs are unchanged; only extraction/CLI
hooks and the explicit unsupported-audit guard modify old code.
