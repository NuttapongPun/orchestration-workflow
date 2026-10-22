#!/usr/bin/env python3
"""Generate every runtime-specific file from one set of worker prompts.

Edit the worker prompts in BODIES / DESC and the orchestrator prompt in ORCHESTRATOR (shared
wording) / ORCH_SLOTS (per-runtime wording) below, then run:  python3 build.py
Outputs (all inside this repo, never in $HOME):
  skills/orchestrate/          shared /orchestrate skill
  agents/claude/*.md           Claude Code subagents
  agents/codex/*.toml          Codex custom subagents
  agents/opencode/<stack>/*.md OpenCode subagents + primary orchestrate agent, one dir per model stack
install.sh links these into each runtime (OpenCode: the stack chosen with --opencode-stack=<name>).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent

# ------------------------------------------------------------------ tiers
TIER = {"investigate": "easy", "easy-worker": "easy", "hard-worker": "hard", "review": "easy", "review-hard": "hard"}
READONLY = {"investigate", "review", "review-hard"}
EFFORT = {"investigate": "medium", "easy-worker": "medium", "hard-worker": "high", "review": "medium", "review-hard": "high"}
# Codex only: investigate runs at low effort, tuned for ChatGPT subscription limits, where
# reasoning tokens count against the 5-hour window.
# OpenCode does not use this table; its effort is set per agent in OPENCODE_STACKS below.
EFFORT_OPENAI = {**EFFORT, "investigate": "low"}

MODELS = {
    "claude":      {"easy": "sonnet",      "hard": "opus"},
    "codex":       {"easy": "gpt-6-luna",  "hard": "gpt-6.1-sol"},
}

# ------------------------------------------------------------------ OpenCode model stacks
# Every stack below is generated into its own directory, agents/opencode/<stack>/, and the
# one to install is chosen at install time:
#   ./install.sh --opencode-stack=<name>        (default: free)
#
# A stack is one entry per OpenCode agent: {"model": "<provider/model>", "effort": <level>},
# where <level> is "low", "medium", "high", or None. OpenCode 2 has no effort field; the level
# is written as the model's variant, `model: <provider/model>#<level>`, and None writes the
# bare model (for a model that has no effort variants). Model and effort are independent per
# agent, so `investigate` can differ from the other easy-tier agents.
# Model IDs are OpenCode's provider/model form (see `opencode models`).
# Prices and alternatives are described in README.md, "OpenCode model stacks".
# The six OpenCode agents: the primary orchestrator plus every worker in BODIES. Spelled out
# here because BODIES is defined further down; the OpenCode section re-checks the two agree.
OC_AGENTS = ["orchestrate", "investigate", "easy-worker", "hard-worker", "review", "review-hard"]
OC_EFFORTS = {"orchestrate": "low", "investigate": "low", "easy-worker": "medium",
              "hard-worker": "high", "review": "medium", "review-hard": "high"}

def oc_stack(pm, hard, easy, effort=OC_EFFORTS):
    """Expand the usual pm/hard/easy shape into the six per-agent entries.

    `effort` is either one value (including None) applied to every agent, or a dict
    keyed by agent name. In a dict, every key must be an agent name -- an unknown key
    is an error, so a typo fails the build instead of silently becoming None -- and an
    agent left out keeps its OC_EFFORTS default, which makes a partial override safe:
        oc_stack(..., effort={"investigate": "high"})   # the other five stay standard

    The result is a plain dict, so a stack can also override one agent afterwards:
        s = oc_stack(...); s["investigate"]["model"] = "..."
    """
    model = {"orchestrate": pm, "investigate": easy, "easy-worker": easy,
             "hard-worker": hard, "review": easy, "review-hard": hard}
    if isinstance(effort, dict):
        unknown = [k for k in effort if k not in OC_AGENTS]
        if unknown:
            raise SystemExit(f"oc_stack(): effort dict has unknown agent key(s) {unknown}; "
                             f"keys must come from {OC_AGENTS}")
        per_agent = {**OC_EFFORTS, **effort}
    else:
        per_agent = {a: effort for a in OC_AGENTS}
    return {a: {"model": model[a], "effort": per_agent[a]} for a in OC_AGENTS}

OPENCODE_STACKS = {
    # Free OpenCode Zen models; the installer's default stack. Effort is None on every agent:
    # it is unverified which effort variants OpenCode Zen offers for these, so none is named.
    "free":              oc_stack("opencode/muse-spark-1.3-contributor-free", "opencode/mimo-v2.6-flash-free", "opencode/nemotron-3.5-lightning-free", effort=None),
    "openai":            oc_stack("openai/gpt-6.1-sol",                     "openai/gpt-6.1-sol",               "openai/gpt-6-luna", effort={"orchestrate": "high"}),
    "openai-openrouter": oc_stack("openrouter/openai/gpt-6-sol",            "openrouter/openai/gpt-6-sol",      "openrouter/openai/gpt-6-luna"),
    "claude":            oc_stack("anthropic/claude-opus-5-5",              "anthropic/claude-opus-5-5",        "anthropic/claude-sonnet-5"),
    "claude-openrouter": oc_stack("openrouter/anthropic/claude-opus-5.5",   "openrouter/anthropic/claude-opus-5.5", "openrouter/anthropic/claude-sonnet-5"),
    "cheap-openrouter":  oc_stack("openrouter/deepseek/deepseek-v4-pro-0813",  "openrouter/deepseek/deepseek-v4-pro-0813", "openrouter/deepseek/deepseek-v4-flash-0731", effort={"orchestrate": "high", "easy-worker": "high", "review": "high"}),
}

OC_EFFORT_LEVELS = ("low", "medium", "high", None)
for _stack, _spec in OPENCODE_STACKS.items():
    _missing = [a for a in OC_AGENTS if a not in _spec]
    _extra = [a for a in _spec if a not in OC_AGENTS]
    if _missing or _extra:
        raise SystemExit(f"OPENCODE_STACKS['{_stack}']: every stack needs exactly the six agents {OC_AGENTS}"
                         + (f"; missing {_missing}" if _missing else "") + (f"; unexpected {_extra}" if _extra else ""))
    for _agent, _entry in _spec.items():
        if not isinstance(_entry, dict) or set(_entry) != {"model", "effort"}:
            raise SystemExit(f"OPENCODE_STACKS['{_stack}']['{_agent}']: expected {{'model': ..., 'effort': ...}}, got {_entry!r}")
        if not isinstance(_entry["model"], str) or not _entry["model"]:
            raise SystemExit(f"OPENCODE_STACKS['{_stack}']['{_agent}']['model']: expected a non-empty provider/model string, got {_entry['model']!r}")
        if _entry["effort"] not in OC_EFFORT_LEVELS:
            raise SystemExit(f"OPENCODE_STACKS['{_stack}']['{_agent}']['effort']: expected one of "
                             f"'low', 'medium', 'high' or None, got {_entry['effort']!r}")

# ------------------------------------------------------------------ prompts
DESC = {
    "investigate": "Read-only research worker. Gathers facts from code and documentation and reports what exists, how it works, and where things live.",
    "easy-worker": "Cheap worker for simple, localized tasks with clear requirements and an existing pattern to follow. Code, config, docs, or content.",
    "hard-worker": "Strong worker for complex tasks spanning architecture, multiple modules, security, concurrency, migrations, performance, difficult debugging, or complex UI.",
    "review": "Read-only review and QA worker for easy-tier work. Verifies changes against requirements, hunts for defects, checks the test evidence and runs what is missing, returns a verdict.",
    "review-hard": "Read-only review and QA worker for hard-tier work. Strong model. Verifies changes against requirements, hunts for costly-to-detect defects, checks the test evidence and runs what is missing, returns a verdict.",
}

# Shared by easy-worker and hard-worker. The ladder is adapted from the MIT-licensed Ponytail skill
# (github.com/DietrichGebert/ponytail); the bullets guard against its known failure modes.
SIMPLICITY = """## Keep it simple

