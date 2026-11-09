# orchestration-workflow

One orchestration workflow that works the same way in three coding agents: **Claude Code**, **Codex**, and **OpenCode**.

The model in your session acts as the **orchestrator**. It splits the job into tasks, briefs worker subagents, sends their results to a reviewer, judges the evidence, and reports once. It does not write code itself. Hard tasks go to a worker on a strong model and easy tasks to a worker on a cheap one, so cost follows difficulty. The orchestrator's context stays small, because the workers hold the files, search results, and command output.

## For AI agents

If you are an agent reading this repository to help someone install or adapt the workflow, read [`AGENTS.md`](AGENTS.md) first. It has the steps for each case, the invariants to preserve, the verification commands for each runtime, and the facts that are not visible in the files. This README is written for people.

## How it is organized

```
build.py                 single source of truth: worker prompts and model table. Generates everything below.
skills/orchestrate/      the shared /orchestrate skill (the method) and one short binding file per runtime
agents/claude/           worker subagents for Claude Code      -> ~/.claude/agents/*.md
agents/codex/            worker subagents for Codex            -> ~/.codex/agents/*.toml
agents/opencode/<stack>/ worker subagents and the orchestrate primary agent for OpenCode, one directory per model stack -> ~/.config/opencode/agents/*.md
install.sh               installs the files above into every runtime on the machine (see Install)
evals/                   behavioral tests for the skill (see evals/README.md). Not installed anywhere.
```

The same four workers exist in every runtime, with identical prompts. Only the model names differ:

| Worker | Tier | Claude Code | Codex | OpenCode\* |
|---|---|---|---|---|
| `investigate` | easy, read-only | sonnet | gpt-6-luna | nemotron-3.5-lightning-free |
| `easy-worker` | easy | sonnet | gpt-6-luna | nemotron-3.5-lightning-free |
| `hard-worker` | hard | opus | gpt-6.1-sol | mimo-v2.6-flash-free |
| `review` | hard, read-only | opus | gpt-6.1-sol | mimo-v2.6-flash-free |

\* The OpenCode column shows the default `free` stack. You choose OpenCode's models at install time with `--opencode-stack=<name>`. See [OpenCode model stacks](#opencode-model-stacks).

Workers cannot start other workers. Each runtime enforces this differently. Claude Code workers have no `Agent` tool, Codex runs with `[agents] max_depth = 1`, and OpenCode denies its workers the `subagent` permission.

"Read-only" in the table is the worker's role. Each runtime enforces a different amount of it:

