# Detached marker/scaffold implementation

This implementation follows the reviewed pre-output freeze
`abd65a49a5ffd146b9143aada9b639ab58a812a7` and leaves its contract, both fixture
files and the earlier `8093752` cut intact. The matcher identifies itself as
`session-declarations-matcher.v3`; the independent scorer is version `v1.3`.
The output envelope remains `session-declarations.v1`.

## Bounded behavior

- A single horizontal hyphen prefix can format a complete typed colon label
  only in a source-verified metadata block before lesson moments. The marker
  is excluded from the literal label span. Prose, examples and activity bullets
  do not receive this admission. The earlier no-marker regression remains
  recorded in commit `8093752`; its current regression specifically verifies
  abstention inside activities, while the new frozen positives cover metadata.
- A structural cross-page proposal requires a unique immediately prior session,
  a complete metadata-only tail, a complete current metadata/declaration prefix,
  `Inicio` as the first current moment, and containment in the existing product
  segment's admitted literal range. No product scanner logic is changed.
- The full tail and prefix remain exact source slices, including CRLF and
  indentation. The claim distinguishes `structural_scaffold_proposal` from
  `explicit_continuation` and `same_page_explicit`. Every claim keeps null
  confidence and the existing human-review state.
- In this tentative cross-page context only, a completed declaration preceding
  a separate prose line can retain its exact literal value. The prose still
  blocks assignment. This is the source-bounded behavior required by the frozen
  `scaffold_free_prose_after_pda` negative; it does not turn the prose into a
  continuation or award positive scope credit.

## Independent scoring and replay

The scorer's source grammar does not import the matcher or product scanner.
It validates scope proofs independently and withholds unit/joint/strict credit
for missing or invalid bases/proofs while preserving otherwise exact literal
detection. The optional `--scope-contract` argument binds the reviewed
supplement to the original base-reference bytes and reports its five additional
negative declarations separately.

Historical replay uses only saved synthetic predictions from `bfa5146` and
`8093752` on the primary and numbered-label fixtures. Those original outputs
are not regenerated or edited to acquire the new scope metadata. Compare all
historical metric values, both aggregate and per-document, with the old and new
scorers; new report-version/definition metadata is a separate change.

Current matcher records on those two older synthetic strata also remain equal
to their `8093752` records after explicitly excluding only extraction version,
matcher-version metadata and the newly declared scope basis. Original output
files remain untouched. This comparison does not normalize label/value source
spans, evidence, physical IDs, decisions or reasons.

Focused tests and synthetic development scores do not establish global recall,
SEP alignment or pedagogical correctness. Private development evaluation is
performed separately after the implementation commit is frozen. No production
provider, schema, dossier, publication gate or API integration is activated.

## Post-review repair: matcher v3.0.1 and scorer v1.3.1

Commit `534bbd3` and its passing suite receipt are preserved. Independent review
found safety cases outside that suite; this incremental repair addresses only
that closed set, with separate synthetic regressions and unchanged gold fixtures:

- A formatting hyphen is equivalent to empty indentation for the mixed-row
  guard. Two typed colon labels on one row remain ambiguous, including tabs.
- Scaffold quotations require matched pairs, rejecting orphan or mismatched
  closing marks. The legacy quotation parser is unchanged.
- Auxiliary-proof isolation applies only to candidates. Abstentions retain
  ordinary reference validation, so invalid auxiliaries cannot earn explicit
  abstention or falsely establish no-claim safety.
- Explicit moments, sessions, projects or general-data resets embedded in the
  remainder of a session header or planning-metadata value veto a scaffold.
- Symbolic and numbered activity bullets cannot be absorbed as wrapped
  curricular metadata. This only blocks structural proof; otherwise exact
  declaration evidence remains independently scoreable.

The matcher and evaluator implement their respective guards independently. No
previous receipt is relabelled as having tested these later review findings.

## Residual guard repair: matcher v3.0.2 and scorer v1.3.2

The full suite for `f0c8b3f` was explicitly interrupted after review found three
variants of those same guards. Its receipt records interruption, not success.
The incremental repair checks quote state entering the scaffold from the whole
supplied document prefix, uses explicit Unicode-horizontal indentation for the
activity-bullet veto, and rejects embedded structural labels inside complete
typed declaration values as well as planning metadata. These checks apply to
the new structural route; legacy field extraction and frozen references remain
unchanged. Focused verification and review precede the final full suite.

Matcher v3.0.3 and scorer v1.3.3 additionally reject U+001F UNIT SEPARATOR as
an unsupported control in scaffold structure. It is neither normalized away
nor classified as horizontal whitespace. This closes the final reported
activity-indentation variant, with separate header, metadata and prefix tests.
