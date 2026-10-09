# Source structure in phase-based plans

The public acceptance seams are `CurriculumSourceInterpreter.prepare` (a real,
synthetic PDF to a serializable dossier), `verify_curriculum_dossier` (that
dossier against the physical PDF), and the rendered review templates. No
provider calls are needed. These are software acceptance checks, not a claim of
pedagogical validation or exhaustive extraction on private documents.

## Compatibility bridge

The persisted `sessions` collection remains readable. New entries carry
`unit_kind`: `declared_session`, `project_review`, or `unknown`. A legacy entry
without the field stays `unknown`; reading it does not rewrite its data or
promote it to a declared class. The source verifier recomputes a non-unknown
claim from the existing session/phase scanner. Source fields, activities,
annex references, history and human decisions remain available.

A phase-based project has no automatically assigned inicio/desarrollo/cierre.
Its first and last instructions do not establish those moments. The operational
queue does not manufacture missing session-moment questions for that unit.
Existing persisted moment fields remain readable. The display counts declared
sessions separately and calls this container a project review unit.

## Source blocks

`source_structure` version 1 contains `phases` and `blocks`. It is separate from
the legacy `activities` collection, which only receives explicitly delimited
activity text. Phase IDs and block IDs identify physical occurrences. Each
fragment retains document hash, physical page, exact excerpt and offsets into
the extracted page text. These are text offsets, not PDF coordinates.

Roles are provisional: instruction, activity, resource, question, step,
heading, resource_heading, or unassigned. A bullet alone is insufficient to
create an instruction or activity. A resource heading changes block context,
not the remainder-of-page boundary. Subordinate questions/steps retain a
parent block; a continuation retains its own per-page fragment. Ambiguous text
stays visible. A curricular grade-band phase in the overview is outside the
work-phase scope and does not create a work phase or class.

A standalone homework label is a heading. A recognizable action directly in
that task context can be an unbulleted instruction candidate; a new phase or
resource section ends the context. An adverb ending in `-mente,` followed by a
recognizable action is also an instruction candidate. Neither rule promotes
material nouns or establishes a principal-activity count. Both retain the same
proposed/ambiguous/pending states and literal source fragments.

The verifier recomputes the complete structure and checks exact JSON types;
edited roles, memberships, excerpts, offsets, and boolean-as-page coercions do
not pass. Passing mechanical checks does not confirm the proposed roles.

## Material titles and candidate pages

Existing numbered annexes keep their IDs and single-page discovery behavior.
Their header offsets also delimit a preceding named material on the same page,
so an adjacent numbered heading does not erase earlier exercise text.
Quoted worksheet titles near a material mention can also identify a candidate
heading. Such references have a stable title-based ID and an empty printed
annex number: numbering is never invented. Several occurrences of the same
title remain candidate alternatives and require review.

For a named worksheet, `heading_page` and `candidate_exercise_pages` are distinct.
A title at the foot of one page can precede exercise content on later pages.
Literal `source_fragments` retain both heading and content. Candidate ranges
stop at the next detected material heading or a new project/session boundary.
These ranges remain heuristic candidates, not print authorization. The legacy
single `confirmed_page` stays empty; `confirmed_pages` on a source candidate is
also empty. This change does not implement bulk multipage confirmation/export.

Phase units now retain numbered and named material references. An explicitly
delimited activity is linked only when its own physical evidence contains the
material mention. The verifier recomputes named candidate ranges and rejects
changed source fragments or unrelated candidate-page claims.

## Limits

This is an additive bridge for the existing phase-review route, not a migration
to a complete project/fase/session hierarchy. It does not add OCR or infer
column geometry. Role recognition and continuation/title detection are
conservative heuristics, and unknown text must remain reviewable. Named title
discovery currently requires a quoted source mention and a matching heading.
Quoted names and matching headings may wrap across lines on the same physical
page. The complete quoted span remains literal; only the displayed title is
whitespace-normalized. Material-list context can continue through a local
conjunction, not through unrelated paragraphs or another physical page.
Matching prefers the longest complete known title, so a short title does not
consume the first line of a longer one.

An editorial or unresolved prefix before the next material heading is retained
in `unassigned_fragments`; it does not, by itself, extend the previous
worksheet's exercise-page candidates. Exercise text before a footer heading
remains with its preceding candidate. The fragments remain physically
verifiable even if other new candidate metadata is removed. These distinctions
are conservative review candidates and do not authorize printing.
The existing first phase-project selection contract remains; this does not
claim full coverage of mixed multi-project documents. Existing confirmation,
editorial publication, and provider validation rules are unchanged.

No private PDF, private title, expected private-document count, or model output
is used as a fixture. The synthetic cases cover resources between phases,
bare work phases, cross-page continuations, nested questions and steps,
homework, numbered references, title-only worksheets, footer headings, source
tampering, same-page annex boundaries, legacy round trips, and review labels.

Methodology and global project duration now use separate bounded source spans.
Wrapped values, suggested wording, and cross-page continuations keep one
literal citation per physical fragment. The display does not discard a time
unit merely because it wraps, truncate methodology at a character count, or
combine citations into a fabricated cross-page quote. Uncertain continuations
remain proposed/ambiguous/pending and never create class durations.