- **Claude Code** gives the read-only workers no edit tools, but gives them `Bash`.
- **OpenCode** denies their edit tools. `investigate` gets a shell limited to an allowlist of inspection commands, and those deny rules are best-effort (see [Runtime notes](#runtime-notes)). `review` gets a full shell so it can run tests.
- **Codex** has no per-agent control. Every worker, `investigate` included, inherits the session's sandbox and approval settings, so read-only is only a prompt rule. Run Codex in the `workspace-write` sandbox, which is the default, because `review` needs it to run tests.

One reviewer, `review`, checks all work, easy and hard, on the strong model. The orchestrator runs it once, after the last change. It runs it earlier only when later work builds on files that an earlier step wrote. `review` checks the change against the acceptance criteria and against the repository's written rules (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, and style guides). It reports spec, standards, and code defects separately, so a clean result in one cannot hide a failure in another.

`review` cites the worker's test output, and it re-runs or adds checks where that output falls short. Every runtime therefore gives it a shell, and with a shell it can still write files. Staying read-only there is a prompt rule.

Workers and `review` check in a real browser only for flows the brief names, new pages, major layout or flow changes, and complex flows.

## Install

One command installs or updates everything. The installer detects which of the three runtimes are on the machine and installs the worker agents and the skill into each one. It also changes two settings in `~/.codex/config.toml`:

- It adds `[agents] max_depth = 1`, which stops workers from starting workers, when the file has no `[agents]` section. If the section exists without `max_depth`, the installer prints a note asking you to add the line yourself.
- It sets `web_search = "live"` when the file has no `web_search` setting. See [Codex web search](#codex-web-search).

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
```

If an installed worker agent or skill file already exists and differs, the installer asks once before it replaces them. Add `--yes` for unattended runs:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --yes
```

That is the whole install. Do not run `npx skills add` on this repo yourself. The installer already runs it in copy mode when `npx` is available, and the skill cannot work without the worker agents that the installer adds.

**Copy mode and link mode.** The installer picks its mode from how you start it:

- **Copy mode** is what `curl | bash` always uses. The installer copies files into each runtime. It installs the skill through the [`skills` CLI](https://skills.sh) (`npx skills add`) when `npx` is available, and copies it directly otherwise. Link mode never uses the `skills` CLI.
- **Link mode** is used only when `install.sh` runs as a file inside a clone (`./install.sh`). The runtime files, the skill included, become symlinks into the clone, so edits and `git pull` take effect without reinstalling. The `skills` CLI does not manage this link, and the installer prints a note saying so. If the CLI installed `orchestrate` earlier, `npx skills update` replaces the link with a copy of GitHub `main`. Run `./install.sh` from the clone again to restore the link.

Both modes copy the Codex worker files, because Codex rejects symlinked agent files.

For OpenCode, the installer installs the **`free`** model stack unless you name another one with `--opencode-stack=<name>`:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=claude
```

[OpenCode model stacks](#opencode-model-stacks) lists every stack with its install command. Only OpenCode reads the flag. The other runtimes ignore it.

Then start a **fresh** session:

- **Claude Code:** type `/orchestrate`.
- **Codex:** type `$orchestrate`.
- **OpenCode:** select the `orchestrate` primary agent. OpenCode does not use the skill. The default `free` stack uses OpenCode Zen's free models (`opencode/...`), which need no provider login of their own. Other stacks need their provider connected first (see [Runtime notes](#runtime-notes)).

Only you can start the skill. The model never starts it on its own. Codex needs `policy.allow_implicit_invocation: false` for this, and `build.py` writes that setting into the skill's `agents/openai.yaml`.

**Plan gate.** The orchestrator stops for your approval before it sends out the first task that writes anything, in three cases:

- The task is destructive or externally visible.
- The plan is complex. That means two or more hard-tier implementation tasks, not counting review, or one task whose wrong result is expensive to detect or undo.
- You asked for a plan, for example with "plan first".

Otherwise it proceeds without asking. Read-only investigation runs before the gate. Answering the orchestrator's questions or suggesting changes is not approval. The orchestrator reports the plan again and waits for an explicit go.

**Update.** Run the installer again. It asks before it replaces workers or a skill you changed:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
```

**Uninstall.** This removes the skill and the worker agents from every runtime:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --uninstall
```

It leaves the Codex `[agents] max_depth = 1` and `web_search` lines in place.

**Antigravity CLI is no longer supported.** If you installed this workflow for Antigravity earlier, neither updating nor uninstalling touches those files. Remove them by hand: `~/.gemini/config/agents/*.md` (the five workers) and `~/.gemini/config/skills/orchestrate`.

### Codex web search

Codex sets web search per session, not per agent. Its default, `cached`, answers from OpenAI's index without live access. The default becomes `live` only under `--yolo` or a full-access sandbox. The installer therefore adds a top-level `web_search = "live"` to `~/.codex/config.toml`, and creates the file if needed. It does so only when the file has no `web_search` setting in any form or profile, so it never overwrites a value you set. `--uninstall` leaves the line in place. If the installer cannot write the file, for example because it is read-only, immutable, or managed by Nix home-manager, it prints a note and continues. Add the line yourself in that case.

With live search, the orchestrator and every worker browse the web without asking per call. Any page they read can carry a prompt injection. To opt out, set `web_search = "cached"` or `web_search = "disabled"` in `~/.codex/config.toml` before you install, or change it afterwards. Shell network access is a separate setting, `[sandbox_workspace_write] network_access`. It is off by default, and the installer does not touch it.

## Choose the orchestrator model

Your session's model plays the orchestrator, so pick the strongest one available before you type `/orchestrate`. The orchestrator does the judgment work: it splits the job, writes the briefs, and judges the review verdicts. It spends few tokens, so a stronger model raises quality more than it raises cost.

| Runtime | Suggested orchestrator | How to set it |
|---|---|---|
| Claude Code | Fable 5.1 or Opus 5.5 | `/model` |
| Codex | GPT-6.1 Sol, high reasoning effort | `/model` |
| OpenCode | DeepSeek V4.1 Flash on the default `free` stack | The installed stack sets the `orchestrate` agent's model and effort. See [OpenCode model stacks](#opencode-model-stacks). |

Give this role the best judgment you can afford. A weak orchestrator sends tasks to the wrong worker and accepts weak review verdicts. Fast, cheap models belong underneath it, doing the work. That is why the default `free` stack runs MiMo V2.6 Flash as its hard worker and Nemotron 3.5 Lightning as its easy one.

## OpenCode model stacks

OpenCode sets each agent's model and effort in the agent's own file, so a stack picks the models for all five agents together. `agents/opencode/` holds one pre-generated directory per stack, and the installer installs the one you name:

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

Installing a different stack replaces the five installed OpenCode agent files. The installer asks first unless you pass `--yes`. Start a fresh session afterwards. Every stack except `free` needs its provider linked first with `opencode auth login`.

The table has one row per agent and one column per stack, the same shape as `OPENCODE_STACKS` in `build.py`. Model IDs use OpenCode's `provider/model` form, as `opencode models` prints them. A `#low`, `#medium`, or `#high` suffix is the effort level.

| Agent | `free` (default) | `openai` | `openai-openrouter` | `claude` | `claude-openrouter` | `cheap-openrouter` |
|---|---|---|---|---|---|---|
| *Provider* | OpenCode Zen | OpenAI | OpenRouter | Anthropic | OpenRouter | OpenRouter |
| `orchestrate` | `opencode/deepseek-v4.1-flash-free` | `openai/gpt-6.1-sol#high` | `openrouter/openai/gpt-6.1-sol#high` | `anthropic/claude-opus-5-5#low` | `openrouter/anthropic/claude-opus-5.5#high` | `openrouter/deepseek/deepseek-v4-pro-0813#high` |
| `investigate` | `opencode/nemotron-3.5-lightning-free` | `openai/gpt-6-luna#low` | `openrouter/openai/gpt-6-luna#low` | `anthropic/claude-sonnet-5-5#low` | `openrouter/anthropic/claude-sonnet-5.5#low` | `openrouter/deepseek/deepseek-v4.1-flash-1017#low` |
| `easy-worker` | `opencode/nemotron-3.5-lightning-free` | `openai/gpt-6-luna#medium` | `openrouter/openai/gpt-6-luna#medium` | `anthropic/claude-sonnet-5-5#medium` | `openrouter/anthropic/claude-sonnet-5.5#medium` | `openrouter/deepseek/deepseek-v4.1-flash-1017#high` |
| `hard-worker` | `opencode/mimo-v2.6-flash-free` | `openai/gpt-6.1-sol#high` | `openrouter/openai/gpt-6.1-sol#high` | `anthropic/claude-opus-5-5#high` | `openrouter/anthropic/claude-opus-5.5#high` | `openrouter/deepseek/deepseek-v4-pro-0813#high` |
| `review` | `opencode/mimo-v2.6-flash-free` | `openai/gpt-6.1-sol#high` | `openrouter/openai/gpt-6.1-sol#high` | `anthropic/claude-opus-5-5#high` | `openrouter/anthropic/claude-opus-5.5#high` | `openrouter/deepseek/deepseek-v4-pro-0813#high` |

Rough cost per million tokens, from OpenRouter list prices in October 2026:

| Model | Input | Output |
|---|---|---|
| DeepSeek V4.1 Flash, MiMo V2.6 Flash†, and Nemotron 3.5 Lightning†, free on OpenCode Zen | $0 | $0 |
| GPT-6.1 Sol | $2 | $10 |
| GPT-6 Luna | $0.10 | $0.50 |
| Claude Opus 5.5 | $4 | $20 |
| Claude Sonnet 5.5 | $2 | $10 |
| DeepSeek V4 Pro 0813 | $0.66 | $1.98 |
| DeepSeek V4.1 Flash 1017 | $0.15 | $0.60 |

The DeepSeek prices are off-peak. At peak, weekdays 01:00-04:00 and 06:00-10:00 UTC, DeepSeek charges double, and OpenRouter passes the peak price through. V4 Pro then costs $1.32 in and $3.96 out, and V4.1 Flash costs $0.30 in and $1.20 out.

† **Free-tier terms.** MiMo V2.6 Flash (`hard-worker` and `review`) is free on terms that let its provider use collected data to improve the model. Nemotron 3.5 Lightning (`investigate` and `easy-worker`) is for trial use only, with no personal or confidential data. These workers read your files and code, and only the orchestrator's provider promises zero retention. Do not use the `free` stack on confidential code. Install `--opencode-stack=openai` or `--opencode-stack=claude` instead.

The `free` stack costs nothing, but its models are weaker. Read the review verdicts yourself.

## Customize

This repo encodes one way of working. Fork or clone it, and change whatever does not fit your style, your agents, or your providers: the worker prompts, the model tiers, the effort levels, or which runtimes are included. `build.py` generates every prompt and model setting, so most changes are one edit there.

### Set up the clone

Run the installer from the clone as `./install.sh`. That is link mode (see [Install](#install)), so edits and `git pull` take effect without reinstalling. Codex is the exception: its worker files are copies, so run `./install.sh` again after you rebuild.

```bash
git clone https://github.com/NuttapongPun/orchestration-workflow.git
cd orchestration-workflow
./install.sh
```

`--copy` forces copy mode even from a clone. `--link` forces link mode, and stops with an error when the script does not run as a file inside a clone.

If you forked the repo, clone your fork instead. Then change `REPO_SLUG` at the top of `install.sh` so the one-line installer points at your fork.

### Make a change

1. Edit the prompts, models, or effort levels in `build.py`. Every worker prompt is defined there exactly once.
2. Run `python3 build.py` to regenerate the files for every runtime.
3. If you use Codex, run `./install.sh` to refresh its copied worker files.
4. Start a fresh session in the runtime to pick up the change. Commit once it works.

To change a model for Claude Code or Codex, edit one line in the `MODELS` table. OpenCode's models live in `OPENCODE_STACKS`. To move OpenCode to another provider or price point, you do not need to edit anything. Run the installer again with `--opencode-stack=<name>` (see [OpenCode model stacks](#opencode-model-stacks)).

Adding a runtime takes four changes: a generator block in `build.py`, a binding file under `skills/orchestrate/references/`, a line in step 0 of the skill, and a row in `install.sh`. `build.py` generates the binding file and the skill line, so add both of them in `build.py`.

After you change the skill or its plan gate, run `python3 evals/run.py --dry-run` to validate the eval scenarios. A live run works in Claude Code only, tests the *installed* skill, and costs money. See [`evals/README.md`](evals/README.md).

## Runtime notes

- **Codex** needs 0.153 or newer. Run sessions in `workspace-write`, the default. Workers inherit your session's sandbox, so the read-only workers are read-only by prompt only. See [Codex web search](#codex-web-search) for the browsing setting.
- **OpenCode** needs 2.0 or newer. On macOS, run `brew install anomalyco/tap/opencode-v2`. That formula conflicts with the v1 `opencode` formula, so uninstall v1 first. The read-only rules for `investigate` and `review` are best-effort, and a prompt-injected model can get past them.
- **Providers (OpenCode):** `free` needs no login. If your install asks for one, run `opencode auth login` and pick OpenCode Zen. Every other stack needs its provider linked first with `opencode auth login`: `openai` needs OpenAI, `claude` needs Anthropic, and `*-openrouter` needs OpenRouter.

## Companion skills

The workflow works without any of these. Install only the ones you use. The orchestrator and every worker see the description of every installed skill. A skill that a worker cannot run, such as one that starts agents or interviews you, only adds noise.

### For workers

Workers load one of these when it matches their task. They install through the [`skills` CLI](https://skills.sh) into `~/.agents/skills/`, and the CLI links them into every agent it detects. `npx skills update` refreshes them, and `~/.agents/.skill-lock.json` records the source and commit of each one.

**`tdd` and `diagnosing-bugs`** from [mattpocock/skills](https://github.com/mattpocock/skills): test-first development, and a diagnosis loop for hard bugs and performance regressions. Install these two rather than the whole pack, which is built for working with you directly.

```bash
npx skills add mattpocock/skills --global --skill tdd diagnosing-bugs
```

**[playwright-cli](https://github.com/microsoft/playwright-cli)** drives a browser from the shell, for checking web pages and running Playwright tests. `review` can use it too, because it needs only a shell.

```bash
npx skills add microsoft/playwright-cli --global
```

**[defuddle](https://github.com/kepano/obsidian-skills)** extracts clean Markdown from web pages. It is one skill from Kepano's Obsidian pack.

```bash
npx skills add kepano/obsidian-skills --global --skill defuddle
```

**[frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)** is Anthropic's guidance for UI that avoids generic, AI-looking defaults.

```bash
npx skills add anthropics/skills --global --skill frontend-design
```

### For you

**`unslop` and `technical-writing`** come from Lauren Tan's [pstack](https://github.com/cursor/plugins/tree/main/pstack). `/unslop` removes AI-sounding patterns from text. `/technical-writing` is a standard for docs, READMEs, PR descriptions, and commit messages, and it applies `unslop` as it goes. You start both yourself, so workers never load them. Run them on writing you want to tighten.

```bash
npx skills add cursor/plugins --global --skill unslop technical-writing
```

Workers read a project's `DESIGN.md` before UI work. To give agents your visual identity in a structured form, see Google's [DESIGN.md format](https://github.com/google-labs-code/design.md).

## Support

If this workflow saves you time, you can support its upkeep:

- [Ko-fi](https://ko-fi.com/nuttapongp)
- [Buy Me a Coffee](https://buymeacoffee.com/nuttapongp)

## License

MIT
