# General/project metadata: pre-matcher literal reference v1

This proposal is a bounded development extension of
`ad1616a1d8b958bbcc7652c814369ca8b1474416`. This commit freezes only this
contract, synthetic source/reference data and independent reference tests. No
matcher, scorer, scanner, production model or output is changed or executed to
choose the expected answers. The previous cut and all its fixtures remain
unchanged. Nothing is published.

The hypothesis is that a complete literal declaration can occur in a general
or project metadata block without a recognized physical session. Detection and
unit assignment are separate questions. The existing detached envelope stays
`session-declarations.v1`; the existing predicates, evidence roles and claim
rules do not change. No project ontology, field membership, curricular truth,
SEP identity or editorial authority is introduced.

## Small textual admission, not a general project interpreter

A single formatting hyphen may precede one complete existing typed label,
ending with a colon, on a physical line in a qualifying metadata block. The
label span excludes the hyphen/indentation and includes the entire original
local code, PDA number, internal horizontal spacing and colon. The value is one
complete page-local original slice. All old activity, quotation, table,
nonadoption, source-boundary, multiline-value and scaffold-proof protections
remain in force.

The label families remain the existing Contenido(s), Contenido(s)
curricular(es), PDA(s), numbered PDA and long-form process labels. A local code
is still a prefix only to a **numbered PDA** label. The local-code grammar is
1–4 Spanish alphabet letters followed by 1–4 ASCII digits and at least one
horizontal space before PDA. Supported letters are ASCII A–Z/a–z plus
ÁÉÍÓÚÜÑ/áéíóúüñ, including their ordinary canonical decompositions: acute on
A/E/I/O/U, diaeresis on U and tilde on N. Count decomposed pairs as letters,
never as additional letters. Other scripts, arbitrary combining marks,
code-internal separators and incomplete/oversize codes are outside this cut.
Unicode case-fold lookalikes such as K, İ and ſ are not Spanish-code letters;
an unrestricted case-insensitive ASCII range must not silently admit them.
Recognition may compare an NFC copy of the code; offsets and evidence must
always use the unchanged source. No normalization is applied to quoted evidence
or literal values. Number padding and case remain literal, not catalogue IDs.

This extends the old ASCII code admission, not arbitrary prefixes. In
particular, a code alone does not type a declaration and `-Leer ... PDA1:`
cannot become a declaration. Multiple hyphens, other bullets, missing colons,
vertical separators within the label and multiple typed values on a row are
not admitted by this new route. The old independently admitted unmarked labels
remain governed by their existing rules.

## Page-local field context

The new context signal is a complete standalone physical line whose text is
exactly one name from the product's existing CANONICAL_CAMPOS vocabulary:

- Lenguajes
- Saberes y pensamiento científico
- Ética, naturaleza y sociedades
- De lo humano y lo comunitario

Case-insensitive matching and external horizontal indentation are allowed.
This cut does not invent aliases or require any change in the product scanner.
**Using a canonical name alone as a block signal is a new development
hypothesis**, not a claim that the current scanner recognizes such a header.
An explicitly labelled `Campo:`, `Campos:`, `Campo formativo:` or
`Campos formativos:` line containing exactly one such name can also establish
this textual context. No PDA-to-field relation is emitted. The canonical name
is neither evidence of the declaration's semantic subject nor a unit anchor.

Before the first field context, the current page-local metadata region may
contain only blank lines, an initial DATOS GENERALES line, an explicit unit
header, or complete single-line planning metadata already permitted by the
previous contract. An empty `Proyecto:` may delimit unresolved general metadata
but never resolves a project. Free prose, examples, nonadopted proposals,
quotation context, activity lines and lesson moments veto the new admission.
A field name cannot reset an activity or example block. An initial DATOS
GENERALES heading is not permission to reopen metadata after activities.

An explicit new unit already recognized by the unchanged product can start a
new metadata region. This is why a new project after an earlier session's
activity has a positive control. Unknown headings do not create that reset.
The previous marker route remains available without requiring a
canonical field heading; this proposal must not tighten or widen its proofs.

Within an admitted field block, a contextual local row may have the form
`CODE` + horizontal space + a nonempty single-line description ending with
sentence punctuation. For example, `L1 Representaciones escritas.` is context
only. It is not a typed Contenido label and creates no declaration. This cut
does not admit colon-code rows or wrapped contextual descriptions. Codes on
that row and on a following PDA do not have to match: matching them would
invent an identity relationship. A code row must not contain a pipe, typed
declaration label, quotation wrapper, lesson/activity heading, or an example or
nonadoption marker. No semantic classifier guesses whether arbitrary free
prose is really metadata; unfamiliar or ambiguous layouts stay outside the
new admission.