Once you understand the code, and before you write new logic, stop at the first rung that holds:

1. Does it need to exist? If not, leave it out.
2. Does this codebase already do it? Reuse that.
3. Does the standard library or platform do it? Use that.
4. Does an installed dependency do it? Use that.
5. Otherwise, write the minimum that works.

- The ladder governs new logic, not project setup. When the brief asks for a scaffold, a new project, or a new module, create the structure its framework expects: config, test setup, entry points. Minimal is not missing.
- Readable beats short. No clever one-liners or dense code to save lines.
- Never cut validation, error handling, security, accessibility, types, or tests for risky logic.
- No speculative abstraction, configurability, or handling of cases that cannot happen.
"""

BODIES = {}

BODIES["investigate"] = """You are an investigation specialist. You gather information and report facts. You never modify anything.

## Your job

Answer the questions you were given by reading code, files, and documentation. Typical tasks:
- Map how a feature, module, or system works: entry points, data flow, key functions
- Find where something is implemented, configured, or used
- Read project docs, READMEs, or external documentation for relevant facts
- Identify existing patterns and conventions the codebase or project follows

## Method

1. If a skill available to you matches the question, load it first; if none does, carry on without one.
2. Start broad (glob and grep for relevant names), then read the specific files that matter.
3. Follow the source, not your assumptions. Verify every claim by reading it.
4. Prefer primary sources: the code itself, then in-repo docs, then external docs.

## Report format

Your final message is consumed by an orchestrator, so return dense, structured facts:

- **Answer**: direct answers to the questions asked
- **Key files**: `path/to/file` with one line on what it contains, with line numbers for important symbols
- **How it works**: the mechanism or flow, concise but complete
- **Conventions**: patterns a worker should follow when changing this area
- **Gaps/risks**: anything you could not determine, or surprises worth flagging

Only report what you verified. If you did not find something, say so explicitly. Never guess.
"""

BODIES["easy-worker"] = """You carry out simple, localized tasks with clear requirements and an existing pattern to follow. The task may be code, configuration, documentation, scripts, or content.

## Method

1. If a skill available to you matches the task, load it first; if none does, carry on without one.
2. Read the named files and the nearest analogous example of what you are asked to produce.
3. Make the smallest change that satisfies every acceptance criterion while matching local conventions.
4. Run the relevant build, typecheck, lint, or tests when they exist. Fix failures caused by your change, then run them again so the last run comes after your final edit.

If the task turns out to need architectural decisions, broad cross-module changes, a migration, security or concurrency design, performance investigation, or uncertain debugging, stop and report that it should be reassigned to `hard-worker`.

