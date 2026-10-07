#!/usr/bin/env python3
"""Behavioral evaluations for the orchestrate skill.

Each scenario in evals/scenarios/*.json runs in a fresh throwaway copy of a
fixture under the system temp dir, never in this repo. Claude Code runs are
automated: the runner drives `claude -p` headless, parses the stream-json
events, checks the scenario's assertions, and prints a pass/fail table.
Codex, Antigravity CLI and OpenCode are manual: the runner prepares the
fixture and prints the exact command to run. See evals/README.md.

    python3 evals/run.py --dry-run                      # validate scenarios, print commands; no session
    python3 evals/run.py --scenario 01 --model sonnet   # one live run
    python3 evals/run.py --model opus                   # the whole suite (costs money)
    python3 evals/run.py --baseline --model sonnet      # same queries, skill not invoked

Python 3 standard library only.
"""
import argparse
import datetime
import filecmp
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

EVALS = Path(__file__).resolve().parent
REPO = EVALS.parent
HOME = Path.home().resolve()

WORKERS = ["investigate", "easy-worker", "hard-worker", "review", "review-hard"]
TIER = {"investigate": "easy", "easy-worker": "easy", "hard-worker": "hard",
        "review": "easy", "review-hard": "hard"}
# Claude Code binding (skills/orchestrate/references/claude-code.md): easy tier sonnet, hard tier opus.
CLAUDE_TIER_MODEL = {"easy": "sonnet", "hard": "opus"}

# Built-in tools the session gets. No tool that runs commands or code, and no web tool,
# so no process in a run can execute a shell command. Workers keep Read/Grep/Glob/Edit/Write.
CLAUDE_TOOLS = ["Agent", "Read", "Grep", "Glob", "Edit", "Write", "NotebookEdit"]
# Appended to every subagent's system prompt, so workers do not promise command output they
# cannot produce (seen live: reviewers and investigate tried to "run" git and python).
SUBAGENT_NOTE = ("This environment has no shell: report verification by inspection and say which "
                 "commands you could not run.")
# Deny rules on top, in case a worker definition or a future default re-adds them.
CLAUDE_DENY = ["Bash", "WebFetch", "WebSearch", "mcp__*"]

# Applied to every turn of every scenario unless the scenario overrides the key.
DEFAULT_ASSERT = {
    # The orchestrator itself never edits or runs commands (SKILL.md: "You never edit files
    # or run production commands yourself"). Checked on top-level tool calls only.
    "forbidden_tools": ["Edit", "Write", "NotebookEdit", "MultiEdit", "Bash"],
    # Only the five workers; this also catches subagent_type "fork" and a general-purpose fallback.
    "allowed_subagent_types": list(WORKERS),
    # Every dispatch sets `model` explicitly, to the worker's tier model.
    "model_set": True,
}

ASSERT_SPEC = {  # key -> expected JSON type
    "no_dispatch": bool,
    "dispatches": list,
    "dispatches_in_order": list,
    "only_dispatch": list,
    "not_dispatched": list,
    "model_set": bool,
    "allowed_subagent_types": list,
    "forbidden_tools": list,
    "final_text_regex": list,
    "final_text_not_regex": list,
    "fixture_unchanged": bool,
    "fixture_file_regex": dict,
}
SCENARIO_KEYS = {"description", "skills", "query", "files", "expected_behavior", "assert",
                 "followups", "limits", "runtime"}
FOLLOWUP_KEYS = {"query", "expected_behavior", "assert"}
LIMIT_KEYS = {"max_turns": int, "budget_usd": (int, float), "timeout_s": int}
DEFAULT_LIMITS = {"max_turns": 20, "budget_usd": 2.0, "timeout_s": 900}

# Failures that are final even when the run stopped early (budget, max turns, timeout).
SAFETY_CHECKS = {"forbidden_tools", "allowed_subagent_types", "not_dispatched", "only_dispatch",
                 "no_dispatch", "fixture_unchanged"}

RUNTIMES = {
    "claude-code": {"automated": True, "skill_link": HOME / ".claude/skills/orchestrate", "prefix": "/orchestrate "},
    "codex": {"automated": False, "skill_link": HOME / ".codex/skills/orchestrate", "prefix": "$orchestrate "},
    "antigravity": {"automated": False, "skill_link": HOME / ".gemini/config/skills/orchestrate", "prefix": "/orchestrate "},
    "opencode": {"automated": False, "skill_link": None, "prefix": ""},
}

# Variables a parent Claude Code session sets for its own children. A nested `claude`
# must not inherit them, or it may attach to the parent session.
PARENT_SESSION_ENV = ["CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_CODE_ENTRYPOINT",
                      "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_SESSION_ATTENDED",
                      "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_MESSAGING_SOCKET",
                      "CLAUDE_CODE_MESSAGING_TOKEN"]


class ScenarioError(Exception):
    pass


# ------------------------------------------------------------------ scenarios

def _str_list(where, name, v, nonempty=False):
    """A JSON list of non-empty strings. A bare string is rejected, not split into characters."""
    if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v) or (nonempty and not v):
        raise ScenarioError(f"{where}: '{name}' must be a {'non-empty ' if nonempty else ''}list of non-empty strings")
    return v


def _regexes(where, name, v):
    for p in _str_list(where, name, v):
        try:
            re.compile(p)
        except re.error as e:
            raise ScenarioError(f"{where}: bad regex {p!r} in '{name}': {e}")


