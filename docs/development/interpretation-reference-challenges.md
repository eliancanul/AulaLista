# Reference challenges: contract checks are not semantic truth

The synthetic primary references remain frozen. These notes do not relabel them,
remove hard cases, change their denominators, or turn model disagreement into a
model error without examining the annotation policy.

## Incomplete date header

`activity_session_v1.json` / `date_label_without_value` contains a session number,
an empty Fecha label, a labelled moment and an activity. Its primary synthetic
reference expects no admitted session. That is a deliberately conservative
**admission-policy test**, not proof that a teacher would deny that it is a session.
An interpretation that preserves the session and abstains only on its date is
plausible. Score such a response as disagreement with the exact contract while
also reporting the unresolved annotation-policy question.

## Labelled activity with listed substeps

`activity_session_bullets_v1.json` / `labelled_activity_steps` freezes only the
labelled activity header as its gold activity span, while the page also contains
two subordinate listed steps. The scope says those steps belong inside the
activity. Consequently, the frozen span is sufficient to test identity/parentage
but **not** to establish that the whole activity has been recovered. A model that
returns header plus substeps may be penalized by strict containment alignment even
though its grouping is defensible. The primary score stays unchanged; whole-task
claims about this item must carry that limitation.

## Required reporting separation

1. Exact-contract results: unchanged frozen references and evaluator version,
   including misses, extras and strict span purity.
2. Reference/semantic disputes: enumerate disputed items, proposed alternative
   readings and who adjudicated them. Do not silently replace labels after seeing
   model predictions or omit these cases from a reported primary denominator.
3. Generalization: separate later held-out and independently human-reviewed
   material from developer-authored examples. Neither synthetics nor the related
   development sources establish pedagogical correctness or curriculum-wide 90%.

A comparison between rules, LLM proposals and a hybrid must use the same scope and
report both exact-contract results and these disputes. A lower strict score alone
does not establish that one approach interprets the curriculum less well. This
repository's optional provider remains a disabled, synthetic-only boundary; any
separate real-model experiment must identify its own model, prompt, transport,
response parsing, tool-access limits and actual usage.