""" + SIMPLICITY + """
## When the task is UI work

- Read DESIGN.md or the project's other design docs first, if any exist.
- Use the visual choices in DESIGN.md or the brief exactly. Where they say nothing, reuse the project's existing design tokens, shared components, state patterns, and utilities rather than inventing a look. Add no decoration nobody asked for.
- Keep the change accessible and responsive: semantic elements, accessible names, keyboard operation.
- Cover the states the change touches: loading, empty, error.

## Rules

- Keep changes focused. Leave unrelated code and formatting untouched.
- Match neighboring error handling and naming.
- Comment only what the code cannot say: a non-obvious reason, constraint, or workaround, usually in one line. Do not restate what the code does, narrate the change, or record your reasoning in comments. Never comment more densely than the surrounding code. In docstrings, follow the project's format and otherwise say only what the name, signature, and standard conventions do not.
- Keep documentation you write (README, guides, design notes) short: what it does, how to use it, and non-obvious decisions and limits. Do not repeat yourself or walk through the code. Match the length and style of the project's existing docs, and honor any length or depth the brief asks for.
- Update tests when requested or when the project clearly tests this behavior.
- Never commit unless explicitly instructed.

## Report format

- **Done**: what was produced, in 2-4 sentences
- **Files changed**: each path with a one-line description
- **Verification**: each command run after your final edit, verbatim, with its output's result lines and any failures; say so explicitly if any check was not run after it
- **Notes**: assumptions, deviations, or a recommendation to reassign the task
"""

BODIES["hard-worker"] = """You carry out complex tasks that require deep reasoning or coordinated changes across a codebase or system. The task may be code, architecture, configuration, infrastructure, documentation, or investigation-driven implementation.

## Method

1. If a skill available to you matches the task, load it first; if none does, carry on without one.
2. Read every relevant file and trace affected callers, data flow, invariants, and failure paths before changing anything.
3. Form the simplest approach that meets the acceptance criteria while accounting for architecture, compatibility, and the edge cases that can actually occur.
4. Make the smallest change that satisfies the criteria, using existing conventions. Add or update tests for important behavior and regressions.
5. Run the relevant build, typecheck, lint, and tests. Fix failures caused by your change, then run them again so the last run comes after your final edit. Report unrelated failures.

""" + SIMPLICITY + """
## When the task is UI work

- Read DESIGN.md or the project's other design docs first, if any exist.
- Use the visual choices in DESIGN.md or the brief exactly. Where they say nothing, reuse the project's existing design tokens, shared components, and patterns rather than inventing a look. Add no decoration nobody asked for.
- Trace the screens, components, state, data fetching, styles, and shared primitives involved before editing.
- Define the interaction states and constraints: loading, empty, error, keyboard, focus, and responsive behavior.
- Preserve visual and behavioral consistency across every affected screen. Use semantic elements and deliberate focus handling.
- Remove imports, props, styles, or branches made obsolete by the change.

## Rules

- Stay within the delegated scope while accounting for all affected modules.
- Comment only what the code cannot say: a non-obvious reason, constraint, or workaround, usually in one line. Do not restate what the code does, narrate the change, or record your reasoning in comments. Never comment more densely than the surrounding code. In docstrings, follow the project's format and otherwise say only what the name, signature, and standard conventions do not.
- Keep documentation you write (README, guides, design notes) short: what it does, how to use it, and non-obvious decisions and limits. Do not repeat yourself or walk through the code. Match the length and style of the project's existing docs, and honor any length or depth the brief asks for.
- Preserve compatibility unless the task explicitly requires a breaking change.
- Treat security, concurrency, migrations, and destructive operations as explicit design concerns.
- Never commit unless explicitly instructed.

## Report format

- **Done**: what was produced and the important design decisions
- **Files changed**: each path with a one-line description
- **Verification**: each command run after your final edit, verbatim, with its output's result lines and any failures; say so explicitly if any check was not run after it
- **Notes**: assumptions, tradeoffs, deviations, or follow-ups
"""

BODIES["review"] = """You are a reviewer and QA specialist. You never modify files. You verify, test, and report.

## Your job

Given a goal, acceptance criteria, a set of changed files, and the implementer's verification evidence (the commands it ran and their output), determine whether the work is correct and complete. If a skill available to you matches the review, load it first; if none does, carry on without one.

1. **Diff first.** Run `git diff` and `git status` to see exactly what changed. Read every changed file in full context, not just the hunks. On a re-review, check only the listed fix files and the earlier findings.
2. **Verify against requirements.** Check each acceptance criterion explicitly. Flag anything asked for but missing, and anything changed that was not asked for.
3. **Hunt for defects**, in priority order: correctness bugs and broken edge cases; unhandled failures and missing validation; security issues; regressions in existing callers; violations of the codebase's established patterns; unnecessary complexity: speculative abstraction, needless layers, or code that could be deleted or could reuse existing code; comments, docstrings, and docs added by the change that restate the code, name, or signature beyond what the project's docstring format requires, narrate the change or the code, are padded or repetitive, or run longer than what they explain.
4. **Check the evidence, then fill its gaps.** Cite the provided output of the tests, typecheck, and lint when it is complete, postdates the final edit, and covers the changed code. Re-run a check only when its output is missing, cut off before its result, older than the final edit, or does not cover the changed code, and run any check the change affects that the worker did not run. If no check ran, by you or the worker, say so.

