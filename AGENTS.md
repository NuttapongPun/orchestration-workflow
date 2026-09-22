# AGENTS.md

You are reading this because a human asked you to set up, adapt, or debug this orchestration workflow for them. `README.md` is written for people. This file is written for you: the steps, the invariants, and the facts you cannot discover by reading the files.

## Mental model

The model in the human's session is the **orchestrator**. It decomposes, briefs, dispatches, has work reviewed, judges the evidence, and never edits. Five **workers** do the work, and they are identical across runtimes except for model names:

- `investigate` (easy, read-only), `easy-worker` (easy), `hard-worker` (hard), `review` (easy, read-only), `review-hard` (hard, read-only).
- **Tier** means model class. Easy is the cheap model, hard is the strong one. Effort levels ride along with tier.

`build.py` is the single source of truth: every prompt and model name is defined once there and generated into `skills/orchestrate/` and `agents/<runtime>/`. `install.sh` places the generated files into runtimes. Read those two files before changing anything; do not edit generated files by hand.

## Invariants

Preserve these when adapting. Each one closes a failure the workflow was built to prevent.

- Worker names are identical in every runtime, so the shared skill can name them.
- Workers cannot spawn workers. Each runtime enforces it differently (see `build.py`); keep the enforcement when adding one.
- Reviewers run at the tier of the work they review, and the orchestrator judges the verdict itself, including whether the tests actually ran.
- The skill is user-invoked only (`disable-model-invocation: true`). A model must never start orchestration on its own.
- Read-only workers stay read-only at the runtime level where the runtime supports it, not only in the prompt.
- The plan gate conditions are identical in the `SKILL` and `OPENCODE_ORCHESTRATE` literals in `build.py`, and `README.md` summarizes them. Change all three together, then rebuild.

## Branches

### Install for a human