def _check_assert(where, a):
    if not isinstance(a, dict):
        raise ScenarioError(f"{where}: 'assert' must be an object")
    for k, v in a.items():
        if k not in ASSERT_SPEC:
            raise ScenarioError(f"{where}: unknown assert key '{k}' (known: {', '.join(sorted(ASSERT_SPEC))})")
        if not isinstance(v, ASSERT_SPEC[k]):
            raise ScenarioError(f"{where}: assert '{k}' must be {ASSERT_SPEC[k].__name__}")
        if k in ("dispatches", "dispatches_in_order", "only_dispatch", "not_dispatched", "allowed_subagent_types"):
            bad = [w for w in _str_list(where, k, v) if w not in WORKERS]
            if bad:
                raise ScenarioError(f"{where}: assert '{k}' names unknown worker(s) {bad}")
        if k == "forbidden_tools":
            _str_list(where, k, v)
        if k in ("final_text_regex", "final_text_not_regex"):
            _regexes(where, k, v)
        if k == "fixture_file_regex":
            for path, pats in v.items():
                if not path or path.startswith("/") or ".." in Path(path).parts:
                    raise ScenarioError(f"{where}: fixture_file_regex path {path!r} must be relative, without '..'")
                _regexes(where, f"fixture_file_regex[{path!r}]", pats)
    if a.get("no_dispatch") and (a.get("dispatches") or a.get("dispatches_in_order")):
        raise ScenarioError(f"{where}: no_dispatch contradicts dispatches")


def load_scenario(path):
    where = path.name
    try:
        s = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ScenarioError(f"{where}: invalid JSON: {e}")
    if not isinstance(s, dict):
        raise ScenarioError(f"{where}: top level must be an object")
    unknown = set(s) - SCENARIO_KEYS
    if unknown:
        raise ScenarioError(f"{where}: unknown key(s) {sorted(unknown)}")
    for k in ("skills", "query", "files", "expected_behavior", "assert"):
        if k not in s:
            raise ScenarioError(f"{where}: missing required key '{k}'")
    if s["skills"] != ["orchestrate"]:
        raise ScenarioError(f"{where}: 'skills' must be [\"orchestrate\"]")
    if not isinstance(s["query"], str) or not s["query"].strip():
        raise ScenarioError(f"{where}: 'query' must be a non-empty string")
    _str_list(where, "expected_behavior", s["expected_behavior"], nonempty=True)
    for f in _str_list(where, "files", s["files"], nonempty=True):
        p = (EVALS / f).resolve()
        if EVALS not in p.parents or not p.exists():
            raise ScenarioError(f"{where}: file {f!r} must exist under evals/")
    _check_assert(where, s["assert"])
    if not isinstance(s.get("followups", []), list):
        raise ScenarioError(f"{where}: 'followups' must be a list")
    for i, fu in enumerate(s.get("followups", [])):
        fw = f"{where} followups[{i}]"
        if not isinstance(fu, dict) or not isinstance(fu.get("query"), str) or not fu["query"].strip():
            raise ScenarioError(f"{fw}: each followup needs a non-empty string 'query'")
        if set(fu) - FOLLOWUP_KEYS:
            raise ScenarioError(f"{fw}: unknown key(s) {sorted(set(fu) - FOLLOWUP_KEYS)}")
        _str_list(fw, "expected_behavior", fu.get("expected_behavior", []))
        _check_assert(fw, fu.get("assert", {}))
    limits = dict(DEFAULT_LIMITS)
    if not isinstance(s.get("limits", {}), dict):
        raise ScenarioError(f"{where}: 'limits' must be an object")
    for k, v in s.get("limits", {}).items():
        if k not in LIMIT_KEYS or isinstance(v, bool) or not isinstance(v, LIMIT_KEYS[k]) or v <= 0:
            raise ScenarioError(f"{where}: bad limit {k}={v!r} (known: {', '.join(LIMIT_KEYS)}, positive)")
        limits[k] = v
    if not isinstance(s.get("runtime", {}), dict):
        raise ScenarioError(f"{where}: 'runtime' must be an object")
    for rt, cfg in s.get("runtime", {}).items():
        if rt not in RUNTIMES:
            raise ScenarioError(f"{where}: runtime key {rt!r} is not one of {list(RUNTIMES)}")
        if not isinstance(cfg, dict) or set(cfg) - {"disallowed_tools"}:
            raise ScenarioError(f"{where}: runtime.{rt} must be an object with only 'disallowed_tools'")
        _str_list(f"{where} runtime.{rt}", "disallowed_tools", cfg.get("disallowed_tools", []))
    s["name"] = path.stem
    s["limits"] = limits
    s["turns"] = [{"query": s["query"], "assert": s["assert"], "expected_behavior": s["expected_behavior"]}] + [
        {"query": fu["query"], "assert": fu.get("assert", {}), "expected_behavior": fu.get("expected_behavior", [])}
        for fu in s.get("followups", [])]
    return s


def select_scenarios(wanted):
    paths = sorted((EVALS / "scenarios").glob("*.json"))
    if wanted:
        chosen = []
        for w in wanted:
            hits = [p for p in paths if p.stem == w or p.stem.startswith(w)]
            if len(hits) != 1:
                raise ScenarioError(f"--scenario {w!r} matches {len(hits)} scenarios; use a unique prefix of: "
                                    + ", ".join(p.stem for p in paths))
            chosen.append(hits[0])
        paths = chosen
    return paths


# ------------------------------------------------------------------ what is being tested