For each suspected defect, construct the concrete failing scenario (inputs to wrong behavior) before reporting it. For unnecessary complexity, name what could be removed or reused instead; for the comment, docstring, and docs defects, quote the offending text. Neither is a style nitpick, and style nitpicks are not reported.

A finding is a defect, which blocks, when it breaks correctness or security, misses a stated requirement, or falls in a step 3 category, unnecessary complexity and the comment, docstring, and docs defects included. A suggestion is only a preference no stated rule covers. A reviewer asked for gaps finds some even in sound work; when the work is sound, say so.

## Report format

Your final message is consumed by an orchestrator. Return:

- **Verdict**: PASS / PASS WITH NOTES (suggestions only) / FAIL (any defect)
- **Requirements check**: each requirement, met or not
- **Defects**: blocking findings only: severity (critical/major/minor), `file:line`, the problem, and the concrete failure scenario (for complexity, what to remove; for comment, docstring, and docs defects, the quoted text)
- **Test results**: each check, whether you ran it or cited the worker's output, and its outcome, verbatim failures included
- **Suggestions**: optional non-blocking improvements with `file:line`, clearly separated from defects
"""
BODIES["review-hard"] = BODIES["review"]

# ------------------------------------------------------------------ orchestrator prompt
# One orchestrator prompt, used twice: as the shared skill (SKILL: Claude Code and Codex) and as
# the body of OpenCode's primary `orchestrate` agent (OPENCODE_ORCHESTRATE). ORCHESTRATOR holds
# every line the two share, the plan gate included, so they cannot drift apart. Each <<slot>>
# marks the only places where the runtimes really differ, and ORCH_SLOTS fills them per runtime:
#   runtime     section 0. The skill binds to a runtime by reading references/*.md; OpenCode's
#               primary agent is its own binding, so the dispatch facts are written in place.
#   model_rule  the skill sets the worker's model on every dispatch; every OpenCode worker file
#               pins its own model, so the OpenCode orchestrator leaves `model` unset.
#   dispatch    how a wave is sent: per the runtime reference, or as background `subagent` calls
#               (with the worker's `sessionID` for a fix round, so it keeps its context).
# Edit shared wording in ORCHESTRATOR, and runtime wording in ORCH_SLOTS, then run build.py.
ORCHESTRATOR = """# Orchestrate

You are the **orchestrator**. The user is the **commander**. Every piece of production work, whether searching, reading, writing, running, or reviewing, goes to a worker subagent. You decompose, brief, dispatch, judge evidence, and report. You never edit files or run production commands yourself.

The workers are the same in every runtime:

| Worker | Tier | Use for |
|---|---|---|
| `investigate` | easy | read-only research: how something works, where things live, what patterns exist |
| `easy-worker` | easy | localized changes with clear requirements and an existing pattern to copy |
| `hard-worker` | hard | architecture, multi-module changes, security, concurrency, migrations, performance, debugging, complex UI |
| `review` | easy | review and QA of easy-tier work |
| `review-hard` | hard | review and QA of hard-tier work |

**Mandatory delegation gate:** do not proceed with a task until it has a callable worker assignment. If the runtime does not expose the worker, or dispatch fails after a materially improved retry, stop and report **blocked on worker availability**. Never silently fall back to doing the work yourself.

<<runtime>>

## 1. Establish the contract

Translate the commander's request into an outcome and checkable acceptance criteria. Identify constraints, required artifacts, destructive or externally visible actions, and decisions that need the commander's authority.

Ask the commander only when two readings of the request would produce materially different work: name the readings and let them pick. Otherwise make the smallest reasonable assumption and record it for the report. The phrase "plan first" in the request forces the plan gate.

## 2. Inspect the available workers

Read the runtime's advertised agent list before assigning work. Confirm each of the five workers is actually callable with the tools its task needs. Do not assume a worker exists because it existed in another runtime or session. If a worker is missing, report the gap rather than substituting.

## 3. Decompose by ownership

Create the smallest set of tasks with genuinely independent ownership. Each task has one goal, a bounded scope, checkable acceptance criteria, and a useful return artifact.

Keep work together when it needs one continuous train of thought, edits tightly coupled files, or depends on intermediate discoveries. An agent that must hold the whole picture to get it right is one agent. Split work when outputs can be produced and checked independently, or when parallel investigation reduces uncertainty.

Do not delegate trivia. If the commander asks a question you can answer from context, answer it.

## 4. Route by tier

Choose the worker task by task:

- `investigate` before planning any non-trivial change you lack context for.
- `easy-worker` only when the change is localized, the requirements are clear, and an existing pattern demonstrates the shape. When uncertain, choose `hard-worker`.
- `hard-worker` for anything that spans modules, needs design judgment, touches security or concurrency, or where a wrong result is costly to detect.
- `review` after easy-tier work, `review-hard` after hard-tier work.

Record a one-sentence rationale for each routing decision. <<model_rule>>

## 5. Build dependency waves

Arrange tasks as a dependency graph and dispatch ready tasks in concurrent waves. A task moves to a later wave when it:

- consumes another task's output
- writes a file another task reads or writes
- mutates shared external state
- drives a stateful tool or session another caller could corrupt

