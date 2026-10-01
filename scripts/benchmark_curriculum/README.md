# Portable prospective curriculum benchmark

Issues [#143](https://github.com/eliancanul/AulaLista/issues/143) and
[#147](https://github.com/eliancanul/AulaLista/issues/147). Version
`1.2.0-portable` adds two closed comparison profiles to the portable harness.
**This release was not the executable used for the original pilot.** The M and W
scoring contract remains version 1.0.0; the product extractor is unchanged.
The original private freeze, corpus and execution artifacts are not distributed.
Portability changes include explicit paths, optional C01, POSIX resource reporting,
stricter path/config validation, and retention of malformed-output failures in
the existing document denominators. They do not change the M/W scoring formulas.
Published pilot evidence lives separately under `docs/evidence/`.

This tooling measures mechanical behavior and optional agreement with a weak AI
reference. It does not establish semantic accuracy, human annotation, pedagogical
validation or permission to publish a CurriculumPackage. It never generates
activities, calls a cloud model, sets up Django or modifies a database.

## Requirements and paths

Use Python 3.12+ on POSIX with `resource`, process groups and Git available.
The optional product preflight requires the environment from the repository's
hash-pinned `requirements.lock`; setup verifies every applicable package pin.
Windows resource enforcement is not implemented. No automatic package, model,
PDF or Git-history downloads occur.

The public unittest suite uses only the standard library plus `pypdf` and
`packaging`. It creates synthetic inputs in temporary directories, requires no
comparison history, and does not import the repository's `tests/conftest.py`.
It is also discovered by the normal repository pytest command.

All snapshots, fixture PDFs, corpus manifests, source text, references, hashes,
logs and run outputs go in an explicit private workdir outside this checkout and
the comparison checkout. A workdir containing either checkout is also rejected.
Keep that directory private; raw outputs can contain source text and personal
information. Do not commit it. No additional ignore rule makes private data safe.
The code makes no OS security or permission changes.

## Commands

From this checkout, use a selected virtualenv interpreter consistently. The
optional `--python` argument must identify that same interpreter; omitting it
uses `sys.executable`. The file entrypoint also works from another current directory:
`python /path/to/checkout/scripts/benchmark_curriculum/entrypoint.py --help`.
No cloud path or particular virtualenv is embedded in the code.

```sh
python -m unittest discover -s scripts/benchmark_curriculum/tests -v

# Choose a fresh directory outside every checkout; never reuse the pilot directory.
BENCH_WORKDIR=/private/path/to/new-benchmark
python -m scripts.benchmark_curriculum setup --repo . --workdir "$BENCH_WORKDIR"
python -m scripts.benchmark_curriculum preflight --repo . --workdir "$BENCH_WORKDIR" --out preflight/synthetic
```

The default profile, `b0-b2-b3`, exports immutable Git archives for B0
`2541faf04bda4dad1215a4673e3802567ca7c5c9`, B2
`1aae48b93c2d83aec80c1248a38c24d5960a3d2a` and B3
`a4dfe5cf9975d9e9b74a256aff718aec35f11f39`. It does not change refs or the
comparison checkout. All three commits must already exist locally; a shallow CI
checkout does not need them for unit tests. Complete per-file manifests, tree
and archive hashes, the identical dependency lock, interpreter hash, installed
package bytes and platform are recorded privately. Installed bytes do not prove
which original wheels were downloaded.

Preflight accepts no user PDF path. It generates two-page repeated projects,
three blank pages and a thirty-page stress fixture, then runs the complete
B0/B2/B3 order twice. `--include-c01` explicitly adds only the exact previously
versioned C01 calibration PDF, checked against its known SHA. Fixture generation,
snapshot setup, release generation, references and run directories refuse to
overwrite earlier artifacts. Use a fresh workdir for a second preflight.

The explicitly selected `b0-b3-b4` profile compares the same B0 and B3 with B4
`bf1ae21eae80ed38ef02179ea5724b7b0aa7b1c7`. Its paired reports are B0->B4 and
B3->B4. No arbitrary commit, version list or pair is accepted. Each profile uses
its own fresh workdir; include the same `--profile` on every command. Omitting
it always selects `b0-b2-b3`, even when a workdir or freeze contains B4.

```sh
BENCH_WORKDIR=/private/path/to/new-b4-benchmark
python -m scripts.benchmark_curriculum setup --repo . --workdir "$BENCH_WORKDIR" --profile b0-b3-b4
python -m scripts.benchmark_curriculum preflight --repo . --workdir "$BENCH_WORKDIR" --profile b0-b3-b4 --out preflight/synthetic
```

Preflight and freeze-template choose the selected profile's proposed config:
`config.proposed.json` for the default, `config.b0-b3-b4.proposed.json` for B4.
Both proposals have identical resource limits and scoring settings. A coordinator
may supply `--config` with smaller document/page caps for a closed cohort. An
explicit config must match the chosen profile, fixed commits, pairs and order;
config and freeze files cannot silently select or override the CLI profile.

To prepare, but never automatically close, a new freeze:

```sh
python -m scripts.benchmark_curriculum freeze-template --repo . --workdir "$BENCH_WORKDIR" --profile b0-b3-b4 --protocol /path/to/protocol.md --out release
# A coordinator independently completes, reviews and hashes every required artifact.
python -m scripts.benchmark_curriculum run --repo . --workdir "$BENCH_WORKDIR" --profile b0-b3-b4 --freeze release/freeze_record.closed.json --out runs/unique-name
```

These commands continue the B4 example. For the default comparison, omit
`--profile b0-b3-b4` and use the separately prepared B0/B2/B3 workdir.

The generated template stays `ready_to_run: false`. The corpus run requires the
portable release identity, exact code coverage, artifacts, source commits,
environment, input bytes, explicit eligibility, and order. Existing private
pilot freezes and version 1.1.0 portable freezes cannot identify this different
executable. Reproduce old artifacts using their exact original release; never
relabel them. This release requires newly generated snapshot manifests and a
newly closed freeze even for the default comparison. Snapshot indexes must
contain exactly the selected versions. Every snapshot manifest, index entry,
environment manifest, freeze, release record, run configuration and run receipt
identifies the selected profile. Mixed profile artifacts or extra snapshot
directories are rejected. Worker subprocesses receive the profile explicitly
and record it in their status; the independent source reader receives the same
selection without changing its reading or scoring behavior.
Every present worker status must match the complete release/profile/commits/pairs
identity before its output is scored. A mismatch stops the campaign with a terminal
`instrumentation_failure` receipt and preserves the worker's raw output and status.
An absent status after a timeout or crash remains an ordinary failed product run
in the existing metric denominators.

The public test suite preserves the original 44 synthetic tests and adds coverage
for relocated execution, clean subprocess environments, quarantined paths and
symlinks, altered freezes/snapshots, no overwrite, malformed output and retained
failure denominators. Profile tests also cover fixed commits and pairs, CLI
selection, unchanged limits, old/mismatched identities, mixed snapshots and
configuration, and serial repetitions. Tests use only synthetic sources and
do not rerun the private pilot.

## Execution contract

The coordinator closes sources, permissions, PII, families, scope and freeze.
The harness does not authorize its own corpus run. the generated `freeze_record.template.json`
shows required fields. Paths in its artifacts are relative to the freeze record.
Each artifact's SHA must match. The corpus can be a list, or an object with a
`documents` list. Every row needs:

- document_id (ASCII letters, digits, dash, underscore), family_id
- split: D, H, R, T, X, or feasibility_prospective; separate strata never pooled
- path (absolute), or relative_private_path (relative to corpus manifest)
- file_sha256, bytes, physical page_count
- selection_status: included
- rights.status: approved and a nonempty private_processing_basis
- pii.status: no_detected

Private processing approval is not an open license or redistribution approval.
Any path containing quarantine/cuarentena, outside the explicit private workdir,
changed SHA/size, duplicate ID, or uncleared row stops the run. Rights/PII checks
are the coordinator's documented determinations, not inferred from accessibility.
A smaller feasibility cohort is accepted as such, without claiming full D/H.

Worker calls exactly prepare(None selection, None job), compile claims, verify.
Prepare already calls its own verifier; the explicit final call is preserved as
another output. No verifier result is a scoring oracle. A fresh process is used
for each version/document/repetition, without Django setup or DB. No API keys,
proxy variables or credentials are forwarded. In-process Python audit guards
reject socket creation/DNS/network operations and child processes, and reject
open-for-write outside the run directory. These are scoped instrumentation,
not OS security settings and not a hostile-code sandbox. Read access is not
confined; native-extension syscalls and unaudited filesystem operations are not
contained. Only run reviewed, trusted snapshots with this instrumentation. Any
attempted guarded operation aborts the entire run and leaves logs. Timeout kills
the process group.

Preflight-proposed budgets (same for all versions): 120 wall seconds per complete
product pipeline; 1 GiB address-space limit; one process at a time. Independent
source reading gets 60 seconds/1 GiB. No infrastructure retry is automatic.
The maximum input is 20 MiB/30 physical pages; max corpus 12 PDFs/180 pages.
The product's measured max RSS and resource rusage are logged separately because
rusage high-water can inherit the parent's pre-exec peak. Linux `/proc/self/status`
VmHWM is used when available; other POSIX systems use rusage with platform-specific units.

Document IDs sort lexicographically; version order rotates the selected profile
(B0/B2/B3 by default, or B0/B3/B4) by document index. The complete identical order
is repeated once, for two serial repetitions. Raw partial/final outputs,
logs, start/end, resources, raw/canonical SHA and outcomes are retained.
Canonicalization removes only dossier.created_at, dossier.updated_at, and
history[*].timestamp when action is exactly prepare. It does not normalize text,
reorder arrays, change IDs, or erase nested fields. Both completion and equality
are needed to establish deterministic reproduction; two identical failures do
not establish it. Malformed non-list `history` values are preserved verbatim.

An instrumentation exception closes the receipt as `instrumentation_failure`
(or preserves the dedicated source-reader/guard failure), with planned document
and comparison counts, executed/scored counts, and `evaluation_completed: false`.
Raw and partial artifacts remain available. No scores are fabricated for skipped
comparisons, and a partial campaign cannot be presented as the complete cohort.
A completed receipt is written only after final snapshot verification.

## Metric contract and limits

`metrics.py` imports no product scanner, interpreter or verifier. It reads the
original bytes separately with pypdf 6.1.3 using PdfReader(strict=False) and
page.extract_text() defaults. Same reader library is intentional; extraction
representation and semantic fidelity are not independent concepts. Full text
and SHA for each physical page are retained. No OCR/normalization/repair.
Independent reader failure stops before product execution rather than selecting
only readable PDFs. Per-page text errors remain in the physical denominator.

M1: completed three-stage pipelines / included PDFs. M2: independent text-bearing
pages / all physical pages. It is common source-representation coverage and
cannot prove correct comprehension or per-version reading differences.

M3_fields and M4 use nonempty candidate InterpretedFields in
`general_fields` and `sessions[*].fields`. Empty/malformed emitted slots remain
in M8 inventory and abstention counts; they are not added to those candidate denominators.
M3_citations counts every actual evidence and annex_evidence emission from the dossier,
excluding repeated audit/history snapshots. Claims are a separate output view;
their citations and defects are reported separately to avoid duplication.
Scalar session title/project_title/day, context title and activity title/description
are inventoried separately, not silently converted into InterpretedFields or
supplied with evidence they did not emit. M3_fields/M4 must be labeled specifically as
InterpretedField evidence validity. M3_citations is all-dossier emitted-citation validity;
neither is coverage of every text string or the full source document.
M4 requires at least one citation and every emitted citation valid. A valid quote
for a list does not establish every list member's support.

M5 validates native anchors, and units with a valid own header_anchor / every
emitted unit; a nearby project anchor cannot stand in for a session anchor.
Physical indices/schema version/occurrence/offsets must be actual integers,
never bool/string. SHA lowercase hex, exact page literal and exact Python slice
are required. Occurrence's true identity, boundaries and parent context remain
unevaluated even with perfect mechanical integrity.

M6 uses strong InterpretedFields (raw supported OR any mapped checked audit
item). States select the asserted population only; validity comes from independent
literal checks. Absence of evidence and invalid evidence are both unsupported.
Strong raw and audit counts are separate, alongside candidates and emitted-slot
abstention. Non-field audit states are descriptive only; this is not a whole-system
semantic false-assertion rate.

M7 flags any independently invalid dossier/claim citation, anchor, declared source
SHA/version/page metadata, over all included PDFs. Documents with no output and
failures are explicit companion counts. No-output never becomes zero-risk proof.
M8 includes fields, units, claims, strong counts, audit states, candidates, malformed
records, source/read errors, and exact emitted unassigned-span markers. It does
not estimate un-emitted opportunities or find omissions with the product scanner.

Every rate preserves numerator, denominator and unit. Zero denominator is null/N/A.
Micro and macro document/family summaries retain evaluable denominators. Paired
reports (B0->B3 and B2->B3 by default; B0->B4 and B3->B4 for `b0-b3-b4`)
preserve both denominators; conditional changes are not
interpreted as fixed-population risk reductions. Repetitions stay separate and
never double the corpus sample size. R/X/new strata never pool. No composite score.

## Optional weak AI reference

`python -m scripts.benchmark_curriculum combine --repo . --workdir "$BENCH_WORKDIR" --a A.json --b B.json --out combined.json` takes lists
of blinded document annotation records conforming to the coordinator's schema.
It consumes no product output. Coordinator must close and hash the combined
reference before the first corpus run. Two AI readers are still AI, not humans.
Differences in statuses, normalized value, or singleton overview page become
unknown. Present formative fields require source evidence within first 3 pages.

Phase M_only needs no AI or human reference. M_plus_weak_reference_ai additionally
requires frozen combined reference, annotation spec, and explicit false for
weak_reference_ai_outputs_seen_before_freeze. Only four document overview slots
are compared; internal page panels, segmentation and physical relations are not.
Text rule is NFC, whitespace split/join, then casefold. Formative fields use exact
normalized sets. No punctuation/accent/synonym repair or semantic equivalence.
Counts C/W/A/N_pos/N_neg/N_unknown/not_applicable remain visible. Failed end-to-end
runs count abstention on positive slots. W is labeled agreement with weak AI
reference and cannot be advertised as semantic accuracy.

## Deliberate unimplemented parts

No H1-H8, human adjudication, occurrence matching, true cross-occurrence rate,
semantic title/purpose fidelity, teacher impact, or product X mutation-acceptance
benchmark. `mutation_pool.json` is explicitly synthetic scorer-validation controls;
it is not a result on product verifier adversarial behavior. These require a
separately closed scope and evaluator. Literal quotes can still belong to the
wrong occurrence. Unknown/absent reference never becomes fabricated ground truth.