def describe_skill(runtime):
    lines = []
    link = RUNTIMES[runtime]["skill_link"]
    if runtime == "opencode":
        agent = HOME / ".config/opencode/agents/orchestrate.md"
        if not agent.exists():
            return [f"OpenCode orchestrate agent: NOT INSTALLED at {agent}"], None
        text = agent.read_text()
        model = next((ln for ln in text.splitlines() if ln.startswith("model:")), "model: ?")
        stack = next((d.name for d in sorted((REPO / "agents/opencode").glob("*/"))
                      if (d / "orchestrate.md").exists() and filecmp.cmp(d / "orchestrate.md", agent, shallow=False)), None)
        lines.append(f"Testing: {agent.resolve()} ({model})")
        lines.append(f"Matches repo stack: {stack or 'NONE (stale or edited; reinstall with ./install.sh --opencode-stack=<name>)'}")
        return lines, agent.parent
    if not link.exists():
        return [f"Skill: NOT INSTALLED at {link} (run ./install.sh)"], None
    real = link.resolve()
    skill_md = real / "SKILL.md"
    desc = next((ln for ln in skill_md.read_text().splitlines() if ln.startswith("description:")), "description: ?")
    lines.append(f"Testing: {skill_md}  (via {link})")
    lines.append(f"  {desc[:160]}{'...' if len(desc) > 160 else ''}")
    diffs = _tree_diff(REPO / "skills/orchestrate", real)
    if not diffs:
        lines.append("  Matches repo skills/orchestrate: yes")
    else:
        lines.append("  Matches repo skills/orchestrate: NO, differs in " + ", ".join(diffs[:6])
                     + (" ..." if len(diffs) > 6 else ""))
        lines.append("  Results describe the INSTALLED skill. Run ./install.sh to test the repo version.")
    if runtime == "claude-code":
        status = []
        for w in WORKERS:
            inst, src = HOME / f".claude/agents/{w}.md", REPO / f"agents/claude/{w}.md"
            if not inst.exists():
                status.append(f"{w}: MISSING")
            elif not filecmp.cmp(inst, src, shallow=False):
                status.append(f"{w}: differs from repo")
        lines.append("  Workers in ~/.claude/agents: " + ("all five match the repo" if not status else "; ".join(status)))
    return lines, real


def _tree_diff(a, b):
    out = []
    cmp = filecmp.dircmp(a, b, ignore=[".DS_Store", "__pycache__"])

    def walk(c, prefix):
        out.extend(prefix + n for n in c.diff_files + c.left_only + c.right_only)
        for n, sub in c.subdirs.items():
            walk(sub, prefix + n + "/")
    walk(cmp, "")
    # dircmp's shallow compare can miss same-size same-mtime edits; confirm with a byte compare.
    for root, _, files in os.walk(a):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), a)
            other = Path(b) / rel
            if other.exists() and rel not in out and not filecmp.cmp(Path(root) / f, other, shallow=False):
                out.append(rel)
    return out


def cli_version(binary):
    try:
        return subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


# ------------------------------------------------------------------ fixture

def tmp_root():
    """The system temp dir, refused when it sits inside $HOME or this repo (TMPDIR can point anywhere)."""
    root = Path(tempfile.gettempdir()).resolve()
    for forbidden in (REPO, HOME):
        if root == forbidden or forbidden in root.parents:
            raise SystemExit(f"refusing to create fixtures: the temp dir {root} is inside {forbidden}; "
                             "point TMPDIR somewhere outside it")
    return root


def assert_safe(path):
    """Refuse to run anything in a directory that is not a throwaway dir under the temp root."""
    p = Path(path).resolve()
    root = tmp_root()
    if root not in p.parents:
        raise SystemExit(f"refusing to use {p}: not under the temp dir {root}")
    for forbidden in (REPO, HOME):
        if p == forbidden or forbidden in p.parents:
            raise SystemExit(f"refusing to use {p}: inside {forbidden}")
    return p


def _git(args, cwd):
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                    "-c", "user.name=dev", "-c", "user.email=dev@example.invalid",
                    "-c", "init.defaultBranch=main", *args],
                   cwd=cwd, check=True, capture_output=True, text=True)


def make_fixture(scn):
    # Checked before anything is created. Names stay neutral: the session sees its cwd, and a
    # path such as ".../03-destructive-task-hits-plan-gate" would tell the model what is tested.
    base = assert_safe(tempfile.mkdtemp(prefix="pyapp-", dir=tmp_root()))
    work = base / "pyapp"
    work.mkdir()
    for f in scn["files"]:
        src = (EVALS / f).resolve()
        if src.is_dir():
            shutil.copytree(src, work, dirs_exist_ok=True)
        else:
            shutil.copy2(src, work / src.name)
    # A local bare repo stands in for "origin", so a push can only ever land inside the temp dir.
    origin = base / "origin.git"
    _git(["init", "-q", "--bare", str(origin)], base)
    _git(["init", "-q"], work)
    _git(["add", "-A"], work)
    _git(["commit", "-q", "-m", "Initial commit"], work)
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-q", "-u", "origin", "main"], work)
    return base, assert_safe(work)


def snapshot(base):
    work, origin = base / "pyapp", base / "origin.git"
    files = {}
    for root, dirs, names in os.walk(work):
        dirs[:] = [d for d in dirs if d != ".git"]
        for n in names:
            p = Path(root) / n
            files[str(p.relative_to(work))] = hashlib.sha256(p.read_bytes()).hexdigest()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    remote = subprocess.run(["git", "--git-dir", str(origin), "rev-parse", "main"], capture_output=True, text=True).stdout.strip()
    return {"files": files, "head": head, "origin": remote}


def snapshot_diff(before, after):
    changed = sorted(k for k in set(before["files"]) | set(after["files"])
                     if before["files"].get(k) != after["files"].get(k))
    if before["head"] != after["head"]:
        changed.append("<new commit>")
    if before["origin"] != after["origin"]:
        changed.append("<pushed to origin>")
    return changed


# ------------------------------------------------------------------ Claude Code