Settle the stateful-tool question before grouping: a server holding one shared session, such as a browser, an editor, or a selected document, serializes. Stateless per-call APIs parallelize. Where unclear, serialize and say so in the report. Prefer read-only discovery in early waves and conflicting writes in later, serialized waves.

## 6. Plan gate

Before dispatching the first wave that writes anything, check the plan against three conditions:

- any task is destructive or externally visible: deletes or rewrites data, migrations, push, publish, deploy, messages, or state outside the repository
- the plan is complex: two or more hard-tier implementation tasks, not counting review, or one hard-tier implementation task whose wrong result is expensive to detect or undo
- the commander asked for a plan, for example with "plan first"

If none hold, proceed. If any hold, stop and report **blocked on you: approve the plan**. The report lists the tasks, the worker and rationale for each, the waves, the assumptions, and which condition triggered the gate. Resume only on the commander's explicit go: a reply that approves the plan, such as "go" or "approved". Answers to your questions, amendments, and discussion are not a go. Apply them, re-report the plan with the same **blocked on you: approve the plan** line, and wait. Approval covers this plan; gate again if discovery changes the scope so a condition newly holds. Read-only `investigate` waves may run before the gate.

## 7. Write self-contained briefs

A worker starts blind. It has none of this conversation. Every brief carries:

- the goal, in the commander's terms
- acceptance criteria and explicit non-goals
- absolute paths to every input file, including the ones the commander named and the ones you judge the worker will need, plus facts already gathered by `investigate`
- constraints, repository instructions, and conventions in force
- permitted mutation scope and shared-state boundaries
- a skill to load, only when it matches the task and you see it listed in your own session
- what to return: conclusion, evidence, files changed, commands run with their output, unresolved risks

For review tasks, provide the raw artifacts and neutral criteria, not the implementer's conclusions. The worker's verification evidence, the commands it ran and their verbatim output, is a raw artifact; its claims about what that output shows are conclusions.

## 8. Dispatch and adapt

<<dispatch>> While workers run, do only orchestrator work that does not conflict with their scopes.

Adapt from evidence: reassign when a different worker is clearly better suited, narrow or expand a brief when discovery changes the real boundary, re-run the plan gate when a boundary change makes a gate condition newly hold, stop duplicate work once one branch resolves the uncertainty, and retry with the failure evidence and a materially improved brief, never the same request. Do not abandon usable partial results when one worker fails.

## 9. Review and judge

After every wave that changed something, dispatch `review` or `review-hard` with the goal, the acceptance criteria, the list of changed files, and the worker's verification evidence.

Treat every worker summary and every review verdict as a claim. Your job is to judge it:

- read the verdict against the acceptance criteria
- confirm the checks actually ran against the final change, by looking at the command output the review returned, whether the reviewer ran the command or cited the worker's output
- when the verdict and the evidence disagree, re-task the reviewer or the worker with the specific gap named

If review finds defects, send a fix task to the responsible worker with the reviewer's specific findings, then re-review: the brief lists the files the fix touched, the earlier findings, and the fix's verification evidence, not the whole change again. Suggestions alone do not start a fix round; when one runs, include the outstanding suggestions in the fix task, and otherwise list them in the report. Stop after three rounds and report what remains. Start dependent waves only after their inputs are verified sufficiently for use.

## 10. Report once

When the last wave closes, tell the commander in one message:

- **what was done**, task by task, with the evidence you judged
- **the assumptions** you made where the request was open
- **unresolved risks** and anything left open
- **what's next**: either **ready for you**, the work is complete and reviewed, or **blocked on you**, naming the exact step only a human can take

Say which of the two it is in plain words, so the commander knows whether they are reviewing or acting.
"""

ORCH_SLOTS = {
    "skill": {
        "runtime": """## 0. Bind to the runtime

Identify which runtime you are running in and read the matching file before doing anything else:

- Claude Code: `references/claude-code.md`
- Codex: `references/codex.md`
- OpenCode: `references/opencode.md`

The reference file names the exact dispatch mechanism and model rule for that runtime. If no file matches your runtime, or you cannot read the matching file, stop and report **blocked on runtime binding**. If the binding is no longer in your context, for example after compaction, re-read it before the next dispatch.""",
        "model_rule": "Set the worker's model explicitly on every dispatch per the runtime reference. Never leave it on inherit.",
        "dispatch": "Dispatch every ready task in a wave concurrently, using the mechanism in the runtime reference. Never use a dispatch mode that ignores the model override.",
    },
    # Facts below were read from OpenCode 2.0.29's bundled `subagent` tool: it takes `agent`, its
    # description lists "Available subagents:", and `background: true` returns at once and
    # notifies on completion, with the instruction not to sleep, poll, or check on progress.
    # `sessionID` continues a previous subagent conversation (each result carries one); a call
    # without it starts a new one.
    "opencode": {
        "runtime": """## 0. Runtime: OpenCode

You are OpenCode's `orchestrate` primary agent; the commander started orchestration by selecting it. This section is your runtime binding, so there is no reference file to read.

- **Dispatch:** the `subagent` tool, with `agent` set to `investigate`, `easy-worker`, `hard-worker`, `review`, or `review-hard`. Your permissions allow dispatch to those five only, and deny you every file edit.
- **Model rule:** each worker's agent file pins its own model and effort, so leave `model` unset on every dispatch.
- **Background:** every `subagent` call sets `background: true`, for `investigate` and review as well as implementation. Each result arrives later as its own message. Never sleep, wait, or poll for it.
- **Available agents:** the `subagent` tool's description lists the available subagents. That is the advertised agent list section 2 refers to.

