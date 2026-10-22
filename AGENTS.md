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
- Read-only workers stay read-only at the runtime level where the runtime supports it, not only in the prompt. Claude Code removes their edit tools. OpenCode denies their edits and gives `investigate` a shell allowlist. Codex has no per-agent mechanism, because every worker inherits the session's sandbox, so there read-only is prompt-only; do not add a per-agent `sandbox_mode` back, since Codex ignores it.
- The plan gate conditions are written once, in the shared `ORCHESTRATOR` text in `build.py`, which generates both `SKILL.md` and every OpenCode `orchestrate.md`; `README.md` summarizes them, and `evals/scenarios/` asserts their phrases. Change all three together, then rebuild and run `python3 evals/run.py --dry-run`.

## Branches

### Install for a human

1. Detect which runtimes they use: `~/.claude`, `~/.codex`, `~/.config/opencode`. The installer detects the same set.
2. Run the one-line installer from `README.md`. Add `--yes` only when the human has said existing workers may be replaced. If they use Codex, tell them first that the installer sets `web_search = "live"` in `~/.codex/config.toml` when no `web_search` setting is there, which lets the orchestrator and every worker browse without per-call approval and exposes them to prompt injection from web pages. If they do not want that, have them set `web_search = "cached"` there before installing.
3. Ask which orchestrator model they will use per runtime and point them at the table in `README.md`. For OpenCode, ask which model stack they want: the installer takes `--opencode-stack=<name>` and defaults to `free` (OpenCode Zen's free models, no provider login needed). The names are the directories under `agents/opencode/`. Any other stack needs that provider linked first (`openai` needs OpenAI, `claude` needs Anthropic, `*-openrouter` needs OpenRouter). Warn them that `free`'s workers run on models whose free terms allow training on what they see (MiMo) or forbid confidential data (Nemotron), so it is wrong for confidential code.
4. Verify with the checks below. Done when every runtime they use lists all five workers.

### Adapt for a human (different models, providers, prompts, or agents)

1. Have them fork or clone. In a clone, `./install.sh` links runtime files to the clone, so edits are live after a fresh session — except Codex agent files, which are copied, so rerun `./install.sh` after `python3 build.py` to refresh them.
2. Change `build.py` only: `MODELS`, `EFFORT` (Claude Code), `EFFORT_OPENAI` (Codex only), `OPENCODE_STACKS`, `BODIES`, `DESC`, and for the orchestrator prompt `ORCHESTRATOR` (wording shared by the skill and OpenCode's primary agent) or `ORCH_SLOTS` (the few passages that differ per runtime). OpenCode takes neither `MODELS` nor `EFFORT_OPENAI`: a stack in `OPENCODE_STACKS` carries one entry per OpenCode agent, `{"model": "<provider/model>", "effort": "low"|"medium"|"high"|None}`, keyed by all six of `orchestrate`, `investigate`, `easy-worker`, `hard-worker`, `review`, `review-hard`. OpenCode 2 has no effort field: a level is written as the model's variant, `model: <provider/model>#<level>`, and `effort: None` writes the bare model, which is how a model without effort variants is handled; the `free` stack uses it on all six. `oc_stack()` expands the usual orchestrator/hard/easy trio into the six entries, and the result is a plain dict you can override per agent. `build.py` validates every stack and fails naming the stack and key, and rejects an `effort` dict whose keys are not agent names, so a typo cannot pass silently. Each stack is generated into its own directory, `agents/opencode/<stack>/`, holding all six files; there is no single selected stack in `build.py`, because `install.sh --opencode-stack=<name>` picks one at install time (default `free`). Adding a stack is one entry plus `python3 build.py`; a new directory is then installable by name with no change to `install.sh`. Keep worker names unless you also update `ORCHESTRATOR` and `ORCH_SLOTS` (they generate `SKILL.md` and the OpenCode orchestrator), every file under `skills/orchestrate/references/`, `OC_AGENTS` and every stack's keys in `OPENCODE_STACKS`, and the OpenCode primary agent's `subagent` allowlist. `build.py` stops with an error if `OC_AGENTS` and `BODIES` drift apart, but it cannot check the other three for you.
3. Run `python3 build.py`, then `./install.sh`.
4. Verify with the checks below. Done when the generated files parse and every runtime lists the workers with the new models.

### Add a runtime

Four touch points, all required. Three are in `build.py`, because their outputs are generated: a generator block that writes `agents/<runtime>/`; a `write()` of the binding file `skills/orchestrate/references/<runtime>.md`, naming the dispatch mechanism and model rule; and a line in the skill's step 0, `ORCH_SLOTS["skill"]["runtime"]`, pointing at that file. The fourth is a row in the `RUNTIMES` array of `install.sh`. Never create the binding file or edit `SKILL.md` directly; `python3 build.py` overwrites them. Before writing the generator block, find the runtime's agent file format, its no-nesting mechanism, and which per-agent settings it actually honors (Codex, for one, ignores `sandbox_mode` in an agent file). Done when the new runtime passes a verification check equivalent to the ones below.

## Verification

Each check is a headless run that asks the runtime to list its subagents. A missing worker means the file was not loaded; read the runtime's own log before editing anything.

- **Claude Code:** `claude -p "Do not use any tools. List the custom subagent types available through the Agent tool." --model sonnet` should name all five.
- **Codex:** `python3 -c "import tomllib,glob;[tomllib.load(open(f,'rb')) for f in glob.glob('$HOME/.codex/agents/*.toml')]"` must parse, and `~/.codex/config.toml` must contain `max_depth = 1` under `[agents]` and a `web_search` setting (the installer's top-level `web_search = "live"`, or whatever the human had set before, at top level or in a profile, which the installer keeps). A `sandbox_mode` line in an installed agent file means it is stale from an older install; Codex ignores the line, and re-installing removes it.
- **OpenCode:** `opencode --version` must be 2.0 or newer. `opencode debug agents | python3 -c "import json,sys;[print(a['id'],a['mode']) for a in json.load(sys.stdin)]"` should list the five workers as `subagent` and `orchestrate` as `primary`. `grep '^model:' ~/.config/opencode/agents/*.md` should print the installed stack's model IDs (default `free`: `opencode/deepseek-v4.1-flash-free` for `orchestrate`, `opencode/mimo-v2.6-flash-free` for `hard-worker` and `review-hard`, `opencode/nemotron-3.5-lightning-free` for `investigate`, `easy-worker`, and `review`). Anything else means a different `--opencode-stack` was installed, or the files are stale. `free` sets no effort, so its model lines carry no `#<variant>` suffix; every other stack's do.
- **Skill:** `~/.agents/skills/orchestrate/SKILL.md` exists and `~/.claude/skills/orchestrate` and `~/.codex/skills/orchestrate` resolve to it.
- **Behavior:** after changing the skill or its plan gate, run `python3 evals/run.py --dry-run`; a live run (`python3 evals/run.py --model <orchestrator model>`, Claude Code only) tests the *installed* skill and costs money, so reinstall first and run it only when the human asks; see `evals/README.md`.

## Facts you cannot find by reading the files

- Codex 0.155 opens role files under `~/.codex/agents/` with O_NOFOLLOW at spawn time. A symlinked file is listed as available but every spawn fails with "agent type is currently not available". `install.sh` therefore copies the Codex files even in link mode. This was confirmed by a probe.
- Claude Code does not read `~/.agents/skills/` directly. The symlink in `~/.claude/skills/` is what makes the skill visible.
- Codex ignores `disable-model-invocation`. It lists the skill to the model, including in worker threads, unless `agents/openai.yaml` sets `policy.allow_implicit_invocation: false`, which `build.py` writes. This was confirmed from Codex session logs (0.153 to 0.159) and the binary (0.160.1).
- Codex ignores `sandbox_mode` and the other session settings in a custom agent file. A role file can override only `developer_instructions`, `model`, `model_reasoning_effort`, `model_reasoning_summary`, `model_verbosity`, `personality`, `service_tier` (though the docs say the service tier also follows the root session's preference), `skills`, and `features` set to false; subagents inherit the parent turn's sandbox and approval settings. The Codex docs say so ("Subagents inherit the parent turn's current sandbox and approval settings"; "A custom agent file can't replace those settings"), and so does upstream `codex-rs/core/src/agent/role.rs`, which matches the 0.162.1 binary. Consequences: in `workspace-write` (the default) every worker, `investigate` included, can write in the workspace; in `read-only` reviewers cannot run tests that write caches; under `--yolo` or full access every worker has full access. Web search (`web_search`: disabled, cached, indexed, live; default cached, or live under `--yolo` or a full-access sandbox) and shell network access (`[sandbox_workspace_write] network_access`, off by default) are session-level as well and cannot be set per agent.
- Codex custom agents need 0.153 or newer. `max_depth`, `max_concurrent_threads_per_session`, `default_subagent_model`, and `default_subagent_reasoning_effort` are the `[agents]` keys the binary accepts.
- OpenCode 1 is not supported. The generated agent files use OpenCode 2's format (`permissions` rule list, `subagent` action, `model: <provider/model>#<variant>`, hex `color`); v1 does not read it.
- `opencode debug agents` asks OpenCode's shared background service, which can answer with the agent list from before files were added. If a freshly installed agent is missing, run it again before editing anything. This was confirmed by a probe.
- `install.sh` is wrapped in `main "$@"` on purpose. Without it, `curl | bash` is cut short when `npx` reads the rest of the script from stdin. Keep the wrapper if you edit the script.
- `npx skills list` misreports the agents for `orchestrate` when it is a symlink into a clone. The runtimes load it correctly; ignore the column.
- The Unity MCP package's skill-sync button writes a duplicate of one companion skill under a different folder name. If a human has both, tell them to keep one.
