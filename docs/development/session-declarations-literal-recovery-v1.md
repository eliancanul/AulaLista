# Opt-in literal recovery: independent local-list reference v1

This is a source-only, synthetic development freeze based on
`740b5ca6d9b852824ebb8abdfcb8aa226f5016bb`. It contains a proposed contract,
authored source strings and original source spans, and independent fixture-only
tests. No new matcher, prediction, scorer, product scanner or old real output
was consulted to choose the answers. No private corpus, private report,
development source reference, FINAL or holdout material was inspected. All new
examples are synthetic structural examples. No implementation is in this cut.

The final bounded scope is **only explicit, structurally closed local-content
lists**. The earlier proposed dotted-code recovery is deliberately not admitted.
It remains synthetic ambiguity diagnostics. Complete terminal-page lists are
also deliberately outside this cut: completed final punctuation alone cannot
prove that a list does not continue outside the supplied source window.

The detached output envelope remains `session-declarations.v1`; the proposed
API opt-in is `literal_recovery=False` by default. Existing default records and
full complete literals must remain unchanged. This experiment changes no
production field, unit scanner, session scaffold, curricular identity, dossier,
UI, Atlas, tribunal or editorial gate. It adds no publication authority or
pedagogical claim.

## Exact compositional local-content labels

On a standalone physical row, admit only these grammatical label forms:

- `Contenido local:`
- `Contenidos locales:`
- `Incorporación de Contenido local:`
- `Incorporación de Contenidos locales:`

Case-insensitive comparison and external horizontal indentation are allowed.
Horizontal internal gaps may use the previously bounded horizontal whitespace
set; vertical separators cannot join label words or the colon. The accented
`Incorporación` may use its ordinary NFC or canonically decomposed NFD spelling.
The unchanged original source supplies all evidence and offsets. An unaccented
prefix, number disagreement, duplicate prefix, missing colon, inline prose,
arbitrary qualifier or synonym is outside the grammar. No contextual inference
turns a mention of local content into a typed label.

The complete label span includes the optional incorporation prefix, every
original internal space, spelling and colon. Only preceding indentation and
following external whitespace are excluded. Recover it as the existing literal
kind `contenido`, never as an objective, activity, SEP content identity or
new field predicate.

## One full, page-local, explicitly closed list

The value is one full original source slice under that label. It is never split
into separate item declarations. This cut requires:

1. At least one bullet item, each on one complete physical line
2. Exactly one repeated marker family: ASCII hyphen `-`, ASCII asterisk `*`,
   or U+2022 bullet `•`; markers and their horizontal gap remain in the value
3. Each item ends with complete sentence punctuation and has balanced quotes
4. No typed label, heading, explicit activity/moment row or local-code row
   inside the list; ordinary inline mentions such as `L1` remain literal text
5. An explicit subsequent **unbulleted colon-labelled heading or field row**
   on the same physical page, outside the value, using the previously recognized
   explicit vocabulary or an exact new local-content label

An explicit closure may have a value on its row, for example
`Recursos: Cartas sintéticas.`, or two labelled fields on that row. It proves
only the list boundary; it creates no declaration, unit or relationship.
An `Inicio:` row can close an already complete preceding list, while preventing
subsequent recovery through an activity block. A subsequent exact local-content
heading can close the preceding list and introduce a distinct physical list.

The closure vocabulary is bounded by the pre-existing `HEADING` names in
`scripts/session_declarations.py` and explicit field/barrier label families in
`curriculum/overview_fields.py`, plus the exact local-content forms above. These
include recognized lesson moments, activity headings, campo, materials/resources,
evaluation/products/evidence, project/purpose/finality, planning metadata such
as theme/objective/time/organization/phase/grade, annexes, methodology/scenario,
ejes, instruments, adjustments and the already recognized content/PDA/process
field forms. Only their already supported label spellings/qualifiers are
admitted, with an explicit colon on this closure row. This is a vocabulary reuse,
not a general-colon-row grammar. An unknown explanatory row such as
`Nota adicional: Texto aparte.` cannot prove closure and leaves the list
uncertain. Generic unknown headings, numbered narrative rows and code-shaped
rows do not become closure evidence.