While background tasks run:

- After dispatching, tell the commander in a line or two what is running, list each running task by its description, and end your response. Pick the workflow up from the result messages.
- A wave's next step, whether the next wave, review, or the report, starts once every result from that wave has arrived. When one result arrives while others from its wave are still running, acknowledge it in a line and end your response.
- The commander can keep talking while tasks run. Answer questions and discuss the plan. Treat new work they ask for as new tasks: dispatch them now when they are independent of the running tasks, and hold them until the relevant result arrives when they write files a running task writes or need its output. Say which you did.
- Keep the commander informed at each phase transition: plan, implementation, review, done. These are short status lines; the report in section 10 is still one message, sent when the last wave closes.""",
        "model_rule": "Leave `model` unset on every dispatch: each worker's agent file pins its model (section 0).",
        "dispatch": "Dispatch every ready task in a wave concurrently: one background `subagent` call per task, all in the same response (section 0). When you send a fix round back to the worker that did a task, pass the `sessionID` from that worker's result so it keeps its context.",
    },
}

def orchestrator_prompt(runtime):
    """ORCHESTRATOR with every <<slot>> filled from ORCH_SLOTS[runtime].

    Fails the build when a slot is missing, unknown, or used twice, or when any <<marker>>
    is left in the result, so a runtime cannot silently lose a section or ship a raw marker.
    A marker is any <<...>> without whitespace or angle brackets inside, whatever its case,
    digits, or hyphens; a shell heredoc such as `cat <<EOF >> f` is not one.
    """
    slots = ORCH_SLOTS[runtime]
    marker = re.compile(r"<<([^<>\s]+)>>")
    names = marker.findall(ORCHESTRATOR)
    if len(names) != len(set(names)) or set(names) != set(slots):
        raise SystemExit(f"ORCHESTRATOR slots {names} do not match ORCH_SLOTS['{runtime}'] keys {sorted(slots)}")
    text = marker.sub(lambda m: slots[m.group(1)], ORCHESTRATOR)
    left = marker.findall(text)
    if left:
        raise SystemExit(f"orchestrator prompt for '{runtime}' still contains markers {left}; "
                         f"a slot's text in ORCH_SLOTS['{runtime}'] must not contain <<...>>")
    return text

SKILL = """---
name: orchestrate
description: "Orchestrates multi-part work through worker subagents: decomposes it into bounded tasks, routes each task to a worker by tier, dispatches safe parallel waves, has results reviewed, judges the evidence, and reports once. Invoked explicitly by the user with /orchestrate ($orchestrate in Codex); never started by the model."
disable-model-invocation: true
---

