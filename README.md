# orchestration-workflow

One orchestration workflow that works the same way in three coding agents: **Claude Code**, **Codex**, and **OpenCode**.

The model you are talking to acts as an **orchestrator**: it breaks the job into tasks, briefs worker subagents, sends the results to a reviewer, judges the evidence, and reports once. It does not write code itself. Hard tasks go to a strong worker model, easy tasks to a cheap one. This keeps the expensive model's context small, because the workers hold the files, search results, and command output, and it routes cost by task difficulty.

## For AI agents

If you are an agent reading this repository to help someone install or adapt the workflow, read [`AGENTS.md`](AGENTS.md) first. It carries the steps for each case, the invariants to preserve, per-runtime verification commands, and the facts that are not visible in the files. This README is written for people.

## How it is organized

```
build.py                 single source of truth: worker prompts + model table. Generates everything below.
skills/orchestrate/      the shared /orchestrate skill (the method) + one short binding file per runtime
agents/claude/           worker subagents for Claude Code      -> ~/.claude/agents/*.md
agents/codex/            worker subagents for Codex            -> ~/.codex/agents/*.toml
agents/opencode/<stack>/ worker subagents + primary orchestrate agent for OpenCode, one directory per model stack -> ~/.config/opencode/agents/*.md
install.sh               installs all of the above into the runtimes present on the machine: symlinks when run as ./install.sh in a clone, copies for the one-line install (Codex worker files are always copied, since Codex rejects symlinked agent files). `--opencode-stack=<name>` picks the OpenCode stack.
evals/                   behavioral tests for the skill (see evals/README.md). Not installed anywhere.
```

The same five workers exist in every runtime, with identical prompts. Only the model names differ:

| Worker | Tier | Claude Code | Codex | OpenCode\* |
|---|---|---|---|---|
| `investigate` | easy, read-only | sonnet | gpt-6-luna | nemotron-3.5-lightning-free |
| `easy-worker` | easy | sonnet | gpt-6-luna | nemotron-3.5-lightning-free |
| `hard-worker` | hard | opus | gpt-6.1-sol | mimo-v2.6-flash-free |
| `review` | easy, read-only | sonnet | gpt-6-luna | nemotron-3.5-lightning-free |
| `review-hard` | hard, read-only | opus | gpt-6.1-sol | mimo-v2.6-flash-free |

\* The OpenCode column shows the default `free` stack. OpenCode's models are chosen per install with `--opencode-stack=<name>`; see [OpenCode model stacks](#opencode-model-stacks).

Workers cannot spawn workers. Claude workers lack the `Agent` tool, Codex gets `[agents] max_depth = 1`, OpenCode workers deny the `subagent` permission.

"Read-only" in the table is the worker's role. How much of it each runtime enforces differs:

- **Claude Code** gives the read-only workers no edit tools, but does give them `Bash`.
- **OpenCode** denies their edit tools. `investigate` also gets a shell limited to an allowlist of inspection commands, whose deny rules are best-effort (see Runtime notes); `review` and `review-hard` get a full shell so they can run tests.
- **Codex** has no per-agent control. Every worker, `investigate` included, inherits the session's sandbox and approval settings, so read-only is a prompt rule for all of them. Run Codex in the `workspace-write` sandbox (the default): reviewers need it to run tests.

`review` and `review-hard` cite the worker's test output and re-run or add checks where it falls short, so every runtime gives them a shell, and through it they can still write. Staying read-only there is a prompt rule.

## Install