Blank rows and original indentation between completed items are retained
inside the single span. CRLF stays CRLF, NBSP stays NBSP, and decomposed letters
stay decomposed. Exclude only external whitespace. Wrapped items, numbered
lists, mixed markers, doubled markers, incomplete punctuation, unmarked prose,
unbalanced or mismatched quotes and bulleted headings are not admitted. A
complete list at the last page/window edge still lacks explicit closure and
must remain uncertain. A heading or list continuation on another page cannot
provide that closure. No source fragments are joined across pages.

## Safe source context cannot be manufactured by the new header

The label must occur in an already safe page-local planning metadata region.
The new label and a canonical field name cannot reset an activity, example,
quotation, nonadoption or unknown prose region. Initial `DATOS GENERALES` and
existing safe planning metadata can provide bounded context, but a later
`DATOS GENERALES` cannot erase unsafe source-prefix evidence.

An immediately preceding **independently admitted affirmative typed literal**
can corroborate on-page metadata when its own full label and complete value are
already established by the unchanged baseline safety and boundary rules, and
only whitespace lies between that full value and the local-content header.
Keep that baseline declaration separate and unchanged. Punctuation alone, a
typed-looking line, an uncertain prior value, an unlabelled page-start
continuation or note, or an intervening prose row is not this proof. Unsafe
activity/quotation/example/nonadoption context still vetoes recovery even when
the preceding text otherwise resembles a complete literal. The local header
alone cannot reset unknown prose. A source-backed complete local list may be
followed by another exact local label under the same bounded context.

Open or mismatched source quotation, an explicit example and explicit
nonadoption earlier in the supplied pages remain unsafe across page boundaries.
Do not discard that prefix when looking at a later local header or planning
root. Explicit `Inicio`, `Desarrollo`, `Cierre` or `Actividad` rows inside the
current metadata region veto later admission unless an already recognized real
unit or independently supported reset establishes a new safe region. The new
local label is not such a reset. Unlabelled activity bullets outside a previously
completed literal value likewise do not license a new metadata block.

An explicit reset may reuse only an **unchanged independently safe existing
real-unit/project source proof**, never a new shortcut. In particular, the
existing `_governing_book_project` profile in `scripts/anchor_scope_catalogue.py`
and the earlier independent `project-anchor-structure-v1.md` contract require
one same-page `Planeación didáctica` root, one complete `Proyecto del Libro
[de Texto]:` heading/title, ordered nonempty `Escenario:`, `Propósito:` and
`Producto:` witnesses, and the exact `Contenidos/PDA asociados al proyecto:`
section, with all existing source-prefix, quotation, example/nonadoption,
activity, duplicate and intervening-barrier protections intact. Do not relax
that proof or call a root line alone sufficient context.

Three source-prefix controls use the identical complete synthetic profile on
page 2. The positive has a physically closed prior example/nonadoption paragraph
on page 1, terminated by an actual blank paragraph before the root. The otherwise
identical no-gap prefix remains active and cannot be reset. An inherited open
quotation remains unsafe even across the blank paragraph. Their profile
witnesses and prefix facts are separately authored in scope metadata and checked
against original slices, without executing the proof or matcher. A blank after
the root cannot erase unsafe context present at the root. This existing proof
supplies **context only** here: the newly recovered list retains null unit and
null claim, with no project assignment or invented curricular relationship.

This is a bounded textual grammar. It is not a general semantic classifier,
and limited recall is acceptable. Uncertain source context remains uncertain.

## Dotted descriptors remain ambiguity diagnostics

A row shaped like 1–4 supported Spanish letters, 1–4 ASCII digits, a period,
horizontal space and a complete description may be metadata or literal
narrative. The synthetic diagnostics cover ASCII, Spanish NFC/NFD letters,
CRLF, repeated physical labels, complete preceding sentences, same exact next
numbered-PDA prefix, different prefixes and canonically equivalent but
nonidentical spelling. **None of these licenses the new recovery route.**

Even a repeated exact prefix and a following standalone numbered-PDA label do
not prove whether the descriptor belongs to the prior literal value. Without
independent structural evidence, cropping the preceding value would choose an
interpretation the text does not establish. Keep that prior declaration as
`uncertain_boundary`; do not shorten, normalize, invent or assign its value.

Explicit narrative/example-marked variants demonstrate a distinguishable
adversary. If two layouts are textually identical in all supplied context but
their intended meanings differ, this reference cannot assign contradictory
oracle answers. That indistinguishability is an inherent limit, not a hidden
semantic gold label. The 17 independently complete following PDA declarations
are baseline-preservation controls, including one existing session candidate
and one existing project abstention. An additional independently complete
typed `Contenido` is the separate adjacency control for a local list. No
descriptor row itself is a declaration.

