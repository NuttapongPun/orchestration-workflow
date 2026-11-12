# orchestration-workflow

One orchestration workflow that works the same way in three coding agents, called runtimes here: **Claude Code**, **Codex**, and **OpenCode**. The model in your session becomes the **orchestrator**: it splits the job into tasks, writes a brief for each, sends them to **workers** (subagents that do the work), has the result reviewed, and reports once. It never writes code itself. Each worker runs on a tier: the hard tier is a stronger model or a higher effort level, and the easy tier is a cheaper model or a lower effort level, so cost follows difficulty. The four workers are the same in every runtime:

- `investigate` reads code, runs commands, and searches the web to find facts. It changes nothing.
- `easy-worker` does simple, well-defined changes on the easy tier.
- `hard-worker` does complex changes on the hard tier.
- `review` checks the finished work against the goal and the repository's rules. It changes nothing.

If you are an AI agent setting this up for someone, read [`AGENTS.md`](AGENTS.md) instead.

## Install

One command installs or updates everything. It finds which of the three runtimes are on your machine and installs the worker agents, the `orchestrate` skill, and the `generate-image` skill into each one.

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
```

If an installed file already exists and differs, the installer asks once before it replaces it. Add `--yes` to replace without asking:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --yes
```

For OpenCode, the installer uses the `free` model stack unless you pick another with `--opencode-stack=<name>`. See [Pick an OpenCode stack](#pick-an-opencode-stack). Do not run `npx skills add` on this repo to get the `orchestrate` workflow. It cannot work without the worker agents that the installer adds.

## What the installer changes in Codex

The installer edits `~/.codex/config.toml`:

- It adds `[agents] max_depth = 1`, which stops workers from starting other workers. If an `[agents]` section exists without `max_depth`, it prints a note asking you to add the line.
- It sets `web_search = "live"`, but only when the file has no `web_search` setting at all. It never overwrites your own value.

With live search, the orchestrator and every worker browse the web without asking you per call, so a page they read can inject instructions. To opt out, set `web_search = "cached"` or `web_search = "disabled"` in `~/.codex/config.toml`, either before you install or afterwards. Uninstalling leaves both lines in place.

Codex workers inherit your session's sandbox and approval settings. Run Codex in the default `workspace-write` sandbox, because `review` needs it to run tests.

## Use it

Start a **fresh** session after installing. Only you can start the workflow. A model never starts it on its own.

- **Claude Code:** type `/orchestrate`.
- **Codex:** type `$orchestrate`.
- **OpenCode:** select the `orchestrate` primary agent.

**Pick a strong orchestrator.** Your session's model plays the orchestrator, and it does the judgment work: splitting the job, writing briefs, and judging review verdicts. It spends few tokens, so a stronger model raises quality more than cost.

| Runtime | Suggested orchestrator | How to set it |
|---|---|---|
| Claude Code | Claude Fable 5.2, medium effort | `/model` |
| Codex | GPT-6.1 Sol, high reasoning effort | `/model` |
| OpenCode | Set by the stack you installed | See [Pick an OpenCode stack](#pick-an-opencode-stack) |

**Questions first.** When a request is unclear, the orchestrator first finds what it can through `investigate`. Then it asks every remaining question in one numbered message, each with a default. Reply "defaults" to accept them all. Once writing starts, it stops again for the plan gate or a step only you can take. Otherwise it takes the safe, reversible choice and lists it in the report.

**Plan gate.** The plan gate is a stop for your approval before the orchestrator sends out the first task that writes anything. It stops in three cases:

- The task is destructive or externally visible.
- The plan is complex. That means two or more hard-tier implementation tasks, not counting review, or one task whose wrong result is expensive to detect or undo.
- You asked for a plan, for example with "plan first".

Otherwise it proceeds without asking. Read-only investigation runs before the gate. Answering the orchestrator's questions or suggesting changes is not approval. The orchestrator reports the plan again and waits for an explicit go.

**At the end** you get one report that says either "ready for you" or "blocked on you", with the step only you can take. One `review` worker checks all non-trivial work. When the whole change is trivial, one file with no logic or behavior change, a worker still makes it but it skips review, and the report says "not reviewed". Workers clean up the processes and scratch files they started, and the report lists anything left behind.

## Pick an OpenCode stack

OpenCode sets each agent's model in its own file, so a **stack** picks the models for the orchestrator and all four workers together. Choose one at install time:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=<name>
```

| Stack | Orchestrator | `investigate`, `easy-worker` | `hard-worker` | `review` | Login |
|---|---|---|---|---|---|
| `free` (default) | DeepSeek V4.1 Flash | MiniMax M3.1 Flash | DeepSeek V4.1 Flash | DeepSeek V4.1 Flash | none (OpenCode Zen) |
| `openai` | GPT-6.1 Sol | GPT-6.1 Terra | GPT-6.1 Terra | GPT-6.1 Sol | OpenAI |
| `claude` | Claude Fable 5.2 | Claude Sonnet 5.5 | Claude Opus 5.5 | Claude Fable 5.2 | Anthropic |
| `openai-openrouter` | GPT-6.1 Sol | GPT-6 Luna | GPT-6.1 Terra | GPT-6.1 Sol | OpenRouter |
| `claude-openrouter` | Claude Opus 5.5 | Claude Sonnet 5.5 | Claude Opus 5.5 | Claude Opus 5.5 | OpenRouter |
| `cheap-openrouter` | GPT-6.1 Terra | Muse Ember | GPT-6.1 Terra | Claude Haiku 5.5 | OpenRouter |

Every stack except `free` needs its provider linked first with `opencode auth login`. Installing a different stack replaces the installed OpenCode agent files, so start a fresh session afterwards. The `free` stack costs nothing, but its models are weaker, so read the review verdicts yourself. The free offer is for a limited time.

**How the models are chosen.** Each stack balances result quality, cost per task, and time per task. In most stacks the strongest model orchestrates and reviews, and cheaper, faster models do the simple work.

**Your data.** `free` uses only models whose providers keep no data and do not train on it. On OpenRouter stacks, you can block providers that train on your prompts in your [OpenRouter privacy settings](https://openrouter.ai/settings/privacy). Muse Ember, in `cheap-openrouter`, has two providers: Meta keeps prompts for 30 days, and Google Vertex keeps some for safety checks. A strict zero-retention setting there may leave Muse Ember with no provider.

## Requirements and known risks

- **Codex** needs 0.153 or newer.
- **OpenCode** needs 2.0 or newer. On macOS, run `brew install anomalyco/tap/opencode-v2`. That formula conflicts with the v1 `opencode` formula, so uninstall v1 first.
- In every runtime, `investigate` and `review` have a full shell, so they stay read-only only because their prompts say so. A prompt-injected model can ignore that.
- `investigate` browses the web, so a page it reads can inject commands, including ones that print API keys from the environment.
- The `generate-image` skill uses `codex` to generate images when it is installed, and `agy` otherwise. It runs `agy` with `--dangerously-skip-permissions`, which lets `agy` run any command without asking.

## Optional companion skills

The workflow works without these. Workers load one when it fits their task, and the orchestrator names most of them in the worker's brief.

- **`tdd` and `diagnosing-bugs`** from [mattpocock/skills](https://github.com/mattpocock/skills): test-first development, and a diagnosis loop for hard bugs and performance regressions.
- **[playwright-cli](https://github.com/microsoft/playwright-cli)** drives a browser from the shell, for checking web pages and running Playwright tests.
- **[defuddle](https://github.com/kepano/obsidian-skills)** extracts clean Markdown from web pages.
- **[frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)** is Anthropic's guidance for UI that avoids generic, AI-looking defaults.

Install the ones you want. Each line matches one item above:

```bash
npx skills add mattpocock/skills --global --skill tdd diagnosing-bugs
npx skills add microsoft/playwright-cli --global
npx skills add kepano/obsidian-skills --global --skill defuddle
npx skills add anthropics/skills --global --skill frontend-design
```

**`generate-image`** makes an image asset from a reference image or from a description. It processes a reference locally when that is good enough, and otherwise has `codex`, then `agy`, generate it, which spends that agent's usage. The main installer already installs it. To install only this skill:

```bash
npx skills add NuttapongPun/orchestration-workflow --global --skill generate-image
```

## Update and uninstall

To update, run the installer again. On OpenCode, pass the same `--opencode-stack` you installed, or the installer offers to replace your agents with the `free` stack. It asks before it replaces anything you changed.

To uninstall from every runtime:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --uninstall
```

Uninstall removes the worker agents and the `orchestrate` and `generate-image` skills. It leaves the Codex `max_depth` and `web_search` lines in `~/.codex/config.toml`, and any companion skills you installed separately.

## Customize

Fork or clone the repo and run `./install.sh` from the clone. The runtimes then link to your copy, so your edits take effect in a fresh session. The installer copies Codex agent files instead, so run `./install.sh` again after a rebuild.

Change models and prompts in `build.py`, then run `python3 build.py`. See [`AGENTS.md`](AGENTS.md) for the full steps and [`evals/README.md`](evals/README.md) for the behavior tests.

## Credits, support, and license

The writing rules in the workers and the orchestrator's report are adapted from the `unslop` and `technical-writing` skills in Lauren Tan's [pStack](https://github.com/cursor/plugins/tree/main/pstack) (MIT). Workers read a project's `DESIGN.md` before UI work. To give agents your visual identity in a structured form, see Google's [DESIGN.md format](https://github.com/google-labs-code/design.md).

If this workflow saves you time, you can support its upkeep:

- [Ko-fi](https://ko-fi.com/nuttapongp)
- [Buy Me a Coffee](https://buymeacoffee.com/nuttapongp)

License: MIT
