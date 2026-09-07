# Codex binding

- **Dispatch:** spawn subagents by worker name: `investigate`, `easy-worker`, `hard-worker`, `review`, `review-hard`. Worker definitions live in `~/.codex/agents/*.toml` and carry their own model and reasoning effort.
- **Model rule:** pass the model explicitly on every spawn even though the worker file sets it. Easy tier is `gpt-5.6-luna`, hard tier is `gpt-5.6-terra`. If neither override is callable in the live runtime, report blocked on Terra/Luna availability. Never substitute another model.
- **No nesting:** `[agents] max_depth = 1` in `~/.codex/config.toml` prevents workers from spawning workers.
- **Concurrency:** spawn every ready task in the wave before waiting on any of them. Respect `agents.max_concurrent_threads_per_session`.
- **Available agents:** read the runtime's subagent tool description before dispatching. It is the source of truth for names and callable models.
