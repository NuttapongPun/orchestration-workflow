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
agents/opencode/         worker subagents + primary orchestrate agent for OpenCode -> ~/.config/opencode/agents/*.md
install.sh               symlinks all of the above into the runtimes present on the machine
```

The same five workers exist in every runtime, with identical prompts. Only the model names differ:

| Worker | Tier | Claude Code | Codex | Antigravity | OpenCode |
|---|---|---|---|---|---|
| `investigate` | easy, read-only | sonnet | gpt-5.6-luna | flash | gpt-5.6-luna |
| `easy-worker` | easy | sonnet | gpt-5.6-luna | flash | gpt-5.6-luna |
| `hard-worker` | hard | opus | gpt-5.6-terra | pro | gpt-5.6-terra |
| `review` | easy, read-only | sonnet | gpt-5.6-luna | flash | gpt-5.6-luna |
| `review-hard` | hard, read-only | opus | gpt-5.6-terra | pro | gpt-5.6-terra |

Workers cannot spawn workers. Claude workers lack the `Agent` tool, Codex gets `[agents] max_depth = 1`, Antigravity workers' tool lists exclude `invoke_subagent`, OpenCode workers have `task: deny`.

## Install

One command installs or updates everything. It detects which of the four runtimes are present, installs the worker agents into each, installs the skill (through the [`skills` CLI](https://skills.sh) when `npx` is available, otherwise by copying), and adds the Codex no-nesting setting if it is missing.

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
```

If worker agents already exist and differ, it asks once before replacing them. Add `--yes` for unattended runs:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --yes
```

That is the whole install. Do not run `npx skills add` on this repo yourself; the installer already does that when the CLI is available, and the skill cannot work without the worker agents the installer adds.

Then start a **fresh** session:

- **Claude Code, Codex, Antigravity:** type `/orchestrate`. The skill is user-invoked only; the model never triggers it on its own.
- **OpenCode:** select the `orchestrate` primary agent. The skill is not used there. The agents use `openai/...` models, so the OpenAI provider must be connected first (see Runtime notes).

**Update** (re-runs the installer; asks before replacing workers you changed):

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
| Claude Code | Fable 5.1, or Opus 5 | `/model` |
| Codex | GPT-6 Astra if your plan has it, else GPT-5.6 Sol | `/model` |
| Antigravity CLI | Gemini 3.1 Pro (High) | session model setting; `--agent` is ignored when resuming, so start fresh |
| OpenCode | GPT-5.6 Sol | pinned in the `orchestrate` primary agent (`OPENCODE_PM_MODEL` in `build.py`) |

A Flash, Haiku, or mini-class model as orchestrator defeats the purpose: it will route badly and accept weak review verdicts.

## OpenCode model stacks

OpenCode fixes each agent's model in its file, so the whole stack (orchestrator, hard worker, easy worker) is chosen once in `build.py` by setting `OPENCODE_STACK`. Five stacks are predefined. Model IDs are in OpenCode's `provider/model` form, as printed by `opencode models` once the provider is linked with `opencode auth login`.

| `OPENCODE_STACK` | Provider | Orchestrator | Hard worker | Easy worker |
|---|---|---|---|---|
| `openai` (default) | OpenAI | `openai/gpt-5.6-sol` | `openai/gpt-5.6-terra` | `openai/gpt-5.6-luna` |
| `openai-openrouter` | OpenRouter | `openrouter/openai/gpt-5.6-sol` | `openrouter/openai/gpt-5.6-terra` | `openrouter/openai/gpt-5.6-luna` |
| `claude` | Anthropic | `anthropic/claude-fable-5-1` | `anthropic/claude-opus-5` | `anthropic/claude-sonnet-5` |
| `claude-openrouter` | OpenRouter | `openrouter/anthropic/claude-fable-5.1` | `openrouter/anthropic/claude-opus-5` | `openrouter/anthropic/claude-sonnet-5` |
| `cheap-openrouter` | OpenRouter | `openrouter/moonshotai/kimi-k3` | `openrouter/z-ai/glm-5.3` | `openrouter/deepseek/deepseek-v4-flash-0731` |

Rough cost per million tokens (input / output), OpenRouter list prices in September 2026:

| Model | Input | Output |
|---|---|---|
| GPT-5.6 Sol / Terra / Luna | $2 / $2 / $0.20 | $10 / $12 / $1.20 |
| GPT-6 Astra | $10 | $50 |
| Claude Fable 5.1 / Opus 5 / Sonnet 5 | $10 / $5 / $2 | $50 / $25 / $10 |
| Kimi K3 / GLM 5.3 / DeepSeek V4 Flash 0731 | $3 / $1.40 / $0.14 | $15 / $4.40 / $0.28 |

Notes:

- The Claude stack mirrors what the Claude Code runtime uses natively (Fable as orchestrator, Opus hard, Sonnet easy). Pick `claude` with an Anthropic key, or `claude-openrouter` to route it through OpenRouter.
- The cheap stack keeps the same three-role shape at roughly a tenth of the cost. Expect weaker routing judgment from the orchestrator; the review step matters more there. `openrouter/z-ai/glm-5.3-flash` is an even cheaper easy-worker option.
- Anthropic's direct IDs use dashes in the version (`claude-fable-5-1`); OpenRouter's use dots (`claude-fable-5.1`). Both are correct for their provider.
- To use a mix, edit the entries in `OPENCODE_STACKS` directly. After any change: `python3 build.py`, then re-run the installer.

## Customize

This repo encodes one way of working. Fork it, or clone it, and change whatever does not match your style, your agents, or your providers: the worker prompts, the model tiers, the effort levels, which runtimes are included. Everything is generated from one file, so a change is one edit.

### Set up the clone

Run the installer from the clone. In that mode the runtime files become symlinks into the clone, so edits and `git pull` take effect immediately without re-installing:

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

Changing a model for one runtime is a one-line edit in the `MODELS` table. Swapping OpenCode to another provider or price point is one line, `OPENCODE_STACK` (see the stacks above). Adding a runtime means a generator block in `build.py`, a binding file under `skills/orchestrate/references/`, and a row in `install.sh`.

## Runtime notes

- **Antigravity CLI** reads global skills only from `~/.gemini/config/skills/`, not from `~/.agents/skills/` and not from the folders the `skills` CLI targets. `install.sh` creates the right link. `agy agent` lists only primary agents, so the workers do not appear there even though `invoke_subagent` can call them. Start the orchestrator session on the Pro model; `--agent` is ignored when resuming a conversation.
- **Codex** custom agents need Codex 0.153 or newer. The review workers use the `workspace-write` sandbox so tests can run; only `investigate` is sandbox read-only.
- **Claude Code** reads `~/.claude/skills`, not `~/.agents/skills` directly; the symlink handles that. Workers pin `model` and `effort` in frontmatter, and the skill still asks the orchestrator to set `model` explicitly on every dispatch.
- **OpenCode** is the only runtime with a real primary agent, so the orchestrator's "never edit" rule is enforced by permissions there. In the other three it is a prompt rule.
- **OpenCode needs the OpenAI provider connected.** The OpenCode agents reference `openai/gpt-5.6-sol`, `openai/gpt-5.6-terra`, and `openai/gpt-5.6-luna`. Link the provider once, either with a ChatGPT login or an API key:

  ```bash
  opencode auth login      # choose OpenAI, then ChatGPT login or API key
  opencode auth list       # should show "OpenAI"
  ```

  To use another provider instead, set `OPENCODE_STACK` in `build.py` (see "OpenCode model stacks"), run `python3 build.py`, and re-run the installer.
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
