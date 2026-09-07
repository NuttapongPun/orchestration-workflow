# OpenCode binding

This runtime does orchestration through its primary `orchestrate` agent, not through this skill. If this skill is loaded in a normal session, tell the commander to switch to the `orchestrate` primary agent and stop.

Worker definitions live in `~/.config/opencode/agents/`: `investigate`, `easy-worker`, `hard-worker`, `review`, `review-hard`. Models and effort are fixed per file; the primary agent's `task` allowlist limits dispatch to these five.
