# Activity → annex: exact numbered-reference interpretation

This increment retains the existing `requiere_anexo` predicate and candidate
state. It neither confirms an annex sheet nor interprets pedagogical necessity,
suitability, negation or conditions automatically.

## Reproduced problem

In an artificial session with two activities, “Leer el anexo 1 y responder el
punto 2” was linked to annexes 1 **and 2** when another activity mentioned annex 2.
The old matcher scanned arbitrary intervening text before searching for a number.
A raw substring fallback also allowed anexo 1 to match anexo 12 or preanexo 1.

The new shared literal mention parser only accepts a numbered annex marker and
its immediately adjacent explicit number list. It does not turn a subsequent
point, page or other prose number into an annex target. Padding is canonicalized;
original literal text and line breaks remain in evidence. No new relationship
ontology is introduced.

Each activity–annex edge now retains its own original activity context containing
the actual annex mention. The claims compiler uses that relationship-specific
evidence instead of a generic first-80-character activity excerpt that might end
before the annex appears. A legacy/manual link without such evidence stays a
candidate with no invented supporting citation. A foreign-source citation is
not reused.

## Fixed synthetic result

`tests/fixtures/interpretation/activity_annex_v1.json` was frozen before changing
the matcher, SHA256:
`c49e767843a695a3fa3e760f259ab17ffc2dc29ae01367dfa4e2dc3214bac48c`.

Nine artificial documents contain twelve expected numbered-reference edges,
including adjacent point/page numbers, 1 versus 12, explicit padded/multiline
lists, different sessions, a late mention beyond 80 characters, a resource-only
mention and a word-fragment negative.

| Measure | Baseline 4a697a4 | Candidate |
|---|---:|---:|
| Expected edges | 12 | 12 |
| Correct edges | 12 | 12 |
| Extra edges | 4 | 0 |
| Emitted-edge precision | 12/16 (75%) | 12/12 (100%) |
| Expected-edge recall | 12/12 (100%) | 12/12 (100%) |
| Correct edges with complete mention in citation | 11/12 | 12/12 |

This is a synthetic development contract, not teacher gold, held-out performance
or an improvement claim on real PDFs. Perfect recall alone concealed false links;
precision and evidence support are necessary companion measures. Missing resources
remain missing and no `confirmed_page` or teacher decision is manufactured.

## Deliberate boundaries

- Conditional or negated mentions need contextual interpretation. A textual
  numbered mention alone does not prove an unconditional requirement.
- Range interpretation, implied pronouns and unnumbered/titled annexes are not
  claimed as solved by this increment.
- Candidate sheet retrieval and suitability are separate from activity reference
  linkage. Finding a page does not establish that it is the right educational
  resource.
- A later LLM/hybrid evaluation must preserve these distinctions and score against
  independently reviewed reference opportunities with uncertainty visible.

```sh
python scripts/evaluate_activity_annex.py
python scripts/evaluate_activity_annex.py --product-root /path/to/baseline
python -m pytest -q tests/test_activity_annex_evaluation.py
```