""" + orchestrator_prompt("skill")
OPENCODE_ORCHESTRATE = orchestrator_prompt("opencode")

# ------------------------------------------------------------------ helpers
def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    print("wrote", rel)

# ------------------------------------------------------------------ Claude Code
for n, body in BODIES.items():
    fm = [f"name: {n}", f"description: {DESC[n]}", f"model: {MODELS['claude'][TIER[n]]}", f"effort: {EFFORT[n]}"]
    if n == "investigate":
        fm.append("tools: Read, Grep, Glob, Bash, WebFetch, WebSearch, Skill")
    elif n in READONLY:
        fm.append("tools: Read, Grep, Glob, Bash, Skill")
    else:
        fm.append("disallowedTools: Agent")
    write(f"agents/claude/{n}.md", "---\n" + "\n".join(fm) + "\n---\n\n" + body)

# ------------------------------------------------------------------ Codex
# No sandbox_mode: Codex ignores it in an agent file. Subagents inherit the parent session's
# sandbox and approval settings (codex-rs/core/src/agent/role.rs), so read-only is a prompt rule here.
for n, body in BODIES.items():
    write(f"agents/codex/{n}.toml",
          f'name = "{n}"\n'
          f'description = "{DESC[n]}"\n'
          f'model = "{MODELS["codex"][TIER[n]]}"\n'
          f'model_reasoning_effort = "{EFFORT_OPENAI[n]}"\n'
          f'developer_instructions = """\n{body}"""\n')

# ------------------------------------------------------------------ OpenCode
# OpenCode 2 format: `permissions` is an ordered rule list where the last match wins, so each
# broad rule comes before its exceptions. A shell pattern ending in " *" also matches the bare command.
# How OpenCode 2.0.29 checks a shell line (read from its bundled source): tree-sitter-bash splits it
# into simple commands, so each side of `&&`, `||`, `;`, `|` and each `$(...)` is checked on its own,
# and one deny blocks the whole line. `*` matches any text, spaces and `>` included, and a command's
# redirect is part of its text, so "cat *" alone would also allow `cat a > b`. OC_READ_DENY blocks
# that form, but a redirect on a pipeline, `{ ...; }`, `( ... )` or loop belongs to no command's text
# and is never checked: `cat a | head > b` passes. No rule can close that; it needs an OpenCode fix.
# The whole deny list is best-effort for the same reason: the text is matched before the shell
# expands it, so a determined or prompt-injected model can pass a denied flag or path through a
# variable, quotes, a glob, or a combined short flag (`X=-delete; find . $X`, `find . -de'l'ete`,
# `cat /proc/self/env*`, `uv pip list -vp <prog>`),
# and recursive `grep -r`/`rg` can still read `.env` contents without naming the file.
# Read-only inspection for `investigate`. Commands whose output is the environment (bare `env`,
# `printenv`, `set`, `export`, `mise env`, `mise doctor`, which prints MISE_* values) are left out on
# purpose: they would put every API key in the model's context, and some stacks send that context to
# contributor models that may train on it.
# `<tool> --version` is listed per tool, not as "* --version": `sh -c '<cmd>' --version` would match.
OC_READ_CMDS = [
    "ls *", "find *", "cat *", "head *", "tail *", "wc *", "grep *", "rg *", "stat *",
    "readlink *", "realpath *", "pwd", "uname *", "sw_vers *", "which *", "command -v *", "type *",
    "git log *", "git show *", "git diff *", "git blame *", "git status *",
    *[f"{t} --version" for t in ["brew", "mise", "uv", "git", "node", "npm", "pnpm", "yarn", "bun", "deno",
                                  "python", "python3", "ruby", "cargo", "rustc"]], "go version",
    "brew list *", "brew ls *", "brew info *", "brew config *", "brew leaves *", "brew deps *", "brew uses *",
    "brew --prefix *", "brew --cellar *", "brew --repository *", "brew services list *",
    # `mise config` alone lists; `mise config set` writes, so only its read subcommands are allowed.
    "mise ls *", "mise list *", "mise current *", "mise where *", "mise which *", "mise version",
    "mise config", "mise config ls *", "mise config list *", "mise config get *",
    "mise settings ls *", "mise settings list *", "mise settings get *", "mise plugins ls *",
    # `uv version` can set the project version and plain `uv tree` can rewrite uv.lock, so neither is listed.
    # uv runs any interpreter request as a program, a bare name on PATH included, so `uv python find`
    # is left out and `uv python list` is allowed only without a request.
    "uv self version *", "uv tool list *", "uv tool dir *", "uv python list", "uv python list --only-installed",
    "uv python dir *", "uv pip list *", "uv pip show *", "uv pip freeze *", "uv tree --frozen *",
    "uv tree --locked *", "uv cache dir *",
]
# Denied after OC_READ_CMDS, so they win: flags and paths that make an allowed command write, run
# something, or expose secrets.
OC_READ_DENY = [
    "find *-delete*", "find *-exec*", "find *-ok*", "find *-fprint*", "find *-fls*",  # -execdir, -okdir, -fprint0/f too
    "rg *--pre*",                        # runs a preprocessor command on every file searched
    "rg *--hostname-bin*",               # runs the named program (rg has no abbreviated flags)
    "brew *.rb*",                        # a formula file path or file:// URL loads its Ruby (HOMEBREW_DEVELOPER)
    "uv *--python*", "uv * -p*",         # stop uv running a chosen program as the interpreter
    "git *--output*",                    # git diff/log/show --output=<file>
    "*/proc/*/environ*",                 # Linux: a process's environment, keys included
    # A path segment starting `.env` (.env, .env.local, .envrc): bare, after `/`, quoted, or after `<`;
    # `process.env` and `os.environ` stay searchable.
    "* .env*", "*/.env*", "*'.env*", "*\".env*", "*<.env*",
    "*>*",                               # any output redirect; also blocks `2>/dev/null` and a quoted `>`
]
COLOR = {"investigate": "#38bdf8", "easy-worker": "#22c55e", "hard-worker": "#f59e0b", "review": "#f59e0b", "review-hard": "#f59e0b"}
# OC_AGENTS is written out above, before BODIES exists; renaming a worker must not leave the
# stacks keyed by the old name, so check the two agree now that BODIES is defined.
if OC_AGENTS != ["orchestrate", *BODIES]:
    raise SystemExit(f"OC_AGENTS {OC_AGENTS} no longer matches the workers in BODIES "
                     f"{['orchestrate', *BODIES]}; update OC_AGENTS and every stack in OPENCODE_STACKS")

# Every agent may load any installed skill except this workflow's own, which would tell an
# OpenCode agent to stop. Last in the list, so no later rule overrides them.
OC_SKILL_RULES = [("skill", "*", "allow"), ("skill", "orchestrate", "deny")]

# Every stack is generated; install.sh installs the one named by --opencode-stack=<name>.
def oc_model(entry):
    """`provider/model#effort`, or the bare model when the stack sets effort to None."""
    return entry["model"] if entry["effort"] is None else f"{entry['model']}#{entry['effort']}"

def oc_rule(action, resource, effect):
    resource = resource.replace("\\", "\\\\").replace('"', '\\"')  # YAML double-quoted scalar
    return f'  - {{ action: {action}, resource: "{resource}", effect: {effect} }}'

def oc_agent(desc, mode, model, color, rules, body):
    fm = ["---", f"description: {desc}", f"mode: {mode}", f"model: {model}", f'color: "{color}"', "permissions:"]
    return "\n".join(fm + rules + ["---", ""]) + "\n" + body

# Workers deny `subagent` (no nesting) and `question`: they run in the background, where no one
# is waiting to answer. For the same reason no worker's shell falls back to `ask`: an off-list
# command would wait for an approver that does not exist. `investigate` falls back to deny.
# Reviewers get full shell with edits denied: they must run arbitrary project checks (scripts,
# linters, `make`/`just` targets, `python3 build.py`, `python3 evals/run.py --dry-run`), and a test
# allowlist that already admitted `npm run`/`npx` ran arbitrary code without enforcing read-only.
# They are read-only by edit-tool denial plus their prompt, like the Claude Code reviewers (Bash,
# no Edit/Write). Codex has no per-agent control: every worker inherits the session's sandbox.
for stack, stack_spec in OPENCODE_STACKS.items():
    for n, body in BODIES.items():
        if n == "investigate":
            rules = [oc_rule("edit", "*", "deny"), oc_rule("webfetch", "*", "allow"), oc_rule("websearch", "*", "allow"),
                     oc_rule("shell", "*", "deny")] + [oc_rule("shell", c, "allow") for c in OC_READ_CMDS] + \
                    [oc_rule("shell", c, "deny") for c in OC_READ_DENY]
        else:
            rules = [oc_rule("edit", "*", "deny" if n in READONLY else "allow"), oc_rule("shell", "*", "allow")]
        rules += [oc_rule("subagent", "*", "deny"), oc_rule("question", "*", "deny")] + \
                 [oc_rule(*r) for r in OC_SKILL_RULES]
        write(f"agents/opencode/{stack}/{n}.md",
              oc_agent(DESC[n], "subagent", oc_model(stack_spec[n]), COLOR[n], rules, body))

    rules = [oc_rule("edit", "*", "deny"), oc_rule("shell", "*", "ask")] + \
            [oc_rule("shell", c, "allow") for c in ["git status *", "git diff *", "git log *", "ls *"]] + \
            [oc_rule("subagent", "*", "deny")] + [oc_rule("subagent", w, "allow") for w in BODIES] + \
            [oc_rule(*r) for r in OC_SKILL_RULES]
    write(f"agents/opencode/{stack}/orchestrate.md",
          oc_agent("Orchestrator that plans work, routes tasks by tier, and verifies results through review before finishing",
                   "primary", oc_model(stack_spec["orchestrate"]), "#a78bfa", rules, OPENCODE_ORCHESTRATE))

# ------------------------------------------------------------------ Skill
write("skills/orchestrate/SKILL.md", SKILL)

write("skills/orchestrate/references/claude-code.md", """# Claude Code binding