## Recovery cannot assign units or create AtomicClaim

Every newly recovered list has:

- `kind=contenido`
- `decision=abstained`, `reason=unresolved_scope`
- `unit=null`, `claim=null`
- One exact whole-label reference and one exact full-value reference

These decisions apply even when a session or project anchor is visible on the
same page. The recovery extension never joins a unit, inherits a previous-page
unit, changes an existing candidate, upgrades an abstention, or emits a separate
claim per list item. Baseline complete declarations retain their existing unit,
decision, full literal, evidence and claim behavior. Their unchanged existing
rules remain independently governed by the earlier contracts.

Use original Python Unicode character offsets with exclusive `end`, not UTF-8
byte offsets or offsets in normalized text. Every label/value reference retains
the supplied source hash, physical page and exact original quote through the
existing `region={kind: text_offsets, start, end}` convention. Repeated physical
blocks require distinct offset-based record identities. Additional extraction
proof metadata, if used, cannot replace this evidence or assert unit identity.

## Independent frozen reference and separate denominators

`tests/fixtures/interpretation/session_declarations_literal_recovery_v1.json`
uses the existing `session-declarations-reference.v1` envelope. `design_tags`
are source-review annotations only, never matcher inputs. The scope metadata
separately lists `new_recovery_opportunities` and
`baseline_preservation_opportunities`; those sets partition all 37 authored
literal opportunities. They do not replace original spans.

Fixture SHA256:
`1a8f35662fe3d097cd14ce874d3e37ca9a52ecbace93ec2a7a371bfaf9d96184`.

Fixed separate denominators:

1. 119 synthetic documents
2. 37 complete literal opportunities: 19 new local-list recoveries and
   18 baseline-preservation literals
3. 19 new recovery opportunities, all local lists, all explicit unresolved-scope
   abstentions; zero admitted dotted-descriptor recoveries
4. 37 independent unit-assignment opportunities: 35 unresolved/null, one known
   session and one known project; all new recoveries are within the null group
5. One pre-existing session-candidate opportunity and 36 scope-abstention
   opportunities; new recovery contributes no positive session-claim numerator
6. 109 negative/ambiguous challenges, including 48 dotted-descriptor challenges;
   their safety, explicit abstention, silence, multiplicity and invalidity must
   remain separate
7. 85 documents without affirmative complete declarations, including two
   clean-silence documents with no challenge
8. Three source-proven context-reset controls: one safely corroborated context
   recovery and two source-unsafe challenges; this diagnostic overlaps the
   preceding literal/challenge strata and is never added to recall

The existing scorer is unchanged. Preserve exact literal detection, unit
assignment, joint detection/assignment, session claims, unresolved abstention,
extras, duplicates and negative safety as separate measures. Silence is not an
explicit abstention or positive recovery. A one-item excerpt from a multi-item
list, cropped incorporation prefix, normalized quote, contaminated value, wrong
page or wrong span cannot earn full literal credit. Negative document counts
cannot be added to positive recall. Missing/zero denominators are N/A.

Scope contains an independently computed SHA256 binding for every exact page
array: UTF-8 JSON using `ensure_ascii=False, separators=(",", ":")`.
This synthetic page-snapshot hash can be used as both caller source binding and
extraction binding. It is not an original PDF-byte hash or proof of PDF/OCR work.

The ten older interpretation fixture hashes, existing scorer hash and unchanged
existing project-context proof/contract hashes are pinned in the fixture and
independent tests. All their bytes are preserved.
Scorer SHA256 (`scripts/evaluate_session_declarations.py`):
`393285dc7a472febecb3056f162eeecb91510f8c927db5d4e516e2e7c053a8ca`.

## Fixture-only verification

Run without loading the matcher, scorer or product scanner:

```text
python -m unittest discover -s tests -p test_session_declarations_literal_recovery_reference.py -v
```

These checks validate frozen hashes, exact spans, full labels/lists, repeated
physical identities, original Unicode/CRLF, source bindings, separate authored
denominators, baseline/recovery partition, null-unit recovery and explicit
adversarial coverage. They do not execute an extraction grammar to produce the
expected answers and do not establish implementation accuracy.

An eventual matcher evaluation must be a separate step after this freeze.
Nothing here establishes global reliability, private/final performance,
curricular alignment, teacher validation, pedagogical validity, real API cost,
time saved or readiness for publication.
