# Handoff — supervisor loop bootstrap

- **Scope:** unattended documentation/architecture loop for `updated-tech`; no implementation fixes.
- **Repository:** `/Users/dojo/Documents/ChatGPT/AulaLista-updated-tech`
- **Supervisor:** `/Users/dojo/.local/bin/aulalista-updated-tech-supervisor.sh`
- **Prompt template:** `/Users/dojo/.config/opencode/aulalista-updated-tech-loop-prompt.md`
- **Runtime state/logs:** `/Users/dojo/.local/state/aulalista-updated-tech-supervisor/`
- **Process at bootstrap:** `5595` (verify with `ps`/`supervisor.pid`)
- **Parallel coding lane:** `/Users/dojo/.local/bin/aulalista-updated-tech-coding-lane.sh`, launchd job `com.dojo.aulalista-updated-tech-coding-lane`, state/logs `/Users/dojo/.local/state/aulalista-updated-tech-coding-lane/`. It remains idle until a published `IMPLEMENTATION-GATE.md` says `STATUS: READY_FOR_IMPLEMENTATION`, then uses an isolated worktree and produces a separate PR.
- **Loop:** fresh opencode session per iteration, sequential, ten rotating audit phases, checkpoints every 10 and 100 iterations; continues indefinitely.
- **Model:** `opencode/muse-spark-1.3-contributor-free`. The paid `opencode/muse-spark-1.3` was attempted first but returned `Insufficient balance`; the free 1.3 variant is the operational fallback.
- **Safety boundary:** agents may write only Markdown under `docs/handoffs/` and `docs/adr/`; no Python/tests/templates/settings/migrations/config edits. At 10-iteration checkpoints they may stage only those Markdown paths, push the dedicated `supervisor/aulalista-docs` branch, and create/update one non-merged PR targeting `main`; never use `git add -A`, merge, reset, or create standalone issues.
- **Required final checkpoint:** `docs/handoffs/supervisor-final-{cycle}.md`, including observed changes, ten strongest prompts/outcomes, graph/loop/evidence-matrix methodology, and PR links.

The working tree already contained pre-existing implementation changes and untracked artifacts before this bootstrap; the supervisor must preserve and report them, not revert them.