One command installs or updates everything. It detects which of the three runtimes are present, installs the worker agents and the skill into each, and changes two Codex settings in `~/.codex/config.toml`: it adds the no-nesting setting (`[agents] max_depth = 1`) when the file has no `[agents]` section, and it sets `web_search = "live"` when no `web_search` setting is there yet (see [Codex web search](#codex-web-search)). If the `[agents]` section is already there without `max_depth`, it prints a note asking you to add the line yourself.

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
```

If any installed file already exists and differs (worker agents or the skill), it asks once before replacing them. Add `--yes` for unattended runs:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --yes
```

That is the whole install. Do not run `npx skills add` on this repo yourself; the installer already does that in copy mode when the CLI is available, and the skill cannot work without the worker agents the installer adds.

**Copy mode and link mode.** The installer picks its mode from how it was started:

- **Copy mode** is what `curl | bash` always uses. Files are copied into each runtime, and the skill is installed through the [`skills` CLI](https://skills.sh) (`npx skills add`) when `npx` is available, otherwise copied directly. This is the only mode that uses the `skills` CLI.
- **Link mode** is used only when `install.sh` runs as a real file inside a clone (`./install.sh`). Runtime files, the skill included, become symlinks into the clone, so edits and `git pull` take effect without re-installing. The `skills` CLI does not manage this link, and the installer prints a note saying so: if the CLI installed `orchestrate` earlier, `npx skills update` will replace the link with a copy of GitHub `main`. Re-run `./install.sh` from the clone to restore the link.

Codex worker files are copied in both modes, because Codex rejects symlinked agent files.

OpenCode installs the **`free`** model stack unless you ask for another one. Pick a different one with `--opencode-stack=<name>`:

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --opencode-stack=claude
```

The names, and an install command for every stack, are listed under [OpenCode model stacks](#opencode-model-stacks). The flag only affects OpenCode; the other runtimes ignore it.

Then start a **fresh** session:

- **Claude Code:** type `/orchestrate`. **Codex:** type `$orchestrate`. The skill is user-invoked only; the model never triggers it on its own (Codex needs `policy.allow_implicit_invocation: false` for this, which `build.py` writes into the skill's `agents/openai.yaml`).
- **OpenCode:** select the `orchestrate` primary agent. The skill is not used there. The default `free` stack uses OpenCode Zen's free models (`opencode/...`), which worked here with no provider credential of their own. Other stacks need their provider connected first (see Runtime notes).

**Plan gate.** The orchestrator stops for your approval before the first wave that writes anything when a task is destructive or externally visible, when the plan is complex (two or more hard-tier implementation tasks, not counting review, or one whose wrong result is expensive to detect or undo), or when you asked for a plan, for example with "plan first". Otherwise it proceeds without asking. Answering its questions or suggesting changes is not approval; it re-reports the plan, still blocked on you, and waits for an explicit go. Read-only investigation still runs before the gate.

**Update** (re-runs the installer; asks before replacing workers or the skill you changed):

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
```

**Uninstall** (removes the skill and worker agents from every runtime):

```bash
curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash -s -- --uninstall
```

It leaves the Codex `[agents] max_depth = 1` and `web_search` lines in place.

**Antigravity CLI is no longer supported.** If you installed this workflow for Antigravity earlier, neither updating nor uninstalling touches those files. Remove them by hand: `~/.gemini/config/agents/*.md` (the five workers) and `~/.gemini/config/skills/orchestrate`.

### Codex web search

Codex sets web search per session, not per agent. Its default, `cached`, answers from OpenAI's index without live access; only under `--yolo` or a full-access sandbox does the default become `live`. The installer therefore adds a top-level `web_search = "live"` to `~/.codex/config.toml` (creating the file if needed), but only when no `web_search` setting is there yet, in any form or profile; it never overwrites a value you set, and `--uninstall` leaves the line in place. If the file can't be written (read-only, immutable, or managed by a tool such as Nix home-manager), the installer prints a note and carries on, and you add the line yourself.

The trade-off: with live search, the orchestrator and every worker browse the web without asking per call, which also exposes all of them to prompt injection from the pages they read. To opt out, set `web_search = "cached"` (or `"disabled"`) in `~/.codex/config.toml` before installing, or change it afterwards. Shell network access is a separate setting (`[sandbox_workspace_write] network_access`, off by default) that the installer does not touch.

## Choose the orchestrator model

The orchestrator role is played by whatever model your session runs, so pick the strongest one available before typing `/orchestrate`. It does the judgment work (decomposition, briefing, judging review verdicts) and spends few tokens, so a stronger model raises quality more than it raises cost.

| Runtime | Suggested orchestrator | How to set |
|---|---|---|
| Claude Code | Fable 5.1, or Opus 5.5 | `/model` |
| Codex | GPT-6.1 Sol (high reasoning effort) | Select GPT-6.1 Sol in the active Codex session with `/model` |
| OpenCode | Muse Spark 1.3 on the default `free` stack, which sets no effort; `openai` and `cheap-openrouter` run their orchestrator at high effort, the other paid stacks at low | pinned in the `orchestrate` primary agent; each stack sets its own `orchestrate` model and effort in `OPENCODE_STACKS` in `build.py`, and `--opencode-stack=<name>` chooses which stack is installed |

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
| `orchestrate` | `opencode/muse-spark-1.3-contributor-free` | `openai/gpt-6.1-sol#high` | `openrouter/openai/gpt-6-sol#low` | `anthropic/claude-opus-5-5#low` | `openrouter/anthropic/claude-opus-5.5#low` | `openrouter/deepseek/deepseek-v4-pro-0813#high` |
| `investigate` | `opencode/nemotron-3.5-lightning-free` | `openai/gpt-6-luna#low` | `openrouter/openai/gpt-6-luna#low` | `anthropic/claude-sonnet-5#low` | `openrouter/anthropic/claude-sonnet-5#low` | `openrouter/deepseek/deepseek-v4-flash-0731#low` |
| `easy-worker` | `opencode/nemotron-3.5-lightning-free` | `openai/gpt-6-luna#medium` | `openrouter/openai/gpt-6-luna#medium` | `anthropic/claude-sonnet-5#medium` | `openrouter/anthropic/claude-sonnet-5#medium` | `openrouter/deepseek/deepseek-v4-flash-0731#high` |
| `hard-worker` | `opencode/mimo-v2.6-flash-free` | `openai/gpt-6.1-sol#high` | `openrouter/openai/gpt-6-sol#high` | `anthropic/claude-opus-5-5#high` | `openrouter/anthropic/claude-opus-5.5#high` | `openrouter/deepseek/deepseek-v4-pro-0813#high` |
| `review` | `opencode/nemotron-3.5-lightning-free` | `openai/gpt-6-luna#medium` | `openrouter/openai/gpt-6-luna#medium` | `anthropic/claude-sonnet-5#medium` | `openrouter/anthropic/claude-sonnet-5#medium` | `openrouter/deepseek/deepseek-v4-flash-0731#high` |
| `review-hard` | `opencode/mimo-v2.6-flash-free` | `openai/gpt-6.1-sol#high` | `openrouter/openai/gpt-6-sol#high` | `anthropic/claude-opus-5-5#high` | `openrouter/anthropic/claude-opus-5.5#high` | `openrouter/deepseek/deepseek-v4-pro-0813#high` |

**Effort is set per entry too**, next to the model, as `low`, `medium`, `high`, or `None`. OpenCode 2 takes effort as the model's variant, so a level is written as `model: <provider/model>#<level>`, and `None` writes the bare model with no variant, which is what you want for a model that has no effort variants. The `openai` stack uses GPT-6.1 Sol at high effort for `orchestrate`, `hard-worker`, and `review-hard`; its easy agents run Luna at medium, except `investigate` at low. `openai-openrouter`, `claude`, and `claude-openrouter` use `orchestrate` low, `investigate` low, `easy-worker` medium, `hard-worker` high, `review` medium, `review-hard` high. `cheap-openrouter` differs; see its note below. The `free` stack sets `None` on all six, because it is unverified which effort variants OpenCode Zen offers for those models. Because model and effort are stored per agent, `investigate` can be given a different model or effort from the other easy-tier agents without touching them.


Rough cost per million tokens (input / output), OpenRouter list prices in October 2026:

| Model | Input | Output |
|---|---|---|
| Muse Spark 1.3 (contributor)† / MiMo V2.6 Flash / Nemotron 3.5 Lightning, free on OpenCode Zen | $0 | $0 |
| GPT-6.1 Sol / GPT-6 Luna | $2 / $0.10 | $10 / $0.50 |
| Claude Opus 5.5 / Sonnet 5 | $4 / $2 | $20 / $10 |
| DeepSeek V4 Pro 0813 / V4 Flash 0731 | $0.66 / $0.14 | $1.98 / $0.28 |

† **Contributor model.** `muse-spark-1.3-contributor-free` is free because it is offered on contributor terms: Meta may use the prompts and completions you send it to train future models. Everything the orchestrator sees, including file paths, code, and worker reports, goes through it. Do not use the `free` stack on confidential code; install `--opencode-stack=openai` or `--opencode-stack=claude` instead.

Notes:

- The `free` stack costs nothing and is the default so the workflow runs out of the box. Vendor-reported specs: MiMo V2.6 Flash has a 200K context and its family claims 73.4% on SWE-bench Verified, which is why it takes the hard tier; Muse Spark 1.3 has a 1M context, useful for an orchestrator that accumulates worker reports; Nemotron 3.5 Lightning has a 262K context and is the fastest of the three (around 297 tok/s per Artificial Analysis) but the weakest reasoner, so it takes the easy tier. Expect weaker routing judgment than the paid stacks give you, and read the review verdicts yourself.
- Other free OpenCode Zen models you can swap into any agent of the `free` stack in `OPENCODE_STACKS`, with their known problems: `opencode/nemotron-3-ultra-free` (reported stream timeouts during tool execution), `opencode/ling-3.0-flash-fin-free` (finance-tuned), `opencode/muse-spark-1.2-contributor-free` (same contributor terms as 1.3), `opencode/big-pickle` (many reports of corrupted output).
- The Claude stack mirrors what the Claude Code runtime uses natively (Opus 5.5 as orchestrator and hard tier, Sonnet easy). Pick `claude` with an Anthropic key, or `claude-openrouter` to route it through OpenRouter.
- The cheap stack keeps the same three-role shape on DeepSeek alone: V4 Pro 0813 for `orchestrate`, `hard-worker`, and `review-hard`, V4 Flash 0731 for the easy tier. A session costs roughly $0.94 against roughly $2.60 for this stack's previous Kimi K3 / GLM 5.3 line-up. Expect weaker routing judgment from the orchestrator; the review step matters more there.
- The DeepSeek prices above are its standard rate; DeepSeek doubles its price during peak hours.
- These DeepSeek models offer only `low`, `high`, and `max` effort, with no `medium`, so the cheap stack rounds the usual medium up to `high` (`easy-worker`, `review`). `orchestrate` is raised from its usual `low` to `high` on purpose, for planning quality; `investigate` stays at `low`.
- Anthropic's direct IDs use dashes in the version (`claude-opus-5-5`); OpenRouter's use dots (`claude-opus-5.5`). Both are correct for their provider.
- All stacks are generated, so switching is an install-time choice, not a rebuild: re-run the installer with a different `--opencode-stack=<name>` and start a fresh OpenCode session. To add a stack or change one agent's model or effort, edit `OPENCODE_STACKS` in `build.py`, run `python3 build.py`, then re-install with the flag. The `oc_stack()` helper there fills the six entries from the usual orchestrator/hard/easy trio; override a single agent afterwards when you want it to differ. `build.py` refuses to build a stack that is missing an agent, names an agent that does not exist, or uses an effort other than `low`, `medium`, `high`, or `None`.

## Customize

This repo encodes one way of working. Fork it, or clone it, and change whatever does not match your style, your agents, or your providers: the worker prompts, the model tiers, the effort levels, which runtimes are included. Everything is generated from one file, so a change is one edit.

### Set up the clone

Run the installer from the clone as `./install.sh`. That is link mode (see [Install](#install)): the runtime files become symlinks into the clone, so edits and `git pull` take effect immediately without re-installing (Codex worker files are copied instead, because Codex rejects symlinked agent files; rerun `./install.sh` after rebuilding):

```bash
git clone https://github.com/NuttapongPun/orchestration-workflow.git
cd orchestration-workflow
./install.sh
```

`--copy` forces copy mode even from a clone. `--link` forces link mode and stops with an error when the script is not run as a file inside a clone.

If you forked it, clone your fork instead and change `REPO_SLUG` at the top of `install.sh` so the one-line installer points at your fork.

### Make a change

1. Edit the prompts, models, or effort levels in `build.py`. Every worker prompt is defined exactly once there.
2. Run `python3 build.py` to regenerate the files for every runtime.
3. Start a fresh session in the runtime to pick up the change. Commit when you are happy with it.

Changing a model for Claude Code or Codex is a one-line edit in the `MODELS` table; OpenCode's models live in `OPENCODE_STACKS`. Swapping OpenCode to another provider or price point needs no edit at all: re-run the installer with `--opencode-stack=<name>` (see the stacks above). Adding a runtime means a generator block in `build.py`, a binding file under `skills/orchestrate/references/` and a line in step 0 of the skill (both are generated, so add them in `build.py`), and a row in `install.sh`.

After changing the skill or its plan gate, run `python3 evals/run.py --dry-run` to validate the eval scenarios. A live run (Claude Code only) tests the *installed* skill and costs money; see [`evals/README.md`](evals/README.md).

## Runtime notes

- **Codex** custom agents need Codex 0.153 or newer. An agent file sets the model, reasoning effort, and instructions; Codex ignores any `sandbox_mode` or approval setting in it. Every worker inherits the session's sandbox and approval settings: in `workspace-write` (the default) any worker, `investigate` included, can write in the workspace; in a `read-only` session reviewers cannot run tests that write caches or build output; under `--yolo` or full access every worker has full access. Run orchestration sessions in `workspace-write`. Web search and shell network access are session settings too (see [Codex web search](#codex-web-search)).
- **OpenCode** review workers have full shell so tests and checks can run; only their edit tools are denied, so they can still write through the shell. `investigate` has its edit tools denied and a deny-by-default shell: an allowlist of read-only inspection commands (including `ls`, `cat`, `grep`, `rg`, `stat`, `which`, `command -v`, `git log`/`diff`/`show`/`status`, per-tool `--version` checks, and the read subcommands of `brew`, `mise`, and `uv`; the full list is `OC_READ_CMDS` in `build.py`), with commands that print the environment left off. On top of that, deny rules block flags and paths that write, run a chosen program, or expose secrets (output redirects, `find -exec`/`-delete`, `rg --pre`, `.env` paths, `/proc/*/environ`). The deny rules are best-effort: they match the command text before the shell expands it, and a redirect on a pipeline or group (`cat a | head > b`) is never checked, so `investigate` can still write a file that way; a determined or prompt-injected model can get past them, and a recursive `grep` or `rg` can still read `.env` contents. The comments above `OC_READ_CMDS` in `build.py` list the known gaps.
- **Claude Code** reads `~/.claude/skills`, not `~/.agents/skills` directly; the symlink handles that. Workers pin `model` and `effort` in frontmatter, and the skill still asks the orchestrator to set `model` explicitly on every dispatch.
- **OpenCode** 2.0 or newer is required: the agent files use its format (an ordered `permissions` rule list and `model: <provider/model>#<variant>`), which OpenCode 1 does not read. On macOS, `brew install anomalyco/tap/opencode-v2`; it conflicts with the v1 `opencode` formula, so uninstall that first.
- **OpenCode** is the only runtime with a real primary agent, so the orchestrator's "never edit" rule is enforced by permissions there. In Claude Code and Codex it is a prompt rule.
- **OpenCode's orchestrator dispatches every worker in the background** (`background: true` on the `subagent` tool), then ends its turn. You can keep talking to it while workers run; each result arrives as a message and the orchestrator picks the workflow up from there. New work that touches files a running worker writes waits for that worker.
- **OpenCode's default `free` stack needs no provider login.** Its agents reference OpenCode Zen's free models (`opencode/muse-spark-1.3-contributor-free`, `opencode/mimo-v2.6-flash-free`, `opencode/nemotron-3.5-lightning-free`). A probe on a machine whose `opencode auth list` held only OpenRouter and OpenAI credentials, with nothing for OpenCode Zen, answered normally:

  ```bash
  opencode run --model opencode/nemotron-3.5-lightning-free "Reply with exactly the word OK"
  # > build · nemotron-3.5-lightning-free
  # OK
  ```

  If your install does ask for a credential, run `opencode auth login` and pick OpenCode Zen. Free models are rate-limited and can be withdrawn; read the contributor-terms warning under "OpenCode model stacks" before pointing this stack at private code.
- **If you pick the `openai` stack, connect the OpenAI provider first.** Its orchestrator, `hard-worker`, and `review-hard` use `openai/gpt-6.1-sol#high`; the easy tier uses `openai/gpt-6-luna` (`#medium`, and `#low` for `investigate`). Link the provider once, either with a ChatGPT login or an API key:

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

Optional, for UI and code style. Workers load an installed skill when it matches the task, and the workflow works the same without any of these:

```bash
npx impeccable install   # Impeccable: run from a project root; it asks which agents, and project or global
```

- [frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design), Anthropic's, ships in the `example-skills` plugin. In Claude Code: `/plugin marketplace add anthropics/skills`, then `/plugin install example-skills@anthropic-agent-skills`.
- [Ponytail](https://github.com/DietrichGebert/ponytail) installs as a plugin. In Claude Code: `/plugin marketplace add DietrichGebert/ponytail`, then `/plugin install ponytail@ponytail`. In Codex: `codex plugin marketplace add DietrichGebert/ponytail`, then `codex plugin add ponytail@ponytail`, then trust its hooks in `/hooks`.
- [Impeccable](https://github.com/pbakaus/impeccable) documents its other install routes.

Workers read a project's `DESIGN.md` before UI work. To give agents your visual identity in a structured form, see Google's [DESIGN.md format](https://github.com/google-labs-code/design.md).

## Support

If this workflow saves you time, you can support its upkeep:

- [Ko-fi](https://ko-fi.com/nuttapongp)
- [Buy Me a Coffee](https://buymeacoffee.com/nuttapongp)

## License

MIT
