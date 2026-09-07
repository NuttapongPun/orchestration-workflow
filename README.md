# orchestration-workflow

One orchestration workflow that works the same way in four coding agents: **Claude Code**, **Codex**, **Antigravity CLI (`agy`)**, and **OpenCode**.

The model you are talking to acts as an **orchestrator**: it breaks the job into tasks, briefs worker subagents, sends the results to a reviewer, judges the evidence, and reports once. It does not write code itself. Hard tasks go to a strong worker model, easy tasks to a cheap one. This keeps the expensive model's context small, because the workers hold the files, search results, and command output, and it routes cost by task difficulty.

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
- **OpenCode:** select the `orchestrate` primary agent. The skill is not used there.

**Update:** re-run the same command. **Uninstall:** `curl -fsSL .../install.sh | bash -s -- --uninstall`.

### Working on the repo itself

Clone it and run the installer from the clone. In that mode the runtime files become symlinks into the clone, so edits and `git pull` take effect immediately:

```bash
git clone https://github.com/NuttapongPun/orchestration-workflow.git
cd orchestration-workflow
./install.sh
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

## Customize

1. Edit the prompts, models, or effort levels in `build.py`. Every worker prompt is defined exactly once there.
2. Run `python3 build.py` to regenerate the files for all four runtimes.
3. Commit. Other machines pick up the change with `git pull`.

Changing a model for one runtime is a one-line edit in the `MODELS` table. Adding a runtime means a generator block in `build.py`, a binding file under `skills/orchestrate/references/`, and a row in `install.sh`.

## Runtime notes

- **Antigravity CLI** reads global skills only from `~/.gemini/config/skills/`, not from `~/.agents/skills/` and not from the folders the `skills` CLI targets. `install.sh` creates the right link. `agy agent` lists only primary agents, so the workers do not appear there even though `invoke_subagent` can call them. Start the orchestrator session on the Pro model; `--agent` is ignored when resuming a conversation.
- **Codex** custom agents need Codex 0.153 or newer. The review workers use the `workspace-write` sandbox so tests can run; only `investigate` is sandbox read-only.
- **Claude Code** reads `~/.claude/skills`, not `~/.agents/skills` directly; the symlink handles that. Workers pin `model` and `effort` in frontmatter, and the skill still asks the orchestrator to set `model` explicitly on every dispatch.
- **OpenCode** is the only runtime with a real primary agent, so the orchestrator's "never edit" rule is enforced by permissions there. In the other three it is a prompt rule.
- Reviewers run at the tier of the work they review. The orchestrator's one non-delegable job is to judge the verdict and confirm the tests actually ran.

## Companion skills

These general-purpose skills pair well with this workflow. They install through the [`skills` CLI](https://skills.sh) into `~/.agents/skills/` and link into every agent it detects:

```bash
npx skills add mattpocock/skills --global          # interactive: pick only the ones you want
npx skills add microsoft/playwright-cli --global
npx skills add kepano/obsidian-skills --global --skill defuddle
```

`npx skills update` refreshes them. `~/.agents/.skill-lock.json` records the exact source and commit of each one.

## License

MIT