def claude_cmd(prompt, scn, args, work, skill_dirs, turn, session_id):
    lim = scn["limits"]
    budget = args.budget_usd if args.budget_usd is not None else lim["budget_usd"]
    cmd = ["claude", "-p", prompt,
           "--output-format", "stream-json", "--verbose",
           # Not --restricted: it drops the `user` setting source, and with it ~/.claude/skills and
           # ~/.claude/agents, so the installed skill and workers would not load (probed live).
           # `user` only: the installed skill + workers load; project/local settings do not.
           "--setting-sources", "user",
           "--tools", ",".join(CLAUDE_TOOLS),   # built-in tool set: nothing that runs commands or fetches
           "--permission-mode", "dontAsk",       # anything not pre-approved is denied
           "--permission-prompts", "none",       # and nobody is asked
           "--strict-mcp-config",                # no MCP servers
           # Hooks run shell commands outside the tool permission system; turn them all off.
           "--settings", json.dumps({"disableAllHooks": True}),
           "--max-turns", str(args.max_turns or lim["max_turns"]),
           "--max-budget-usd", f"{budget:g}",
           # Subagents only (-p mode); the orchestrator's prompt is untouched.
           "--append-subagent-system-prompt", SUBAGENT_NOTE]
    if args.baseline:
        cmd += ["--disable-slash-commands"]
    else:
        # Read access to the skill's references/. Claude Code names the skill's base dir by its
        # link path (~/.claude/skills/orchestrate), so both that and the resolved dir are added.
        for d in skill_dirs:
            cmd += ["--add-dir", str(d)]
    if len(scn["turns"]) == 1:
        cmd += ["--no-session-persistence"]
    elif turn == 0:
        cmd += ["--session-id", session_id]
    else:
        cmd += ["--resume", session_id]
    if args.model:
        cmd += ["--model", args.model]
    if args.effort:
        cmd += ["--effort", args.effort]
    # Writes are pre-approved only inside the fixture ("//" = absolute path). Edit rules cover
    # every file-editing tool. Deny rules are session-wide, so they bind the workers too, and a
    # deny beats any allow: nothing under $HOME (this repo, ~/.claude, the installed skill) or
    # the skill dir can be edited, and no tool that runs commands or reaches the network exists.
    cmd += ["--allowedTools", f"Edit(//{str(work).lstrip('/')}/**)"]
    deny = list(CLAUDE_DENY) + ["Edit(~/**)"]
    deny += [f"Edit(//{str(d).lstrip('/')}/**)" for d in skill_dirs]
    deny += scn.get("runtime", {}).get("claude-code", {}).get("disallowed_tools", [])
    cmd += ["--disallowedTools", *deny]      # variadic: keep last
    return cmd


def run_process(cmd, cwd, timeout, raw_path):
    env = {k: v for k, v in os.environ.items() if k not in PARENT_SESSION_ENV}
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    events, err = [], []

    def read_out():
        with open(raw_path, "w") as fh:
            for line in proc.stdout:
                fh.write(line)
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        events.append({"type": "_unparsed", "line": line[:500]})

    t_out = threading.Thread(target=read_out, daemon=True)
    t_err = threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)
    t_out.start()
    t_err.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        stop_group(proc, ((signal.SIGINT, 15), (signal.SIGTERM, 10), (signal.SIGKILL, 5)))
    except BaseException:
        # Ctrl-C, or SIGTERM/SIGHUP turned into SystemExit by main(). The child runs in its own session,
        # so it would not get the signal and would keep running after the fixture is deleted.
        stop_group(proc, ((signal.SIGTERM, 5), (signal.SIGKILL, 5)))
        raise
    t_out.join(timeout=10)
    t_err.join(timeout=10)
    return events, "".join(err), proc.returncode, timed_out


def stop_group(proc, steps):
    """Signal the child's whole process group, escalating until it exits; SIGKILL is always the last resort.

    Nothing is sent once the child has been reaped: its pid (the group id) may belong to someone else by
    then. A second Ctrl-C or SIGTERM during a grace wait escalates to the next signal instead of
    abandoning the child, and is re-raised once the group is down.
    """
    interrupted = None
    for sig, grace in list(steps) + [(signal.SIGKILL, 5)]:
        if proc.poll() is not None:
            break
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            break
        try:
            proc.wait(timeout=grace)
            break
        except subprocess.TimeoutExpired:
            continue
        except BaseException as e:      # interrupted again while waiting: escalate, never stop here
            interrupted = interrupted or e
            continue
    if interrupted is not None:
        raise interrupted


def dispatch_state(tool_use_id, results, started, notified):
    """How one Agent call ended: "completed", or why it did not count as done.

    Claude Code runs Agent calls in the background in -p mode: the tool_result arrives at once
    ("Async agent launched successfully") and the worker's outcome comes later as a
    system/task_notification with the same tool_use_id. A synchronous call has no task events,
    and its tool_result is the worker's own result.
    """
    if tool_use_id in notified:
        status = notified[tool_use_id]
        return "completed" if status == "completed" else f"ended:{status}"
    if tool_use_id in started:
        return "launched, never finished"
    if tool_use_id not in results:
        return "no result"
    return "completed" if results[tool_use_id] else "error/denied"


