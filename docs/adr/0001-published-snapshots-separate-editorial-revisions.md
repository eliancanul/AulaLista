# Published snapshots are separate from editorial revisions

`ClassroomSession` reads a `PublishedPackageSnapshot`, not the live editorial object. Every correction creates a new reviewed and published snapshot, because an active session must remain reproducible even when future content changes.

## Considered options

- Read the current editorial revision from active sessions: rejected because corrections would silently alter work already in progress.
- Copy the whole spike's model unchanged: rejected because production must add explicit permissions, transactions, and tests around the invariant.
