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

## Branches

### Install for a human

1. Detect which runtimes they use: `~/.claude`, `~/.codex`, `~/.gemini/config`, `~/.config/opencode`. The installer detects the same set.
2. Run the one-line installer from `README.md`. Add `--yes` only when the human has said existing workers may be replaced.
3. Ask which orchestrator model they will use per runtime and point them at the table in `README.md`. OpenCode additionally needs the OpenAI provider linked, or a model change in `build.py`.
4. Verify with the checks below. Done when every runtime they use lists all five workers.

### Adapt for a human (different models, providers, prompts, or agents)

1. Have them fork or clone. In a clone, `./install.sh` links runtime files to the clone, so edits are live after a fresh session.
2. Change `build.py` only: `MODELS`, `EFFORT`, `OPENCODE_PM_MODEL`, `BODIES`, `DESC`. Keep worker names unless you also update `SKILL.md`, every file under `skills/orchestrate/references/`, and the OpenCode primary agent's `task` allowlist.
3. Run `python3 build.py`, then `./install.sh`.
4. Verify with the checks below. Done when the generated files parse and every runtime lists the workers with the new models.

### Add a runtime

Three touch points, all required: a generator block in `build.py` that writes `agents/<runtime>/`, a binding file `skills/orchestrate/references/<runtime>.md` naming the dispatch mechanism and model rule, and a row in the `RUNTIMES` array of `install.sh`. Also add a line to step 0 of `skills/orchestrate/SKILL.md`. Find the runtime's agent file format and its no-nesting mechanism before writing the block. Done when the new runtime passes a verification check equivalent to the ones below.

## Verification

Each check is a headless run that asks the runtime to list its subagents. A missing worker means the file was not loaded; read the runtime's own log before editing anything.

- **Claude Code:** `claude -p "Do not use any tools. List the custom subagent types available through the Agent tool." --model sonnet` should name all five.
- **Antigravity CLI:** `agy -p "Do not call any tools. List the subagents you could invoke with invoke_subagent." --mode plan` should name all five. `agy agent` will not list them (it shows primary agents only); that is expected.
- **Codex:** `python3 -c "import tomllib,glob;[tomllib.load(open(f,'rb')) for f in glob.glob('$HOME/.codex/agents/*.toml')]"` must parse, and `~/.codex/config.toml` must contain `max_depth = 1` under `[agents]`.
- **OpenCode:** `opencode agent list` should show the five workers as `(subagent)` and `orchestrate (primary)`.
- **Skill:** `~/.agents/skills/orchestrate/SKILL.md` exists and `~/.claude/skills/orchestrate`, `~/.codex/skills/orchestrate`, `~/.gemini/config/skills/orchestrate` resolve to it.

## Facts you cannot find by reading the files

- Antigravity CLI loads global skills only from `~/.gemini/config/skills/`. It ignores `~/.agents/skills/` and the two folders the `skills` CLI writes for it. This was confirmed by a probe, not documentation.
- Antigravity ignores `--agent` when resuming a conversation. Orchestration there needs a fresh session on the Pro model.
- Claude Code does not read `~/.agents/skills/` directly. The symlink in `~/.claude/skills/` is what makes the skill visible.
- Codex custom agents need 0.153 or newer. `max_depth`, `max_concurrent_threads_per_session`, `default_subagent_model`, and `default_subagent_reasoning_effort` are the `[agents]` keys the binary accepts.
- `install.sh` is wrapped in `main "$@"` on purpose. Without it, `curl | bash` is cut short when `npx` reads the rest of the script from stdin. Keep the wrapper if you edit the script.
- `npx skills list` misreports the agents for `orchestrate` when it is a symlink into a clone. The runtimes load it correctly; ignore the column.
- The Unity MCP package's skill-sync button writes a duplicate of one companion skill under a different folder name. If a human has both, tell them to keep one.
