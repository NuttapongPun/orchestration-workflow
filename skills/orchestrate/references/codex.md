# Codex binding

- **Dispatch:** spawn subagents by worker name: `investigate`, `easy-worker`, `hard-worker`, `review`, `review-hard`. Worker definitions live in `~/.codex/agents/*.toml` and carry their own model and reasoning effort.
- **Model rule:** pass the model explicitly on every spawn even though the worker file sets it. Easy tier is `gpt-6-luna`, hard tier is `gpt-6.1-sol` at high reasoning effort. If either override is not callable in the live runtime, report blocked on model availability. Never substitute another model.
- **No nesting:** `[agents] max_depth = 1` in `~/.codex/config.toml` prevents workers from spawning workers.
- **Concurrency:** spawn every ready task in the wave before waiting on any of them. Respect `agents.max_concurrent_threads_per_session`. The wave's results come back together.
- **Sandbox:** workers inherit the session's sandbox and approval settings; a worker file cannot change them. Read-only workers are read-only by their instructions only, so tell `investigate`, `review`, and `review-hard` in the brief not to modify files. The commander should run the session in `workspace-write` (the default): reviewers re-run or add checks when the worker's output falls short, which a `read-only` session blocks when they write caches or build output.
- **Web search:** follows the session's `web_search` setting, for you and every worker alike. If a task needs live pages and search is not live, say so in the report.
- **Available agents:** read the runtime's subagent tool description before dispatching. It is the source of truth for names and callable models.