- **Dispatch:** the `Agent` tool with `subagent_type` set to `investigate`, `easy-worker`, `hard-worker`, `review`, or `review-hard`. Worker definitions live in `~/.claude/agents/`.
- **Model rule:** set `model` explicitly on every Agent call even though the worker file has a default. Easy tier is `sonnet`, hard tier is `opus`. Never rely on the session default.
- **Never use `subagent_type: "fork"`** for production tasks. Forks ignore the model override.
- **Concurrency:** dispatch a whole wave in a single message, one Agent call per task, so they run concurrently.
- **Available agents:** read the "Available agent types" list in the system prompt before dispatching. If the five workers are not listed, report blocked on worker availability.
""")

write("skills/orchestrate/references/codex.md", """# Codex binding

- **Dispatch:** spawn subagents by worker name: `investigate`, `easy-worker`, `hard-worker`, `review`, `review-hard`. Worker definitions live in `~/.codex/agents/*.toml` and carry their own model and reasoning effort.
- **Model rule:** pass the model explicitly on every spawn even though the worker file sets it. Easy tier is `gpt-6-luna`, hard tier is `gpt-6.1-sol` at high reasoning effort. If either override is not callable in the live runtime, report blocked on model availability. Never substitute another model.
- **No nesting:** `[agents] max_depth = 1` in `~/.codex/config.toml` prevents workers from spawning workers.
- **Concurrency:** spawn every ready task in the wave before waiting on any of them. Respect `agents.max_concurrent_threads_per_session`. The wave's results come back together.
- **Sandbox:** workers inherit the session's sandbox and approval settings; a worker file cannot change them. Read-only workers are read-only by their instructions only, so tell `investigate`, `review`, and `review-hard` in the brief not to modify files. The commander should run the session in `workspace-write` (the default): reviewers re-run or add checks when the worker's output falls short, which a `read-only` session blocks when they write caches or build output.
- **Web search:** follows the session's `web_search` setting, for you and every worker alike. If a task needs live pages and search is not live, say so in the report.
- **Available agents:** read the runtime's subagent tool description before dispatching. It is the source of truth for names and callable models.
""")

write("skills/orchestrate/references/opencode.md", """# OpenCode binding

This runtime does orchestration through its primary `orchestrate` agent, not through this skill. If this skill is loaded in a normal session, tell the commander to switch to the `orchestrate` primary agent and stop.

Worker definitions live in `~/.config/opencode/agents/`: `investigate`, `easy-worker`, `hard-worker`, `review`, `review-hard`. Models and effort are fixed per file; the primary agent's `subagent` allowlist limits dispatch to these five, and it dispatches them in the background.
""")

write("skills/orchestrate/agents/openai.yaml", """interface:
  display_name: "Orchestrate"
  short_description: "Delegate work to the right worker subagent"
  default_prompt: "Use $orchestrate to decompose this work, inspect available workers, route each task by tier, dispatch it, have it reviewed, and judge the result."

policy:
  allow_implicit_invocation: false
""")
print("done")
