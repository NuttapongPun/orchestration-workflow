# Claude Code binding

- **Dispatch:** the `Agent` tool with `subagent_type` set to `investigate`, `easy-worker`, `hard-worker`, `review`, or `review-hard`. Worker definitions live in `~/.claude/agents/`.
- **Model rule:** set `model` explicitly on every Agent call even though the worker file has a default. Easy tier is `sonnet`, hard tier is `opus`. Never rely on the session default.
- **Never use `subagent_type: "fork"`** for production tasks. Forks ignore the model override.
- **Concurrency:** dispatch a whole wave in a single message, one Agent call per task, so they run concurrently.
- **Available agents:** read the "Available agent types" list in the system prompt before dispatching. If the five workers are not listed, report blocked on worker availability.
