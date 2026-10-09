# AulaLista frontend

S11 owns this Vue 3 shell, API transport, router, shared styles, package manifest and lockfile. Feature owners keep their components under `src/features/`. Django remains available through `/tutor/` and `/cms/`.

## Build and verification

Use Node 24 or Node >=22.12. Run from `frontend/`.

```sh
npm ci
npm run build
npm test
```

`build` checks TypeScript and Vue SFCs before producing local assets and `dist/.vite/manifest.json`. No CDN or font download is used by the application. `test` selects S11 tests explicitly. The five specialist integration tests skip when their components have not been integrated. A skip is not evidence that a feature works.

S19 owns real-browser layout, keyboard, zoom and disconnected download checks. DOM tests and authored HTTP responses do not establish real authentication, database persistence, provider results or pedagogical quality.

## Runtime integration

The hash router leaves existing Django paths intact. Serve the built index and assets from one local origin. All requests use `/api/v1`, `credentials: same-origin`, `cache: no-store` and `redirect: error`. Mutations require Django CSRF from a rendered hidden input, `meta[name=csrf-token]`, or the `csrftoken` cookie. No token is persisted in frontend storage. Missing tokens block the request. Errors retain numeric HTTP status for conflict handling and never display raw response bodies. Requests are not automatically retried.

The development proxy preserves the browser origin. `/api/v1` targets loopback port 8001; `/cms/`, `/tutor/` and `/static/` target loopback port 8000. For the integrated local application, follow [the startup guide](../docs/integration-night.md) and use its single loopback origin. The Vite scripts alone do not configure the Django/API server. `vite preview` does not provide the development proxy. Session, CSRF trusted-origin and Host checks remain backend responsibilities and are not relaxed here.

The server may render `<meta name="aulalista-can-approve" content="true">` only for an authorized reviewer. The default is false. This enables a UI control; it is never authorization. S07/S08 must independently enforce authority, ownership, CSRF and revision checks for every write. A static fixture must not be used as a capability source in a real runtime.

Approval confirms only the saved draft revision. It never publishes, activates a session or advances curriculum. A missing school level stays unknown. A source lookup response never applies changes. The current API exposes no supported generated-proposal schema, so `EditPreview` is not mounted.

## Shared component contract

`features.ts` imports only these entry files. Missing modules display an explicit availability message. Async imports display loading and error states. Feature fixtures are excluded from the production module registry.

| Owner and entry | Props provided by shell | Events and exposed methods consumed |
| --- | --- | --- |
| S15 `landing/LandingPage.vue` | `entryHref="#/preparar"`, `exportsAvailable=false` | None. Availability remains false pending the integrated export acceptance check. |
| S12 `review/UploadReview.vue` | `initialInterpretation` from S07 GET | `continue({interpretation, answers})`. Answers remain separate in-memory notes, visible beside the editor. The shell does not silently map them into fields or persist unsupported metadata. |
| S13 `editor/ActivityEditor.vue` | `activity`, `persistence`, `canApprove` | `change`, `request-refresh`, exposed `hasUnsavedChanges()`. Save and approve promises return the S13 projection. The editor owns live text and conflicts. |
| S14 `export/ActivityExport.vue` | `state={saved,draft,approved}`, `source={document_id,source_segments}` | The editor route supplies its live state, enabling download without leaving unsaved text. The standalone download route supplies only the current persisted response. |
| S17 `chat/TeacherChat.vue` | `interpretationId`, `sources`, `transport` | Transport sends S07's exact chat request. Input marks this view as needing leave confirmation, preserving a pending question or conversation until explicit exit. |

`contracts/interpretation.ts` follows S06/S07 response fields. `SavedActivity` is a structural adapter to S13, not a competing backend schema. Current approved content is derived only from persisted `approval_status=approved`. The editor loads immutable revision history on reopen and can display the last confirmed approved snapshot while the current draft remains pending.

Route guards cover navigation, including editor unmount and document changes. The browser leave guard covers full-page links and reload. Leaving requires an explicit decision when a view reports changes, pending requests or conflict. Browser unload protection cannot recover a crashed process. No silent localStorage copy is made. Review notes are not a durable draft and their lifetime is stated in the UI.

Plain local fragment links in review components and the skip link are handled without replacing the hash-router path. The target is scrolled into view and focused. Route changes move focus to main content. The shell owns canonical tokens from `DESIGN.md`, a 4px focus ring, touch targets, wrap-based navigation and reduced-motion behavior.

Shared components are `PrimaryAction` (`type`, `busy`, `disabled`, default slot), `AppStatus` (`title`, `detail`, `kind`, default slot) and `EditorialBoundary`. Components should accept immutable props and emit intents; they must not import the shell or mutate sibling state.

## Current limits and verification

- Review metadata and teacher answers have no persistence contract. Notes remain visibly temporary until the teacher explicitly incorporates them into the saved activity.
- The editor reloads revision history and the last approved snapshot from the authenticated API. A subsequent edit remains pending; historical approval never approves current text.
- S17's component exposes no state or leave method. The shell conservatively marks the whole chat view dirty after input, including after sending. It may ask for confirmation even when the composer is empty.
- The compiled browser and API regression suites exercise real local Django sessions, CSRF, persistence, reopen and explicit approval with temporary databases and synthetic PDFs. Export has separate focused tests; neither fixture suite establishes pedagogical quality or provider performance.
- Standalone feature verifiers exercise their own fixtures. Use the integrated build and browser suite to assess the assembled application; a focused feature result does not establish the full workflow.