def parse_claude(events):
    out = {"init": None, "tools": [], "dispatches": [], "final_text": "", "result": None, "denials": []}
    results, started, notified = {}, set(), {}
    last_text = ""
    for ev in events:
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            out["init"] = ev
        elif t == "system" and ev.get("subtype") == "permission_denied":
            out["denials"].append(ev)
        elif t == "system" and ev.get("subtype") == "task_started" and ev.get("tool_use_id"):
            if ev.get("is_backgrounded", True):
                started.add(ev["tool_use_id"])
        elif t == "system" and ev.get("subtype") == "task_notification" and ev.get("tool_use_id"):
            notified[ev["tool_use_id"]] = ev.get("status")
        elif t == "assistant":
            top = ev.get("parent_tool_use_id") is None
            for b in (ev.get("message") or {}).get("content") or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and top:
                    inp = b.get("input") or {}
                    out["tools"].append({"id": b.get("id"), "name": b.get("name"), "input": inp})
                    if b.get("name") in ("Agent", "Task"):
                        out["dispatches"].append({"id": b.get("id"),
                                                  "type": inp.get("subagent_type") or "general-purpose",
                                                  "model": inp.get("model"), "ok": None, "state": None})
                elif b.get("type") == "text" and top and b.get("text", "").strip():
                    last_text = b["text"]
        elif t == "user":
            content = (ev.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    results[b.get("tool_use_id")] = not b.get("is_error", False)
        elif t == "result":
            out["result"] = ev
    for d in out["dispatches"]:
        d["state"] = dispatch_state(d["id"], results, started, notified)
        d["ok"] = d["state"] == "completed"
    res = out["result"] or {}
    out["final_text"] = res.get("result") if isinstance(res.get("result"), str) else last_text
    return out


def _frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    end = next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), len(lines))
    return lines[1:end]


def claude_preflight(home=None, repo=None, allow_worker_drift=False):
    """Refuse to run when anything the session loads from the user source would widen what it may do.

    - ~/.claude/settings.json pre-approving edits: dontAsk honors allow rules.
    - any user agent setting permissionMode: a subagent runs in its own mode, not the parent's dontAsk.
    - an installed worker that differs from the repo's agents/claude/ (skipped with allow_worker_drift).
    """
    home, repo = Path(home or HOME), Path(repo or REPO)
    problems = []
    p = home / ".claude/settings.json"
    try:
        settings = json.loads(p.read_text()) if p.exists() else {}
    except (OSError, json.JSONDecodeError) as e:
        return [f"cannot read {p}: {e}"]
    allow = (settings.get("permissions") or {}).get("allow") or []
    risky = [r for r in allow if re.match(r"\s*(Edit|Write|NotebookEdit|MultiEdit)\b", str(r))]
    if risky:
        problems.append(f"{p} pre-approves file edits {risky}; a run could write outside the fixture. "
                        "Remove those allow rules while running evals.")
    agents_dir = home / ".claude/agents"
    for f in sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else []:
        try:
            fm = _frontmatter(f.read_text())
        except OSError as e:
            problems.append(f"cannot read {f}: {e}")
            continue
        mode = [ln for ln in fm if re.match(r"""\s*["']?permissionMode["']?\s*:""", ln)]
        if mode:
            problems.append(f"{f} sets {mode[0].strip()}; that agent would not run under the session's "
                            "dontAsk mode. Remove the line (or move the file away) while running evals.")
    if not allow_worker_drift:
        for w in WORKERS:
            inst, src = agents_dir / f"{w}.md", repo / f"agents/claude/{w}.md"
            if not inst.exists():
                problems.append(f"{inst} is missing; run ./install.sh")
            elif src.exists() and not filecmp.cmp(inst, src, shallow=False):
                problems.append(f"{inst} differs from {src}; run ./install.sh, or pass --allow-worker-drift "
                                "to test the installed workers as they are")
    return problems


def claude_preconditions(parsed, baseline, denied_workers):
    """Facts about the session that make the scenario's checks meaningful."""
    checks = []
    init = parsed["init"] or {}
    if not init:
        return [("session_started", False, "no system/init event; see the raw transcript and stderr")]
    tools = init.get("tools") or []
    checks.append(("agent_tool_available", "Agent" in tools or "Task" in tools,
                   f"init tools: {', '.join(tools) or '(none)'}"))
    agents = init.get("agents") or []
    missing = [w for w in WORKERS if w not in agents and w not in denied_workers]
    checks.append(("workers_listed", not missing, f"not in init agents: {missing}; agents: {agents}"))
    if not baseline:
        names = [str(x).lstrip("/") for x in (init.get("slash_commands") or []) + (init.get("skills") or [])]
        unknown = re.match(r"\s*unknown (skill|command|slash command)", parsed["final_text"] or "", re.I)
        listed = "orchestrate" in names
        checks.append(("skill_listed", listed and not unknown,
                       "orchestrate listed in init" if listed else "orchestrate NOT in init slash_commands/skills"))
    return checks


# ------------------------------------------------------------------ assertions

def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", text or ""))


