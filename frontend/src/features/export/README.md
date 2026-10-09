# Activity export integration

`ActivityExport.vue` downloads self-contained printable HTML. `activityExport.ts` renders exact teacher text and literal source excerpts without network requests, scripts, remote assets or dependencies. It escapes text and includes restrictive document CSP. Print is the browser's native menu, including Save as PDF where available.

## S11 / S13 / S20 contract

Pass the most recent S13 editor `change` state as `state`. Its structural subset contains `draft`, `saved.revision` and `approved`. Pass the associated S06 interpretation `{document_id, source_segments}` as `source`. Pages must be positive, one-based physical page numbers and reference IDs must be unique. This is a rendering projection, not a new API schema. S11 retains ownership of shared types and authenticated transport.

The default `draft` mode exports the live `state.draft`, even during save failure or while a request is pending. It labels the saved revision as a base and never calls that current text approved. `approved` mode requires an explicit teacher click and exports `state.approved.content` and its revision, not `state.draft`. The old approved snapshot remains available while the teacher edits a newer draft. A missing snapshot, essential text or referenced source blocks an approved copy with a Spanish error. Missing content or references stay visible on draft copies for review. Empty materials remain pending confirmation, not an invented assertion that none are needed.

Only pass approval snapshots confirmed by the authenticated backend, as required by S13. Do not synthesize `approved` from provider output or client checkbox state. This component cannot grant authorization, approve, publish, synchronize or infer offline. It never changes the editor or its approval state. The exported approval label describes the input snapshot, not a cryptographic certificate.

`download-requested(mode)` reports that the browser download was requested, not verified completion, persistence or approval. Browser errors appear in a live status region. Do not disable this component solely because `navigator.onLine` is false. The exporter uses only already loaded data. Reopening the app itself offline still depends on app hosting; no service worker is supplied here.

Source segments must be supplied for the exact document associated with the selected snapshot. The renderer rejects missing referenced segments for approved output. It cannot independently verify backend document ownership or match the original PDF. It includes only referenced excerpts, never the original PDF or other document segments. Context does not imply that later edits are supported by those excerpts.

All video, image, link, annex and original-PDF resources stay outside this text export. The document asks teachers to obtain required resources separately before class or request an adaptation. It makes no claim of self-contained media availability. S10/S19 should verify that this warning and the distinct draft/approved actions remain visible after shell integration.

## Reproduction

Node 24 can run the focused tests without installation.

```sh
node --test frontend/tests/export.test.mjs
node frontend/tests/export-browser.mjs
```

The browser script uses installed Chrome and an isolated profile beneath `AULALISTA_SCRATCH_DIR`. Override its executable with `S14_CHROME` if necessary. It uses CDP offline mode, calls the real download implementation, verifies the saved file, opens it offline, checks literal teacher text and source content, records absence of HTTP requests, captures a screenshot and prints a PDF. It does not mount the Vue component. It closes its own browser after the check.

`fixtures/activity.json` is an authored synthetic activity. `fixtures/activity.html` is its real generated draft output, explicitly marked as a software example with no provider or pedagogical validation. Regenerate after renderer changes.

```sh
node --input-type=module - <<'JS'
import { readFileSync, writeFileSync } from 'node:fs';
import { createActivityFile } from './frontend/src/features/export/activityExport.ts';
const { state, source } = JSON.parse(readFileSync('frontend/src/features/export/fixtures/activity.json', 'utf8'));
writeFileSync('frontend/src/features/export/fixtures/activity.html', createActivityFile(state, source, 'draft', true).content);
JS
```

The integrated Vue shell mounts this module next to the editor. The compiled browser journey covers authenticated reopen and persistence; this focused export harness checks only the download implementation.