1. Detect which runtimes they use: `~/.claude`, `~/.codex`, `~/.gemini/config`, `~/.config/opencode`. The installer detects the same set.
2. Run the one-line installer from `README.md`. Add `--yes` only when the human has said existing workers may be replaced.
3. Ask which orchestrator model they will use per runtime and point them at the table in `README.md`. For OpenCode, ask which model stack they want: the installer takes `--opencode-stack=<name>` and defaults to `free` (OpenCode Zen's free models, no provider login needed in the probe recorded in `README.md`). The names are the directories under `agents/opencode/`. Any other stack needs that provider linked first (`openai` needs OpenAI, `claude` needs Anthropic, `*-openrouter` needs OpenRouter). Warn them that `free`'s orchestrator is a contributor model: Meta may train on what it sees, so it is wrong for confidential code.
4. Verify with the checks below. Done when every runtime they use lists all five workers.

### Adapt for a human (different models, providers, prompts, or agents)

1. Have them fork or clone. In a clone, `./install.sh` links runtime files to the clone, so edits are live after a fresh session — except Codex agent files, which are copied, so rerun `./install.sh` after `python3 build.py` to refresh them.
2. Change `build.py` only: `MODELS`, `EFFORT` (Claude Code), `EFFORT_OPENAI` (Codex only), `OPENCODE_STACKS`, `BODIES`, `DESC`. OpenCode takes neither `MODELS` nor `EFFORT_OPENAI`: a stack in `OPENCODE_STACKS` carries one entry per OpenCode agent, `{"model": "<provider/model>", "effort": "low"|"medium"|"high"|None}`, keyed by all six of `orchestrate`, `investigate`, `easy-worker`, `hard-worker`, `review`, `review-hard`. `effort: None` omits the `reasoningEffort:` line from that agent's file, which is how a model without an effort parameter is handled; the `free` stack uses it on all six. `oc_stack()` expands the usual orchestrator/hard/easy trio into the six entries, and the result is a plain dict you can override per agent. `build.py` validates every stack and fails naming the stack and key, and rejects an `effort` dict whose keys are not agent names, so a typo cannot pass silently. Each stack is generated into its own directory, `agents/opencode/<stack>/`, holding all six files; there is no single selected stack in `build.py`, because `install.sh --opencode-stack=<name>` picks one at install time (default `free`). Adding a stack is one entry plus `python3 build.py`; a new directory is then installable by name with no change to `install.sh`. Keep worker names unless you also update `SKILL.md`, every file under `skills/orchestrate/references/`, `OC_AGENTS` and every stack's keys in `OPENCODE_STACKS`, and the OpenCode primary agent's `task` allowlist. `build.py` stops with an error if `OC_AGENTS` and `BODIES` drift apart, but it cannot check the other three for you.
3. Run `python3 build.py`, then `./install.sh`.
4. Verify with the checks below. Done when the generated files parse and every runtime lists the workers with the new models.

### Add a runtime

Three touch points, all required: a generator block in `build.py` that writes `agents/<runtime>/`, a binding file `skills/orchestrate/references/<runtime>.md` naming the dispatch mechanism and model rule, and a row in the `RUNTIMES` array of `install.sh`. Also add a line to step 0 of `skills/orchestrate/SKILL.md`. Find the runtime's agent file format and its no-nesting mechanism before writing the block. Done when the new runtime passes a verification check equivalent to the ones below.

## Verification

Each check is a headless run that asks the runtime to list its subagents. A missing worker means the file was not loaded; read the runtime's own log before editing anything.

- **Claude Code:** `claude -p "Do not use any tools. List the custom subagent types available through the Agent tool." --model sonnet` should name all five.
- **Antigravity CLI:** `agy -p "Do not call any tools. List the subagents you could invoke with invoke_subagent." --mode plan` should name all five. `agy agent` will not list them (it shows primary agents only); that is expected.
- **Codex:** `python3 -c "import tomllib,glob;[tomllib.load(open(f,'rb')) for f in glob.glob('$HOME/.codex/agents/*.toml')]"` must parse, and `~/.codex/config.toml` must contain `max_depth = 1` under `[agents]`.
- **OpenCode:** `opencode agent list` should show the five workers as `(subagent)` and `orchestrate (primary)`. `grep '^model:' ~/.config/opencode/agents/*.md` should print the installed stack's model IDs (default `free`: `opencode/muse-spark-1.3-contributor-free` for `orchestrate`, `opencode/mimo-v2.6-flash-free` for `hard-worker` and `review-hard`, `opencode/nemotron-3.5-lightning-free` for `investigate`, `easy-worker`, and `review`). Anything else means a different `--opencode-stack` was installed, or the files are stale. `free` sets no effort, so `grep -c reasoningEffort ~/.config/opencode/agents/*.md` is 0 for each file on that stack and non-zero on every other stack.
- **Skill:** `~/.agents/skills/orchestrate/SKILL.md` exists and `~/.claude/skills/orchestrate`, `~/.codex/skills/orchestrate`, `~/.gemini/config/skills/orchestrate` resolve to it.

## Facts you cannot find by reading the files

- Antigravity CLI loads global skills only from `~/.gemini/config/skills/`. It ignores `~/.agents/skills/` and the two folders the `skills` CLI writes for it. This was confirmed by a probe, not documentation.
- Codex 0.155 opens role files under `~/.codex/agents/` with O_NOFOLLOW at spawn time. A symlinked file is listed as available but every spawn fails with "agent type is currently not available". `install.sh` therefore copies the Codex files even in link mode. This was confirmed by a probe.
- Antigravity ignores `--agent` when resuming a conversation. Orchestration there needs a fresh session on the Pro model.
- Claude Code does not read `~/.agents/skills/` directly. The symlink in `~/.claude/skills/` is what makes the skill visible.
- Codex custom agents need 0.153 or newer. `max_depth`, `max_concurrent_threads_per_session`, `default_subagent_model`, and `default_subagent_reasoning_effort` are the `[agents]` keys the binary accepts.
- `install.sh` is wrapped in `main "$@"` on purpose. Without it, `curl | bash` is cut short when `npx` reads the rest of the script from stdin. Keep the wrapper if you edit the script.
- `npx skills list` misreports the agents for `orchestrate` when it is a symlink into a clone. The runtimes load it correctly; ignore the column.
- The Unity MCP package's skill-sync button writes a duplicate of one companion skill under a different folder name. If a human has both, tell them to keep one.