def evaluate(assertions, parsed, before, after, work):
    a = dict(DEFAULT_ASSERT)
    a.update(assertions)
    checks = []
    # Every attempt counts for the checks on the orchestrator's decisions (worker type, model,
    # only/not/no dispatch): a call that was denied, crashed or ran out of budget was still the
    # orchestrator's choice. Only dispatches whose worker finished count as "dispatched" for
    # `dispatches` and `dispatches_in_order`, which claim the work was actually done.
    attempted = [d["type"] for d in parsed["dispatches"]]
    succeeded = [d["type"] for d in parsed["dispatches"] if d["ok"]]

    bad_tools = sorted({t["name"] for t in parsed["tools"] if t["name"] in a["forbidden_tools"]})
    checks.append(("forbidden_tools", not bad_tools, f"orchestrator called {bad_tools}" if bad_tools else ""))
    bad_types = sorted({t for t in attempted if t not in a["allowed_subagent_types"]})
    checks.append(("allowed_subagent_types", not bad_types, f"dispatched {bad_types}" if bad_types else ""))
    if a["model_set"] and parsed["dispatches"]:
        wrong = []
        for d in parsed["dispatches"]:
            if d["type"] in TIER:
                want = CLAUDE_TIER_MODEL[TIER[d["type"]]]
                if not d["model"] or want not in str(d["model"]).lower():
                    wrong.append(f"{d['type']}:model={d['model']!r} (want {want})")
        checks.append(("model_set", not wrong, "; ".join(wrong)))
    if a.get("no_dispatch"):
        checks.append(("no_dispatch", not attempted, f"dispatched {attempted}" if attempted else ""))
    if "dispatches" in a:
        miss = [w for w in a["dispatches"] if w not in succeeded]
        checks.append(("dispatches", not miss, f"missing {miss}; got {succeeded}" if miss else ""))
    if "dispatches_in_order" in a:
        it = iter(succeeded)
        ok = all(any(x == w for x in it) for w in a["dispatches_in_order"])
        checks.append(("dispatches_in_order", ok, "" if ok else f"want {a['dispatches_in_order']} in order; got {succeeded}"))
    if "only_dispatch" in a:
        extra = [w for w in attempted if w not in a["only_dispatch"]]
        checks.append(("only_dispatch", not extra, f"also dispatched {extra}" if extra else ""))
    if "not_dispatched" in a:
        hit = [w for w in attempted if w in a["not_dispatched"]]
        checks.append(("not_dispatched", not hit, f"dispatched {hit}" if hit else ""))
    text = _norm(parsed["final_text"])
    for p in a.get("final_text_regex", []):
        checks.append((f"final_text_regex /{p}/", bool(re.search(p, text, re.I)), "no match in final message"))
    for p in a.get("final_text_not_regex", []):
        checks.append((f"final_text_not_regex /{p}/", not re.search(p, text, re.I), "matched final message"))
    if a.get("fixture_unchanged"):
        changed = snapshot_diff(before, after)
        checks.append(("fixture_unchanged", not changed, f"changed: {changed}" if changed else ""))
    for rel, pats in a.get("fixture_file_regex", {}).items():
        f = work / rel
        body = f.read_text() if f.exists() else ""
        for p in pats:
            checks.append((f"fixture {rel} /{p}/", bool(re.search(p, body)), "missing" if f.exists() else "file missing"))
    return [(n, ok, "" if ok else d) for n, ok, d in checks]


# ------------------------------------------------------------------ runners

def turn_cost(cumulative, previous_cumulative):
    """This turn's spend. A --resume turn reports the conversation's cumulative total_cost_usd
    (earlier turns included; confirmed live: turn 2's usage = turn 1's + its own), so subtract
    the previous turn's total. A first turn's total is its own."""
    if cumulative is None:
        return None
    if previous_cumulative is None:
        return cumulative
    return max(0.0, cumulative - previous_cumulative)


def run_claude_scenario(scn, args, skill_dirs, outdir):
    base, work = make_fixture(scn)
    before = snapshot(base)
    session_id = str(uuid.uuid4())
    previous_total = None
    label = scn["name"] + ("-baseline" if args.baseline else "")
    record = {"scenario": scn["name"], "mode": "baseline" if args.baseline else "skill", "turns": [], "fixture": str(base)}
    try:
        for i, turn in enumerate(scn["turns"]):
            prompt = turn["query"] if (args.baseline or i > 0) else RUNTIMES["claude-code"]["prefix"] + turn["query"]
            cmd = claude_cmd(prompt, scn, args, work, skill_dirs, i, session_id)
            raw = outdir / f"{label}.turn{i + 1}.jsonl"
            print(f"  [{label}] turn {i + 1}/{len(scn['turns'])} running ...", flush=True)
            events, stderr, rc, timed_out = run_process(cmd, work, scn["limits"]["timeout_s"], raw)
            if stderr.strip():
                (outdir / f"{label}.turn{i + 1}.stderr.txt").write_text(stderr)
            parsed = parse_claude(events)
            after = snapshot(base)
            res = parsed["result"] or {}
            complete = (not timed_out) and res.get("subtype") == "success" and not res.get("is_error")
            denied = [m.group(1) for r in scn.get("runtime", {}).get("claude-code", {}).get("disallowed_tools", [])
                      for m in [re.fullmatch(r"(?:Agent|Task)\((.+)\)", r)] if m]
            checks = (claude_preconditions(parsed, args.baseline, denied)
                      + evaluate(turn["assert"], parsed, before, after, work))
            record["turns"].append({
                "turn": i + 1, "command": shlex.join(cmd), "returncode": rc, "timed_out": timed_out,
                "subtype": res.get("subtype"), "num_turns": res.get("num_turns"),
                "cost_usd": turn_cost(res.get("total_cost_usd"), previous_total),
                "cost_usd_cumulative": res.get("total_cost_usd"),
                "model": (parsed["init"] or {}).get("model"),
                "dispatches": parsed["dispatches"], "orchestrator_tools": [t["name"] for t in parsed["tools"]],
                "permission_denials": res.get("permission_denials") or [d.get("tool_name") for d in parsed["denials"]],
                "final_text": parsed["final_text"], "complete": complete,
                "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
                "stderr_tail": stderr.strip()[-400:]})
            if res.get("total_cost_usd") is not None:
                previous_total = res.get("total_cost_usd")
            if not complete:
                break   # a later turn depends on this one finishing
    finally:
        if args.keep:
            record["kept"] = True
        else:
            purge_claude_state(work)
            cleanup_claude_scratch(work)
            shutil.rmtree(assert_safe(base), ignore_errors=True)
    record["verdict"] = verdict(record, len(scn["turns"]))
    return record


def purge_claude_state(work):
    """Remove the transcript/project entry Claude Code may have created for the temp fixture."""
    work = assert_safe(work)
    try:
        r = subprocess.run(["claude", "purge", str(work), "--yes"], cwd=work, capture_output=True, text=True,
                           timeout=60, stdin=subprocess.DEVNULL,
                           env={k: v for k, v in os.environ.items() if k not in PARENT_SESSION_ENV})
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"  warning: claude purge {work} failed: {e}", file=sys.stderr)
        return
    if r.returncode != 0:
        print(f"  warning: claude purge {work} exited {r.returncode}: {(r.stderr or r.stdout).strip()[:300]}",
              file=sys.stderr)


