# Activity editor integration

`ActivityEditor.vue` owns one teacher draft. `activityEditor.ts` is the framework-independent state implementation. `persistence.ts` maps requests to the published S07 contract. No dependencies are installed by this slice.

## Data and transport

`SavedActivity` is an editor projection, not a competing API response schema. It contains `id`, `revision`, `status: draft | approved`, `content` and `approved`. `content` holds the exact title, objective, materials, steps, assessment and source_ids. `approved` is null or the server-confirmed `{revision, content}` snapshot. Pass the snapshot on reopen so editing does not erase the previous approval. Approval is distinct from publication.

S11 supplies `activity`, `persistence` and `canApprove` (default false). Use `createEditorPersistence({patchDraft, approveDraft}, decodeResponse)` to connect S11's existing authenticated API client. The adapter sends S07's `{expected_revision, changes}` and `{expected_revision, confirm: true}`. It never sends source IDs, owner, status or approval fields in an edit request. S11/S20 own response decoding from the final S09 projection. The decoder must preserve exact text and server-confirmed approval, never mark drafts approved from generated content. Approval may keep the content revision; a successful save must advance it.

The API client must retain Django session identity, CSRF and same-origin ownership enforcement. Reject unsuccessful HTTP responses. Forward numeric `status` on errors (409/412 trigger conflict handling). Optional `current` must already be a decoded `SavedActivity`; otherwise load the latest interpretation after the `request-refresh` event and pass its decoded draft back via `activity` or exposed `receive`. Do not blindly retry stale writes. This module deliberately owns no fetch client, credentials, API endpoint definitions or backend authorization.

## Host integration

- `change` emits a detached state snapshot, including `dirty`, `needsLeaveWarning`, `approved` and `isApproved`.
- `saved` emits the server-confirmed saved projection. Typing may have continued during the request, so it does not imply the current draft is clean.
- `approved` emits the reviewed snapshot. Never export a concurrently edited draft as approved. S14 can use `state.approved` for the previous approved content and `state.isApproved` for the current draft.
- `request-refresh` emits the draft ID. The host knows the associated interpretation ID and fetches it using S07's GET interpretation route.
- A mounted editor is bound to one draft ID. Before changing routes or component keys, call exposed `hasUnsavedChanges()` and require the teacher's explicit leave decision. The component covers browser `beforeunload`; only the shell can guard SPA unmounts.
- S17 displays proposals separately. Only an explicit teacher apply action may call the state editor's `edit` method. Receiving an interpretation or chat response never applies an edit automatically. Never replace editor state with re-extraction output.

Edits can continue during save or approval. Pending requests use an independent snapshot; responses never assign over the live draft. New server versions appear for comparison. The teacher chooses to keep local text (rebased on the chosen server revision) or replace it with the displayed server version. A conflict blocks further writes until that choice. The approved snapshot remains separate.

The Spanish UI offers a recovery JSON download with exact current text and an unconditional `status: draft`. This is a disconnected copy, not the S14 classroom export. Unsaved changes otherwise remain in memory; there is no silent localStorage persistence or automatic recovery across crashes. Browser and route leave guards must remain active.

## Verification

Run `node --test frontend/tests/editor*.test.mjs` with Node 24. No frontend installation is required. Tests use controlled transport promises. The legacy regression executes the actual Django inline script with a minimal simulated DOM and demonstrates a still-open defect outside S13 ownership. It is not a browser test and its pass means the defect was reproduced.
