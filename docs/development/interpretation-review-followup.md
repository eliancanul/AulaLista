# Reproduced review findings and evaluator revision

The external review was static and did not run code. Each actionable report was
reproduced with synthetic source text before changing implementation.

## Findings

- **Not reproduced:** alleged dated headers borrowing a moment across the next
  dated session. The existing weak session boundary already cuts there; the
  counterexample admits only the second, corroborated session. No code change
  was made to accommodate this false-positive review finding.
- **Reproduced and corrected:** an instruction wrapping onto `preguntas guía:`
  was truncated by a generic colon-heading rule. An unfinished instruction may
  retain that introduction and its nested steps; known resource/evaluation
  headings still end activity scope.
- **Reproduced and corrected:** wrapped `actividad 1 que ...` became a second
  activity. A strong activity label remains a boundary, while unfinished listed
  prose without that delimiter stays within its original task.
- **Reproduced and corrected:** an unfinished instruction lost an unbulleted
  continuation on an already admitted next page. It now preserves the full
  description and separate literal evidence per original page. This never
  admits a new page itself, crosses another session, or absorbs an explanatory
  paragraph after a completed sentence.
- **Reproduced and corrected:** `anexo 1 y 2 páginas después` treated a page count
  as a second annex. A coordinated final count followed by an explicit unit is
  not automatically an annex identifier. Ordinary explicit lists still work.
- **Reproduced and corrected:** later references sharing an activity span skipped
  session-ID validation. Every relation and mention is now validated; duplicate
  IDs, unknown parents and conflicting parents fail before scoring.

## Metrics revision, without relabelling references

Activity-session evaluator v4 preserves the strict primary containment contract,
all existing reference hashes and denominators. Baseline and candidate were rerun
under the same revision. The development results remain 139/139 and 204/207.

- Awaiting human review is not abstention. A withheld target or explicit
  `basis=abstained` is an abstention; a non-abstained shadow proposal awaiting
  editorial review remains a proposed assignment when evaluated.
- Existing text-only precision/coverage are explicitly independent of parent
  assignment. New `correctly_assigned_text_precision` measures source overlap
  jointly with the right parent. `clean_complete_activity_recall` already required
  both correct parent and complete uncontaminated text.
- Overextended identifying spans still fail the frozen primary alignment rule.
  Separately supplied coverage spans can expose contamination after identity
  alignment. This strict contract does not adjudicate genuine granularity disputes;
  see the reference-challenges document.

Activity-annex evaluator v2 applies the same explicit scoring-page policy:
context-only predictions are excluded visibly; uncertain scope is retained.
Its frozen synthetic primary remains 12/12 correct with no extras. The earlier
private real-reference adapter already applied context scoping, so its 25 explicit
and 7 contextual opportunities are not redefined by this revision.

## Mention versus requirement: next semantic challenge

`activity_annex_semantics_v1.json` freezes nine artificial instructions with eleven
resource mentions (SHA256
`0a565876b3595209cf7969e0ee37437f7efaeafbea9f10cd82851e3424c812d9`).

A mention can be certain while necessity is true, false or withheld. Examples
include negation, “no olvidar”, substitution, a conditional instruction, a past
reference, current reuse and unresolved teacher authorization. An expected null
requirement means abstain on necessity while preserving the evidenced mention;
it does not mean the resource is absent. No item claims a physical sheet exists.

This is a **new challenge contract, not a reported product pass**. The numbered
mention parser does not solve general negation, conditional need or discourse
reference. `requiere_anexo` candidates must not be described as proven necessities
merely because a number appears. The positive real-development reference alone
cannot evaluate those distinctions.
