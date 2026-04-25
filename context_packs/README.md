# Context Packs

Context packs are manifests for future VCBet LLM/Codex tasks. Each pack says what to include when working on one domain, what to leave out, which invariants matter, and which narrow validation commands are most useful.

Packs are documentation, not code. They do not change runtime behavior and should not be treated as source evidence. Use them with `docs/LLM_CONTEXT_RULES.md`, `docs/context.md`, and `docs/audit_file_manifest.md` to avoid repo-wide context bloat.

Default workflow:

1. Choose one primary context pack.
2. Include the required base context from `docs/LLM_CONTEXT_RULES.md`.
3. Add files from `Include by Default`.
4. Add optional files only when the task specifically touches that call path.
5. Add directly touched files and related tests.
6. Keep runtime artifacts out unless an exception rule explicitly applies.
