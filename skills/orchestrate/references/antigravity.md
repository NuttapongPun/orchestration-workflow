# Antigravity CLI (agy) binding

- **Session model:** the orchestrator must run as Gemini 3.1 Pro (High). Check the session model before starting. If it is a Flash model, tell the commander to switch and stop.
- **Dispatch:** the `invoke_subagent` tool with the worker name: `investigate`, `easy-worker`, `hard-worker`, `review`, `review-hard`. Worker definitions live in `~/.gemini/config/agents/*.md`, or per workspace in `.agents/agents/`.
- **Model rule:** each worker file pins its tier. Easy tier is `flash`, hard tier is `pro`. Do not invoke a worker with the model left on inherit.
- **No nesting:** worker tool lists exclude `invoke_subagent`.
- **Concurrency:** invoke every ready task in the wave before waiting on any of them.
- **Available agents:** run the agent listing or read the tool description before dispatching. If the five workers are not present, report blocked on worker availability.
