# Bounded label interpretation, matcher v2

This development iteration follows scorer-only commit
`0c1bfd776cccf054c91cd5e82855535ff0020de0`. The earlier matcher, scorer, reports
and primary synthetic references remain preserved. The source/output envelope
stays `session-declarations.v1`; implementation identity is separately versioned
in claim extraction metadata and pinned by commit.

## Reference frozen before implementation

`tests/fixtures/interpretation/session_declarations_labels_v1.json` contains
18 synthetic documents with 17 literal declarations: 16 session candidates and
1 project-scope abstention. It also contains 13 challenges and 9 documents with
no affirmative declarations. It uses the lossless structured scope metadata
supported by evaluator v1.2.

SHA256: `a5674e0ef46a8b8e6f374df3e6198bdf917ff3b2ec04ec6c96b23e9b2105d9e9`.

These are newly authored synthetic regressions prompted by already disclosed
development-format patterns. They are not blind, held-out, private-source,
final-reserve or teacher-validated examples. Their source values are synthetic.
No old fixture is edited, and no private reference is read to implement them.

## Literal numbered labels

Recognize a bounded local label grammar: `PDA` plus literal digits, with optional
horizontal whitespace, optionally preceded by a local prefix of 1–4 letters
and 1–4 digits followed by horizontal whitespace. Examples include `PDA2:`,
`PDA 003:` and `X7 PDA2:`. The full original label, prefix, digits, spacing and
colon are retained in the `label` source span. Digits are not cast, normalized,
or interpreted as SEP identifiers. A zero or padded local number is merely
source text. Unknown prefix shapes remain outside this bounded admission.

Repeated labels or values remain separate by physical source occurrence, even
inside one session. Existing quoted, negated, suggested, absent, table, incomplete
window and unit-scope guards continue to apply.

## Explicit subtype inside a combined heading

`Contenidos/PDA: Contenido: Formas.` contains a combined display container followed
immediately by one explicit child label. With no intervening prose, no table
separator and only one child label on that physical line, use the child label
(`Contenido:`) and its complete literal value. The container itself does not
create an additional declaration, curricular value or claim. A separately
labelled `PDA:` on a following line is an independent opportunity. The symmetric
explicit PDA child is allowed under the same bounded condition.

Without an explicit child, the combined label still abstains. Multiple typed
values on the same physical row, pipes, quoted examples and prose mentioning
the labels do not become affirmative declarations. The parser does not infer
table geometry or expand unit scope through cross-page proximity.

## Evaluation

Run both frozen synthetic strata separately with scorer v1.2. Report strict
session-claim precision/recall over all emitted claims, literal detection,
known-unit assignment, project/unresolved abstention, and the new challenge
safety/explicit-abstention/silence diagnostics. Preserve baseline outputs so the
same fixed opportunities can be compared. No result is a claim of 90% global
reliability or curricular correctness.

## Horizontal-boundary repair, matcher v2.0.1

This incremental repair preserves the earlier `420334b` cut and both frozen
references. It corrects only the v2 numbered-label and combined-container
admissions. Their horizontal whitespace is now explicitly tab or a Unicode
space (`U+0020`, `U+00A0`, `U+1680`, `U+2000–U+200A`, `U+202F`, `U+205F`,
`U+3000`). Vertical separators (`CR`, `LF`, `VT`, `FF`, `U+001C–U+001E`,
`U+0085`, `U+2028`, `U+2029`) cannot join local code, PDA, digits or colon,
or serve as numbered-label indentation. Container admission independently
requires horizontal indentation and gap, and rejects vertical separators
through the end of the child label, including inside either label.

The legacy label grammar, line scanner, evaluator and unit scope are unchanged.
CR/LF already split into independent lines: a typed declaration on a following
line remains eligible in its own right, never as a same-line container child.
The separate `test_session_declarations_horizontal.py` synthetic regressions
cover every listed vertical separator plus horizontal spaces, tabs and NBSP.
They do not add opportunities to either frozen reference. Activity bullets and
structural cross-page scope remain outside this repair.
