# orchestration-workflow

One orchestration workflow that works the same way in four coding agents: **Claude Code**, **Codex**, **Antigravity CLI (`agy`)**, and **OpenCode**.

The model you are talking to acts as an **orchestrator**: it breaks the job into tasks, briefs worker subagents, sends the results to a reviewer, judges the evidence, and reports once. It does not write code itself. Hard tasks go to a strong worker model, easy tasks to a cheap one. This keeps the expensive model's context small, because the workers hold the files, search results, and command output, and it routes cost by task difficulty.

## For AI agents

If you are an agent reading this repository to help someone install or adapt the workflow, read [`AGENTS.md`](AGENTS.md) first. It carries the steps for each case, the invariants to preserve, per-runtime verification commands, and the facts that are not visible in the files. This README is written for people.

## How it is organized

```
build.py                 single source of truth: worker prompts + model table. Generates everything below.
skills/orchestrate/      the shared /orchestrate skill (the method) + one short binding file per runtime
agents/claude/           worker subagents for Claude Code      -> ~/.claude/agents/*.md
agents/codex/            worker subagents for Codex            -> ~/.codex/agents/*.toml
agents/antigravity/      worker subagents for Antigravity CLI  -> ~/.gemini/config/agents/*.md
agents/opencode/<stack>/ worker subagents + primary orchestrate agent for OpenCode, one directory per model stack -> ~/.config/opencode/agents/*.md
install.sh               symlinks all of the above into the runtimes present on the machine (Codex worker files are copied, since Codex rejects symlinked agent files). `--opencode-stack=<name>` picks the OpenCode stack.
```

The same five workers exist in every runtime, with identical prompts. Only the model names differ:

| Worker | Tier | Claude Code | Codex | Antigravity | OpenCode\* |
|---|---|---|---|---|---|
| `investigate` | easy, read-only | sonnet | gpt-6-luna | flash | nemotron-3.5-lightning-free |
| `easy-worker` | easy | sonnet | gpt-6-luna | flash | nemotron-3.5-lightning-free |
| `hard-worker` | hard | opus | gpt-6-sol | pro | mimo-v2.6-flash-free |
| `review` | easy, read-only | sonnet | gpt-6-luna | flash | nemotron-3.5-lightning-free |
| `review-hard` | hard, read-only | opus | gpt-6-sol | pro | mimo-v2.6-flash-free |

\* The OpenCode column shows the default `free` stack. OpenCode's models are chosen per install with `--opencode-stack=<name>`; see [OpenCode model stacks](#opencode-model-stacks).

Workers cannot spawn workers. Claude workers lack the `Agent` tool, Codex gets `[agents] max_depth = 1`, Antigravity workers' tool lists exclude `invoke_subagent`, OpenCode workers have `task: deny`.

## Install

