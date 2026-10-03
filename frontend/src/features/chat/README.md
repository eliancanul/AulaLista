# S17 chat integration

`TeacherChat.vue` takes `interpretationId`, `sources` and an authenticated `transport` supplied by S11. Mount with a key that changes with the interpretation and its source version. The module owns in-memory question/history state only. Guard route changes if the teacher has text to preserve. No local storage or credentials are introduced.

Transport receives exactly S07's `{ interpretation_id, message }`. It resolves the decoded JSON body or rejects on HTTP/network failure. Forward numeric `status` and optional `retryable` on errors. Session cookies, CSRF and ownership remain with S11/S08. The response must contain `interpretation_id`, `message`, `source_ids`, `proposals: []`, `mode: source_lookup`, `applies_changes: false`. All evidence IDs must resolve in the supplied source segments. Raw server error bodies are not shown. Question length is at most 4000 characters. Retry resends the failed question, preserving newer text in the composer.

S07 offers complete source-lookup replies. Loading is real request state. This module does not simulate streaming or claim model generation. Nonempty provider proposals are rejected until S06/S07 publish a supported schema and a host adapter is reviewed. An answer with no source IDs shows the missing-source warning. Vue interpolation renders source and answer text without HTML interpretation.

## Optional edit preview

`EditPreview.vue` is a separate host-facing review surface, not a new API contract. Mount with `:key="proposal.id"`. The host supplies a validated `EditProposal` and a reactive `current` snapshot of the editor's live content, not just the last saved content. The proposal's `base` must be captured when proposing the edit. It must never be relabeled with a later revision or later content. Use a new proposal ID for changed proposals.

The preview displays before/after and evidence. Only title, objective, materials, steps and assessment may change. Acceptance is blocked if the activity ID, saved revision or any editable live content differs from the base. Rejection and request failures never touch the activity. Accept emits one detached `{ proposal_id, base, changes }` intent. It never calls persistence, approves, publishes or mutates props.

S11/S13/S20 must handle `accept` synchronously, recheck the same base against the current editor state and call S13's `edit` method for each changed field. Do not await a request between checking and editing. Preserve S13 dirty state, approval invalidation and explicit Save/Approve controls. S13's mounted component does not yet expose that edit method to the shell; the state controller does. Coordinated shell/editor wiring is required before mounting a functional preview. Do not present acceptance as a completed save. `reject` emits the proposal ID so the host can discard it.

No generated proposal source exists in the current API. The preview can be exercised with clearly labeled fixtures. Do not synthesize provider changes from source lookup text. No code in this slice edits editor-owned files.

## Checks

Run `node --test frontend/tests/chat-S17.test.mjs` on Node 24. Tests execute the actual controllers using fixture transport and deterministic delayed responses. They do not prove authenticated API, Vue rendering, browser accessibility or a provider result. S11 owns installation/compiler setup; S19 owns browser checks after S20 integrates the module.