Blank lines, complete typed declarations, contextual code rows and canonical
field lines can occur repeatedly inside the block. Multiple distinct physical
declarations remain distinct, including identical labels and identical values.
At a switch, an exact field line or a bounded code-description row becomes a
value boundary only after the preceding value is already complete and the
following nonblank structure corroborates another field/code/declaration block.
It cannot be used to manufacture completion or crop an unfinished value. A
context-only block can validly produce no declarations.

Inline mentions of a field or code in a literal value remain part of that
value. Balanced quotes inside a complete affirmative value remain literal.
A field/code-shaped row inside an unfinished value or an explicit example
has no uniquely established boundary: retain uncertainty, not a shortened
positive value. This is the explicit stopping limit of the proposal, rather
than an invitation to reconstruct arbitrary discourse.

An actual activity bullet or labelled activity, an unknown heading, a quote or
example/nonadoption block, a table/mixed row, or Inicio/Desarrollo/Cierre ends
eligibility. Do not skip it and resume at a later PDA or canonical name. A
complete preceding declaration may still be detected without absorbing the
stop. Values and context do not carry across a physical page boundary.

## Unit assignment stays independent

Every positive literal opportunity requires exact label and full-value
evidence even when its record is an abstention:

- A safe, already recognized same-page project anchor yields the existing
  project unit, `decision=abstained`, `reason=project_scope`, `claim=null`
- Without a safe existing unit, use `unit=null`, `decision=abstained`,
  `reason=unresolved_scope`, `claim=null`
- The two same-page session controls retain their existing explicit session
  candidate behavior and `unit_scope_basis=same_page_explicit`

This new literal context never licenses a session join. A project, canonical
field or local code is not a session anchor. A later session cannot inherit
earlier project declarations. A previous-page project cannot be inherited,
and a previous-page session still requires exactly the pre-existing named
continuation or structural-scaffold rules and proofs. The new context signal
must not be added to the scaffold grammar or used to relax it.

The synthetic project controls use titles with boundaries already supported
by the existing project extractor (an explicit labelled field or a blank line).
No gold project unit depends on the new bare-field context signal changing how
the project title is extracted. Unknown/empty project headings stay unresolved.

## Frozen independent reference

`tests/fixtures/interpretation/session_declarations_project_metadata_v1.json`
uses the existing `session-declarations-reference.v1` envelope. Document
`design_tags` are review annotations only; they are not matcher inputs or
replacement evidence. Authored spans select original Python Unicode character
offsets, not bytes. The fixture is synthetic development material prompted by
an already-known format hypothesis. No private corpus, historical private
output, development source reference or FINAL/holdout material was inspected.

SHA256: `9323aaaba522c8397aeb675afcafbd745c01d71c99338dbcb5745eded9f97d13`.

The fixed denominators are separate:

1. 46 documents and 28 affirmative literal opportunities
2. 28 unit-assignment opportunities: 10 known project anchors, 2 known session
   anchors and 16 explicit unresolved/null opportunities
3. 2 session-candidate opportunities; only these enter positive session-claim
   recall and strict claim scoring
4. 26 scope-abstention opportunities: 10 project and 16 unresolved; silence is
   omission, not an explicit abstention or successful literal detection
5. 40 negative/ambiguous challenges, with safety, explicit abstention,
   silence/no-claim, false candidate, duplicate and invalid outputs separate
6. 27 documents without affirmative declarations, including 2 clean-silence
   documents with no challenge; never add these to positive recall

Future scoring must retain exact literal detection, assignment, joint
detection/assignment and strict session claims as distinct results. An exact
literal with the wrong or invented unit cannot receive joint/strict credit.
Wrong code spelling, cropped code prefixes, normalized evidence, one-token
values, contaminated values, duplicates and extras cannot get full detection
credit. Safety silence on a negative is useful but is not an explicit recorded
abstention. N/A denominators stay N/A.

Independent pre-matcher tests validate hashes, IDs, spans, source preservation,
authored expected decisions, separate denominators and the listed coverage.
They import neither matcher, scorer nor product scanner and do not infer
expected answers by executing any extraction grammar. They prove reference
consistency only, not future implementation accuracy. Behavioral implementation
and mutation tests are a separate later step after review of this freeze.

## Preserved reference bytes

- `session_declarations_v1.json`:
  `3c7a9aedf5be30b8755d12e6567d154b5d54859d1ff0a868727b8576060201f5`
- `session_declarations_labels_v1.json`:
  `a5674e0ef46a8b8e6f374df3e6198bdf917ff3b2ec04ec6c96b23e9b2105d9e9`
- `session_declarations_scaffold_v1.json`:
  `3b83730070b9e04859a39af78065dbf70399bdfb3a6d5edbbc3a8941d71f3b09`
- `session_declarations_scaffold_supplement_v1.json`:
  `f5136feae92c5c186845f2b080113a3a36f1aa2d1e20a2c8ebfa6b3bdd6cbc0d`

All older strata and receipts remain separate. No claim is made about global
reliability, hidden/private performance, OCR, real API cost, curricular alignment,
pedagogical validity, teacher time saved or publication readiness.