def claude_scratch_roots():
    """Where Claude Code keeps per-cwd scratch (background task output): <tmp>/claude-<uid>/<cwd slug>/.
    Seen live under /tmp (/private/tmp on macOS), not under $TMPDIR; both are checked."""
    roots = []
    for base in (Path("/tmp"), Path(tempfile.gettempdir())):
        r = base.resolve() / f"claude-{os.getuid()}"
        if r not in roots:
            roots.append(r)
    return roots


def cwd_slug(path):
    """Claude Code's directory name for a cwd: every character outside [A-Za-z0-9] becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def scratch_dir_problem(candidate, work):
    """None when `candidate` is this fixture's Claude Code scratch dir and may be removed; else why not."""
    try:
        work = assert_safe(work)
    except SystemExit as e:
        return f"fixture path refused: {e}"
    c = Path(candidate)
    if c.is_symlink():
        return "is a symlink"
    parent = c.parent.resolve()
    if parent not in claude_scratch_roots():
        return f"parent {parent} is not a Claude Code scratch root {[str(r) for r in claude_scratch_roots()]}"
    for forbidden in (REPO, HOME):
        if parent == forbidden or forbidden in parent.parents:
            return f"inside {forbidden}"
    if c.name != cwd_slug(work):
        return f"name does not encode this fixture's path (want {cwd_slug(work)})"
    return None


def cleanup_claude_scratch(work):
    """Remove the scratch dir Claude Code leaves for the fixture's cwd; claude purge does not."""
    for root in claude_scratch_roots():
        c = root / cwd_slug(work)
        if not (c.exists() or c.is_symlink()):
            continue
        problem = scratch_dir_problem(c, work)
        if problem:
            print(f"  warning: left {c} in place: {problem}", file=sys.stderr)
            continue
        shutil.rmtree(c, ignore_errors=True)


def verdict(record, n_turns):
    turns = record["turns"]
    failed = [c for t in turns for c in t["checks"] if not c["ok"]]
    safety_failed = [c for c in failed if c["name"] in SAFETY_CHECKS]
    if safety_failed:
        return "FAIL"
    if len(turns) < n_turns or not all(t["complete"] for t in turns):
        return "ERROR"
    return "FAIL" if failed else "PASS"


def manual_commands(runtime, scn, args, fixture="<FIXTURE>", outfile="<FIXTURE>/../transcript"):
    q = [t["query"] for t in scn["turns"]]
    first = RUNTIMES[runtime]["prefix"] + q[0]
    m = args.model
    cmds = []
    if runtime == "codex":
        eph = ["--ephemeral"] if len(q) == 1 else []
        cmds.append(shlex.join(["codex", "exec", "--json", "--sandbox", "workspace-write", *eph, "-C", fixture,
                                *(["-m", m] if m else []), "-o", f"{outfile}.last.txt", first]) + f" > {outfile}.turn1.jsonl")
        for i, fq in enumerate(q[1:], 2):
            cmds.append(shlex.join(["codex", "exec", "--json", "--sandbox", "workspace-write", "-C", fixture,
                                    "resume", "--last", fq]) + f" > {outfile}.turn{i}.jsonl")
    elif runtime == "antigravity":
        cmds.append(f"cd {shlex.quote(fixture)} && " + shlex.join(
            ["agy", "-p", first, "--output-format", "stream-json", "--sandbox", *(["--model", m] if m else [])])
                    + f" > {outfile}.turn1.jsonl")
        for i, fq in enumerate(q[1:], 2):
            cmds.append(f"cd {shlex.quote(fixture)} && " + shlex.join(
                ["agy", "-c", "-p", fq, "--output-format", "stream-json", "--sandbox"]) + f" > {outfile}.turn{i}.jsonl")
    elif runtime == "opencode":
        cmds.append(f"cd {shlex.quote(fixture)} && " + shlex.join(
            ["opencode", "run", "--standalone", "--agent", "orchestrate", "--format", "json", first])
                    + f" > {outfile}.turn1.jsonl")
        for i, fq in enumerate(q[1:], 2):
            cmds.append(f"cd {shlex.quote(fixture)} && " + shlex.join(
                ["opencode", "run", "--standalone", "--continue", "--agent", "orchestrate", "--format", "json", fq])
                        + f" > {outfile}.turn{i}.jsonl")
    return cmds


# ------------------------------------------------------------------ output

def print_table(records):
    rows = [("scenario", "mode", "verdict", "dispatches (type:model)", "cost", "failed checks")]
    for r in records:
        disp, cost, fails = [], 0.0, []
        for t in r["turns"]:
            disp += [f"{d['type']}:{d['model'] or '-'}{'' if d['ok'] else '(' + str(d.get('state') or 'not completed') + ')'}"
                     for d in t["dispatches"]]
            cost += t["cost_usd"] or 0
            fails += [f"t{t['turn']} {c['name']}: {c['detail']}" for c in t["checks"] if not c["ok"]]
            if not t["complete"]:
                fails.append(f"t{t['turn']} run incomplete: subtype={t['subtype']} rc={t['returncode']}"
                             + (" timeout" if t["timed_out"] else ""))
        rows.append((r["scenario"], r["mode"], r["verdict"], ", ".join(disp) or "-", f"${cost:.2f}",
                     " | ".join(fails) or "-"))
    widths = [max(len(row[i]) for row in rows) for i in range(5)]
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(5)) + "  " + row[5])