One command installs or updates everything. It detects which of the four runtimes are present, installs the worker agents into each, installs the skill (through the [`skills` CLI](https://skills.sh) when `npx` is available, otherwise by copying), and adds the Codex no-nesting setting if it is missing.

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
```

If any installed file already exists and differs (worker agents or the skill), it asks once before replacing them. Add `--yes` for unattended runs:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --yes
```

That is the whole install. Do not run `npx skills add` on this repo yourself; the installer already does that when the CLI is available, and the skill cannot work without the worker agents the installer adds.

OpenCode installs the **`free`** model stack unless you ask for another one. Pick a different one with `--opencode-stack=<name>`:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=claude
```

The names, and an install command for every stack, are listed under [OpenCode model stacks](#opencode-model-stacks). The flag only affects OpenCode; the other runtimes ignore it.

Then start a **fresh** session:

- **Claude Code, Codex, Antigravity:** type `/orchestrate`. The skill is user-invoked only; the model never triggers it on its own.
- **OpenCode:** select the `orchestrate` primary agent. The skill is not used there. The default `free` stack uses OpenCode Zen's free models (`opencode/...`), which worked here with no provider credential of their own. Other stacks need their provider connected first (see Runtime notes).

**Plan gate.** The orchestrator stops for your approval before the first wave that writes anything when a task is destructive or externally visible, when the plan is complex (two or more hard-tier implementation tasks, not counting review, or one whose wrong result is expensive to detect or undo), or when you asked for a plan, for example with "plan first". Otherwise it proceeds without asking. Read-only investigation still runs before the gate.

**Update** (re-runs the installer; asks before replacing workers or the skill you changed):

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
```

**Uninstall** (removes the skill and worker agents from every runtime):

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --uninstall
```

## Choose the orchestrator model

The orchestrator role is played by whatever model your session runs, so pick the strongest one available before typing `/orchestrate`. It does the judgment work (decomposition, briefing, judging review verdicts) and spends few tokens, so a stronger model raises quality more than it raises cost.

| Runtime | Suggested orchestrator | How to set |
|---|---|---|
| Claude Code | Fable 5.1, or Opus 5.5 | `/model` |
| Codex | GPT-6 Astra if your plan has it, else GPT-6 Sol | `/model` |
| Antigravity CLI | Gemini 3.1 Pro (High) | session model setting; `--agent` is ignored when resuming, so start fresh |
| OpenCode | Muse Spark 1.3 on the default `free` stack, which sets no effort; the paid stacks run their orchestrator at low effort | pinned in the `orchestrate` primary agent; each stack sets its own `orchestrate` model and effort in `OPENCODE_STACKS` in `build.py`, and `--opencode-stack=<name>` chooses which stack is installed |

Give this role the best judgment you can afford. Put a provider's cheapest tier in the orchestrator's seat and the workflow loses its point: it routes tasks to the wrong worker and accepts weak review verdicts. That is a statement about the role, not about any model name. A fast, cheap model is exactly what you want doing the work underneath, which is why the default `free` stack runs MiMo V2.6 Flash as its hard worker and Nemotron 3.5 Lightning as its easy one.

## OpenCode model stacks

OpenCode fixes each agent's model and effort in its file, so all six agents are chosen together as a stack. Every stack below is pre-generated into its own directory under `agents/opencode/`, and the installer installs the one you name:

```bash
# free (OpenCode Zen, default; the flag is optional here)
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=free
# openai (OpenAI)
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=openai
# openai-openrouter (OpenRouter)
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=openai-openrouter
# claude (Anthropic)
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=claude
# claude-openrouter (OpenRouter)
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=claude-openrouter
# cheap-openrouter (OpenRouter)
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=cheap-openrouter

# From a clone, the same flag works with ./install.sh, for example:
./install.sh --opencode-stack=openai
```

Re-running with a different stack replaces the six installed OpenCode agent files, and the installer asks before replacing unless `--yes` is passed. Without the flag you get `free`. Model IDs are in OpenCode's `provider/model` form, as printed by `opencode models`; every stack except `free` needs its provider linked first with `opencode auth login`.

Each stack sets a model for each of the six OpenCode agents, so the table has one row per agent and one column per stack, the same shape as `OPENCODE_STACKS` in `build.py`:

| Agent | `free` (default) | `openai` | `openai-openrouter` | `claude` | `claude-openrouter` | `cheap-openrouter` |
|---|---|---|---|---|---|---|
| *Provider* | OpenCode Zen | OpenAI | OpenRouter | Anthropic | OpenRouter | OpenRouter |
| `orchestrate` | `opencode/muse-spark-1.3-contributor-free` | `openai/gpt-6-astra` | `openrouter/openai/gpt-5.6-sol` | `anthropic/claude-fable-5-1` | `openrouter/anthropic/claude-fable-5.1` | `openrouter/moonshotai/kimi-k3` |
| `investigate` | `opencode/nemotron-3.5-lightning-free` | `openai/gpt-5.6-luna` | `openrouter/openai/gpt-5.6-luna` | `anthropic/claude-sonnet-5` | `openrouter/anthropic/claude-sonnet-5` | `openrouter/deepseek/deepseek-v4-flash-0731` |
| `easy-worker` | `opencode/nemotron-3.5-lightning-free` | `openai/gpt-5.6-luna` | `openrouter/openai/gpt-5.6-luna` | `anthropic/claude-sonnet-5` | `openrouter/anthropic/claude-sonnet-5` | `openrouter/deepseek/deepseek-v4-flash-0731` |
| `hard-worker` | `opencode/mimo-v2.6-flash-free` | `openai/gpt-5.6-terra` | `openrouter/openai/gpt-5.6-terra` | `anthropic/claude-opus-5` | `openrouter/anthropic/claude-opus-5` | `openrouter/z-ai/glm-5.3` |
| `review` | `opencode/nemotron-3.5-lightning-free` | `openai/gpt-5.6-luna` | `openrouter/openai/gpt-5.6-luna` | `anthropic/claude-sonnet-5` | `openrouter/anthropic/claude-sonnet-5` | `openrouter/deepseek/deepseek-v4-flash-0731` |
| `review-hard` | `opencode/mimo-v2.6-flash-free` | `openai/gpt-5.6-terra` | `openrouter/openai/gpt-5.6-terra` | `anthropic/claude-opus-5` | `openrouter/anthropic/claude-opus-5` | `openrouter/z-ai/glm-5.3` |

**Effort is set per entry too**, next to the model, as `low`, `medium`, `high`, or `None`. `None` means the generated agent file gets no `reasoningEffort:` line at all, which is what you want for a model that has no effort parameter. Every stack except `free` uses `orchestrate` low, `investigate` low, `easy-worker` medium, `hard-worker` medium, `review` medium, `review-hard` high. The `free` stack sets `None` on all six, because it is unverified whether OpenCode Zen honours the field for those models. Because model and effort are stored per agent, `investigate` can be given a different model or effort from the other easy-tier agents without touching them.

Rough cost per million tokens (input / output), OpenRouter list prices in September 2026:

| Model | Input | Output |
|---|---|---|
| Muse Spark 1.3 (contributor)† / MiMo V2.6 Flash / Nemotron 3.5 Lightning, free on OpenCode Zen | $0 | $0 |
| GPT-5.6 Sol / Terra / Luna | $2 / $2 / $0.20 | $10 / $12 / $1.20 |
| GPT-6 Astra | $10 | $50 |
| Claude Fable 5.1 / Opus 5 / Sonnet 5 | $10 / $5 / $2 | $50 / $25 / $10 |
| Kimi K3 / GLM 5.3 / DeepSeek V4 Flash 0731 | $3 / $1.40 / $0.14 | $15 / $4.40 / $0.28 |

† **Contributor model.** `muse-spark-1.3-contributor-free` is free because it is offered on contributor terms: Meta may use the prompts and completions you send it to train future models. Everything the orchestrator sees, including file paths, code, and worker reports, goes through it. Do not use the `free` stack on confidential code; install `--opencode-stack=openai` or `--opencode-stack=claude` instead.

Notes:

- The `free` stack costs nothing and is the default so the workflow runs out of the box. Vendor-reported specs: MiMo V2.6 Flash has a 200K context and its family claims 73.4% on SWE-bench Verified, which is why it takes the hard tier; Muse Spark 1.3 has a 1M context, useful for an orchestrator that accumulates worker reports; Nemotron 3.5 Lightning has a 262K context and is the fastest of the three (around 297 tok/s per Artificial Analysis) but the weakest reasoner, so it takes the easy tier. Expect weaker routing judgment than the paid stacks give you, and read the review verdicts yourself.
- Other free OpenCode Zen models you can swap into any agent of the `free` stack in `OPENCODE_STACKS`, with their known problems: `opencode/nemotron-3-ultra-free` (reported stream timeouts during tool execution), `opencode/ling-3.0-flash-fin-free` (finance-tuned), `opencode/muse-spark-1.2-contributor-free` (same contributor terms as 1.3), `opencode/big-pickle` (many reports of corrupted output).
- The Claude stack mirrors what the Claude Code runtime uses natively (Fable as orchestrator, Opus hard, Sonnet easy). Pick `claude` with an Anthropic key, or `claude-openrouter` to route it through OpenRouter.
- The cheap stack keeps the same three-role shape at roughly a tenth of the cost. Expect weaker routing judgment from the orchestrator; the review step matters more there. `openrouter/z-ai/glm-5.3-flash` is an even cheaper easy-worker option.
- Anthropic's direct IDs use dashes in the version (`claude-fable-5-1`); OpenRouter's use dots (`claude-fable-5.1`). Both are correct for their provider.
- All stacks are generated, so switching is an install-time choice, not a rebuild: re-run the installer with a different `--opencode-stack=<name>` and start a fresh OpenCode session. To add a stack or change one agent's model or effort, edit `OPENCODE_STACKS` in `build.py`, run `python3 build.py`, then re-install with the flag. The `oc_stack()` helper there fills the six entries from the usual orchestrator/hard/easy trio; override a single agent afterwards when you want it to differ. `build.py` refuses to build a stack that is missing an agent, names an agent that does not exist, or uses an effort other than `low`, `medium`, `high`, or `None`.

## Customize

This repo encodes one way of working. Fork it, or clone it, and change whatever does not match your style, your agents, or your providers: the worker prompts, the model tiers, the effort levels, which runtimes are included. Everything is generated from one file, so a change is one edit.

### Set up the clone

Run the installer from the clone. In that mode the runtime files become symlinks into the clone, so edits and `git pull` take effect immediately without re-installing (Codex worker files are copied instead, because Codex rejects symlinked agent files; rerun `./install.sh` after rebuilding):

```bash
git clone https://github.com/NuttapongPun/orchestration-workflow.git
cd orchestration-workflow
./install.sh
```

If you forked it, clone your fork instead and change `REPO_SLUG` at the top of `install.sh` so the one-line installer points at your fork.

### Make a change

1. Edit the prompts, models, or effort levels in `build.py`. Every worker prompt is defined exactly once there.
2. Run `python3 build.py` to regenerate the files for all four runtimes.
3. Start a fresh session in the runtime to pick up the change. Commit when you are happy with it.

Changing a model for one runtime is a one-line edit in the `MODELS` table. Swapping OpenCode to another provider or price point needs no edit at all: re-run the installer with `--opencode-stack=<name>` (see the stacks above). Adding a runtime means a generator block in `build.py`, a binding file under `skills/orchestrate/references/`, and a row in `install.sh`.

## Runtime notes

- **Antigravity CLI** reads global skills only from `~/.gemini/config/skills/`, not from `~/.agents/skills/` and not from the folders the `skills` CLI targets. `install.sh` creates the right link. `agy agent` lists only primary agents, so the workers do not appear there even though `invoke_subagent` can call them. Start the orchestrator session on the Pro model; `--agent` is ignored when resuming a conversation.
- **Codex** custom agents need Codex 0.153 or newer. The review workers use the `workspace-write` sandbox so tests can run; only `investigate` is sandbox read-only.
- **Claude Code** reads `~/.claude/skills`, not `~/.agents/skills` directly; the symlink handles that. Workers pin `model` and `effort` in frontmatter, and the skill still asks the orchestrator to set `model` explicitly on every dispatch.
- **OpenCode** is the only runtime with a real primary agent, so the orchestrator's "never edit" rule is enforced by permissions there. In the other three it is a prompt rule.
- **OpenCode's default `free` stack needs no provider login.** Its agents reference OpenCode Zen's free models (`opencode/muse-spark-1.3-contributor-free`, `opencode/mimo-v2.6-flash-free`, `opencode/nemotron-3.5-lightning-free`). A probe on a machine whose `opencode auth list` held only OpenRouter and OpenAI credentials, with nothing for OpenCode Zen, answered normally:

  ```bash
  opencode run --model opencode/nemotron-3.5-lightning-free "Reply with exactly the word OK"
  # > build · nemotron-3.5-lightning-free
  # OK
  ```

  If your install does ask for a credential, run `opencode auth login` and pick OpenCode Zen. Free models are rate-limited and can be withdrawn; read the contributor-terms warning under "OpenCode model stacks" before pointing this stack at private code.
- **If you pick the `openai` stack, connect the OpenAI provider first.** Those agents reference `openai/gpt-6-astra`, `openai/gpt-5.6-terra`, and `openai/gpt-5.6-luna`. Link the provider once, either with a ChatGPT login or an API key:

  ```bash
  opencode auth login      # choose OpenAI, then ChatGPT login or API key
  opencode auth list       # should show "OpenAI"
  ```

  The same applies to the other stacks: `claude` needs an Anthropic key, the `*-openrouter` stacks need OpenRouter. To switch, re-run the installer with `--opencode-stack=<name>` (see "OpenCode model stacks").
- Reviewers run at the tier of the work they review. The orchestrator's one non-delegable job is to judge the verdict and confirm the tests actually ran.

## Companion skills

These general-purpose skills pair well with this workflow. They install through the [`skills` CLI](https://skills.sh) into `~/.agents/skills/` and link into every agent it detects:

```bash
npx skills add mattpocock/skills --global          # interactive: pick only the ones you want
npx skills add microsoft/playwright-cli --global
npx skills add kepano/obsidian-skills --global --skill defuddle
```

`npx skills update` refreshes them. `~/.agents/.skill-lock.json` records the exact source and commit of each one.

## Support

If this workflow saves you time, you can support its upkeep:

- [Ko-fi](https://ko-fi.com/nuttapongp)
- [Buy Me a Coffee](https://buymeacoffee.com/nuttapongp)

## License

MIT
