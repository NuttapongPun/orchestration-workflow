# orchestration-workflow

One orchestration workflow for four coding agents: **Claude Code**, **Codex**, **Antigravity CLI (`agy`)**, and **OpenCode**.

The idea: the frontier model you are talking to acts as a **PM**, not a worker. It decomposes the job, briefs cheaper worker subagents, has the result reviewed, judges the evidence, and reports once. Hard tasks go to a strong worker, easy tasks to a cheap one. The PM's context stays small because the workers hold the files, search results, and command output.

## What is in here

```
build.py                 single source of truth: worker prompts + tier table -> generates everything below
skills/orchestrate/      the shared /orchestrate skill (method) + one short binding file per runtime
agents/claude/           worker subagents for Claude Code      (~/.claude/agents/*.md)
agents/codex/            worker subagents for Codex            (~/.codex/agents/*.toml)
agents/antigravity/      worker subagents for Antigravity CLI  (~/.gemini/config/agents/*.md)
agents/opencode/         worker subagents + primary orchestrate agent for OpenCode (~/.config/opencode/agents/*.md)
install.sh               symlinks all of the above into the runtimes present on this machine
```

The same five workers exist in every runtime, with the same prompts:

| Worker | Tier | Claude | Codex | Antigravity | OpenCode |
|---|---|---|---|---|---|
| `investigate` | easy, read-only | sonnet | gpt-5.6-luna | flash | luna |
| `easy-worker` | easy | sonnet | gpt-5.6-luna | flash | luna |
| `hard-worker` | hard | opus | gpt-5.6-terra | pro | terra |
| `review` | easy, read-only | sonnet | gpt-5.6-luna | flash | luna |
| `review-hard` | hard, read-only | opus | gpt-5.6-terra | pro | terra |

Nesting is disabled everywhere (workers cannot spawn workers): Claude workers lack the `Agent` tool, Codex gets `[agents] max_depth = 1`, Antigravity workers' tool lists exclude `invoke_subagent`, OpenCode workers have `task: deny`.

## Install on a new machine

```bash
git clone https://github.com/NuttapongPun/orchestration-workflow.git ~/Documents/coding/orchestration-workflow
cd ~/Documents/coding/orchestration-workflow
./install.sh
```

`install.sh` detects which runtimes are installed and links the files into place. It is idempotent: re-run it after `git pull`. `./install.sh --uninstall` removes the links.

Then start a **fresh** session in each runtime:

- **Claude Code / Codex / Antigravity:** run `/orchestrate`. It is user-invoked only; the model will not trigger it on its own.
- **OpenCode:** select the `orchestrate` primary agent. The skill is not needed there.

### Skill-only install via the `skills` CLI

If you only want the skill (no worker agents), the usual flow works:

```bash
npx skills add NuttapongPun/orchestration-workflow --global
```

The skill will then report *blocked on worker availability* until the worker agents exist, so on a machine you actually work on, use `install.sh`.

Do not mix the two on one machine: `install.sh` makes `~/.agents/skills/orchestrate` a symlink into this repo, while the `skills` CLI writes a copy there. Pick one.

## Other skills I use

Everything else comes from public repos through the [`skills` CLI](https://skills.sh), which installs into `~/.agents/skills/` and links each skill into every agent it detects. On a new machine, after `install.sh`:

```bash
npx skills add mattpocock/skills --global --all
npx skills add vercel-labs/skills --global --skill find-skills
npx skills add microsoft/playwright-cli --global
npx skills add CoplayDev/unity-mcp --global --skill unity-mcp-orchestrator
npx skills add kepano/obsidian-skills --global --skill defuddle
```

| Source | Skills |
|---|---|
| `mattpocock/skills` | ask-matt, code-review, codebase-design, diagnosing-bugs, domain-modeling, grill-me, grill-with-docs, grilling, handoff, implement, improve-codebase-architecture, prototype, research, resolving-merge-conflicts, setup-matt-pocock-skills, tdd, teach, to-questionnaire, to-spec, to-tickets, triage, wait-what, wayfinder, wizard, writing-for-agents |
| `vercel-labs/skills` | find-skills |
| `microsoft/playwright-cli` | playwright-cli |
| `CoplayDev/unity-mcp` | unity-mcp-orchestrator (the Unity MCP package's own sync button writes a duplicate copy named `unity-mcp-skill`; use one or the other) |
| `kepano/obsidian-skills` | defuddle |

`npx skills update` refreshes all of them. `~/.agents/.skill-lock.json` records the exact source and commit of each one.

Two things the `skills` CLI gets wrong for this setup, which `install.sh` covers: it does not link into Antigravity's real skills folder (`~/.gemini/config/skills/`), and `npx skills list` misreports the agents for `orchestrate` because it is a symlink into this repo. The runtimes load it fine.

## Customize

1. Edit the prompts, models, or effort levels in `build.py`.
2. Run `python3 build.py` to regenerate every runtime file.
3. Commit and push. On other machines, `git pull` (files are symlinked, so nothing else to do).

Changing a model for one runtime is a one-line edit in the `MODELS` table. Adding a runtime means adding a generator block in `build.py`, a binding file under `skills/orchestrate/references/`, and a row in `install.sh`.

## Runtime notes and gotchas

- **Antigravity CLI** reads global skills only from `~/.gemini/config/skills/`, not from `~/.agents/skills/` and not from the folders the `skills` CLI targets. `install.sh` creates the correct link. `agy agent` lists only primary agents, so the workers will not show there even though `invoke_subagent` can call them. Start the orchestrator session as Gemini 3.1 Pro; `--agent` is ignored when resuming a conversation.
- **Codex** custom agents need Codex 0.153 or newer. The review workers use the `workspace-write` sandbox so tests can run; only `investigate` is sandbox read-only.
- **Claude Code** reads `~/.claude/skills`, not `~/.agents/skills` directly; the symlink handles that. Workers pin `model` and `effort` in frontmatter; the skill still asks the PM to set `model` explicitly on every dispatch.
- **OpenCode** is the one runtime with a real primary agent, so the PM's "never edit" rule is enforced by permissions there. In the other three it is a prompt rule.
- Reviewers run at the tier of the work they review. The PM's non-delegable job is to judge the verdict and confirm the tests actually ran.

## License

MIT