def main():
    ap = argparse.ArgumentParser(description="Behavioral evals for the orchestrate skill (see evals/README.md).")
    ap.add_argument("--runtime", default="claude-code", choices=list(RUNTIMES))
    ap.add_argument("--model", help="orchestrator (session) model, e.g. sonnet, opus, fable")
    ap.add_argument("--effort", help="Claude Code session effort: low, medium, high, xhigh, max")
    ap.add_argument("--baseline", action="store_true", help="send the same queries without invoking the skill")
    ap.add_argument("--scenario", action="append", help="scenario name or unique prefix (repeatable); default all")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate scenarios and print commands; starts no session (only `<cli> --version`)")
    ap.add_argument("--budget-usd", type=float, help="override each scenario's per-turn --max-budget-usd")
    ap.add_argument("--max-turns", type=int, help="override each scenario's --max-turns")
    ap.add_argument("--keep", action="store_true",
                    help="keep the temp fixtures for inspection (also skips `claude purge` and the scratch-dir cleanup)")
    ap.add_argument("--allow-worker-drift", action="store_true",
                    help="run even when ~/.claude/agents/<worker>.md differs from the repo (permissionMode still refused)")
    ap.add_argument("-v", "--verbose", action="store_true", help="print each turn's final message")
    args = ap.parse_args()
    # SIGTERM and SIGHUP become SystemExit, so run_process stops the child's process group and the
    # fixture cleanup in `finally` still runs.
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda signum, frame: sys.exit(128 + signum))

    try:
        paths = select_scenarios(args.scenario)
        scenarios = [load_scenario(p) for p in paths]
    except ScenarioError as e:
        print(f"invalid scenario: {e}", file=sys.stderr)
        return 2
    if not scenarios:
        print("no scenarios found in evals/scenarios/", file=sys.stderr)
        return 2

    rt = RUNTIMES[args.runtime]
    binary = {"claude-code": "claude", "codex": "codex", "antigravity": "agy", "opencode": "opencode"}[args.runtime]
    print(f"Runtime: {args.runtime} ({'automated' if rt['automated'] else 'manual'})  "
          f"CLI: {cli_version(binary) or 'NOT FOUND'}  Orchestrator model: {args.model or '(session default)'}"
          f"  Mode: {'baseline (skill not invoked)' if args.baseline else 'skill'}")
    info, skill_dir = describe_skill(args.runtime)
    for ln in info:
        print(ln)
    # The link path and the resolved dir, deduplicated: Claude Code reports the link path.
    skill_dirs = []
    if skill_dir is not None and args.runtime == "claude-code":
        skill_dirs = list(dict.fromkeys([rt["skill_link"], skill_dir]))
    if args.runtime == "claude-code":
        problems = claude_preflight(allow_worker_drift=args.allow_worker_drift)
        print("Preflight: " + ("; ".join(problems) if problems else
                               "ok (no edit allow rules, no agent sets permissionMode, workers match the repo)"))
    print(f"Scenarios: {len(scenarios)} valid ({', '.join(s['name'] for s in scenarios)})")

    if args.dry_run or not rt["automated"]:
        prepare = not args.dry_run   # manual runtime, live: build fixtures the human runs the commands in
        for s in scenarios:
            print(f"\n== {s['name']}  (max_turns {s['limits']['max_turns']}, budget ${s['limits']['budget_usd']:g}/turn)")
            fixture, transcript = "<FIXTURE>", "<FIXTURE>/../transcript"
            if prepare:
                base, work = make_fixture(s)
                fixture, transcript = str(work), str(base / "transcript")
            if rt["automated"]:
                for i, t in enumerate(s["turns"]):
                    prompt = t["query"] if (args.baseline or i > 0) else rt["prefix"] + t["query"]
                    cmd = claude_cmd(prompt, s, args, Path(fixture), skill_dirs, i, "<SESSION-UUID>")
                    print(f"  turn {i + 1}: (cwd {fixture})\n    {shlex.join(cmd)}")
            else:
                for c in manual_commands(args.runtime, s, args, fixture, transcript):
                    print(f"  {c}")
                for i, t in enumerate(s["turns"]):
                    print("  expected behavior (whole scenario):" if i == 0 else f"  expected after turn {i + 1}:")
                    for e in t["expected_behavior"]:
                        print(f"    - {e}")
                if prepare:
                    print(f"  fixture: {fixture}   (remove with: rm -rf {shlex.quote(str(base))})")
        if not rt["automated"] and not args.dry_run:
            print("\nManual runtime: run the commands above yourself and grade each turn against its expected "
                  "behavior (evals/README.md, 'Manual runtimes').")
        return 0

    if not shutil.which("claude"):
        print("claude not found on PATH", file=sys.stderr)
        return 2
    if problems:
        for p in problems:
            print(f"refusing to run: {p}", file=sys.stderr)
        return 2
    if not args.baseline and skill_dir is None:
        print("the orchestrate skill is not installed for Claude Code; run ./install.sh", file=sys.stderr)
        return 2
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = EVALS / "results" / f"{stamp}-{args.runtime}-{args.model or 'default'}{'-baseline' if args.baseline else ''}"
    outdir.mkdir(parents=True, exist_ok=True)
    records = []
    for s in scenarios:
        rec = run_claude_scenario(s, args, skill_dirs, outdir)
        records.append(rec)
        if args.verbose:
            for t in rec["turns"]:
                print(f"  [{s['name']}] turn {t['turn']} final message:\n    "
                      + (t["final_text"] or "(none)").replace("\n", "\n    "))
    (outdir / "summary.json").write_text(json.dumps(records, indent=2))
    print()
    print_table(records)
    total = sum((t["cost_usd"] or 0) for r in records for t in r["turns"])
    print(f"\nTotal reported cost: ${total:.2f} (client-side estimate)   Transcripts: {outdir}")
    return 0 if all(r["verdict"] == "PASS" for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
