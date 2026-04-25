# LLM Context Rules

These rules define the default context contract for future VCBet LLM/Codex work.

## Default Rule

Never send the whole repository to an LLM by default. Start from one domain context pack and add only the files needed to answer or implement the specific task.

## Required Base Context

Every LLM task should include:

- `docs/context.md`
- `docs/audit_file_manifest.md`
- `docs/LLM_CONTEXT_RULES.md`
- one relevant `context_packs/*.md` domain context pack
- directly touched files only
- related tests only

If the task crosses domains, choose the primary domain pack first, then add the smallest necessary pieces from the secondary pack.

## Forbidden Default Context

Do not include these paths or artifact classes by default:

- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches, including `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
- logs
- generated runs, replays, and results
- full ledgers

These exclusions apply even when the files are small unless an exception below applies.

## Exception Rules

Use exceptions narrowly and prefer samples over complete runtime artifacts.

- Ledger bug: include ledger code and only the smallest useful ledger excerpt, such as headers plus a few rows, or the exact blocked-candidate artifact that demonstrates the bug. Do not include the full operational ledger unless the user explicitly asks.
- Replay bug: include the replay code, one source run or replay manifest, one summary, and the minimum failing replay artifact. Do not include full replay directories.
- Settlement/result bug: include settlement code, result collector code if relevant, result CSV headers plus a few rows, and the exact override row if needed.
- Aliases/team registry bug: include team identity code, registry configuration CSVs, and a tiny excerpt from runtime review queues only if the queue itself is the failure surface.
- Service job/log bug: include service job code, one job JSON, and the corresponding first or failing log excerpt. Do not include whole job or log directories.

## Max Context Principle

Context should maximize relevance, not volume.

- Include contracts and boundaries first.
- Include implementation only for the target domain.
- Include directly touched files, not nearby files by habit.
- Include related tests, not the full test suite.
- Include samples, not full runtime artifacts.
- Prefer manifests, schemas, and narrow call sites over generated output.

## Briefing Docs Warning

`docs/audit_file_manifest.md` and `docs/context.md` are briefing documents. They are not source evidence to refactor from directly. Use them to choose source files, understand repository shape, and avoid context bloat. Refactor decisions must be grounded in the actual source files and tests loaded for the target domain.
