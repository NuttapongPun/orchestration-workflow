#!/usr/bin/env bash
# Link this repo's skill and worker agents into every runtime found on this machine.
# Idempotent. Re-run after `git pull`. Use `./install.sh --uninstall` to remove the links.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-install}"
SKILL_SRC="$REPO/skills/orchestrate"
CANON="$HOME/.agents/skills/orchestrate"          # canonical location used by the `skills` CLI

# runtime name | detect dir | agents dir | agents source | skills dir (empty = runtime reads ~/.agents/skills directly)
RUNTIMES=(
  "Claude Code|$HOME/.claude|$HOME/.claude/agents|claude|$HOME/.claude/skills"
  "Codex|$HOME/.codex|$HOME/.codex/agents|codex|$HOME/.codex/skills"
  "Antigravity CLI|$HOME/.gemini/config|$HOME/.gemini/config/agents|antigravity|$HOME/.gemini/config/skills"
  "OpenCode|$HOME/.config/opencode|$HOME/.config/opencode/agents|opencode|"
)

link() {  # link <target> <linkpath>
  local target="$1" path="$2"
  if [[ -L "$path" ]]; then
    [[ "$(readlink "$path")" == "$target" ]] && return 0
    rm "$path"
  elif [[ -e "$path" ]]; then
    mv "$path" "$path.bak"
    echo "  moved existing $path -> $path.bak"
  fi
  mkdir -p "$(dirname "$path")"
  ln -s "$target" "$path"
  echo "  linked $path -> $target"
}

unlink_if_ours() {  # unlink_if_ours <linkpath>
  local path="$1"
  [[ -L "$path" ]] && [[ "$(readlink "$path")" == "$REPO"/* || "$(readlink "$path")" == "$CANON" ]] && rm "$path" && echo "  removed $path" || true
}

ensure_codex_no_nesting() {
  local cfg="$HOME/.codex/config.toml"
  [[ -f "$cfg" ]] || return 0
  if ! grep -q '^\[agents\]' "$cfg"; then
    printf '\n[agents]\nmax_depth = 1\n' >> "$cfg"
    echo "  appended [agents] max_depth = 1 to $cfg"
  elif ! grep -q '^max_depth' "$cfg"; then
    echo "  NOTE: [agents] exists in $cfg but has no max_depth; add 'max_depth = 1' to disable nested subagents"
  fi
}

if [[ "$MODE" == "--uninstall" ]]; then
  echo "Removing links..."
  for rt in "${RUNTIMES[@]}"; do
    IFS='|' read -r name detect agents_dir src skills_dir <<<"$rt"
    for f in "$REPO/agents/$src"/*; do unlink_if_ours "$agents_dir/$(basename "$f")"; done
    [[ -n "$skills_dir" ]] && unlink_if_ours "$skills_dir/orchestrate"
  done
  unlink_if_ours "$CANON"
  echo "Done. (Codex [agents] max_depth line left in place.)"
  exit 0
fi

echo "Skill -> $CANON"
link "$SKILL_SRC" "$CANON"

for rt in "${RUNTIMES[@]}"; do
  IFS='|' read -r name detect agents_dir src skills_dir <<<"$rt"
  if [[ ! -d "$detect" ]]; then
    echo "$name: not installed ($detect missing), skipped"
    continue
  fi
  echo "$name:"
  for f in "$REPO/agents/$src"/*; do link "$f" "$agents_dir/$(basename "$f")"; done
  [[ -n "$skills_dir" ]] && link "$CANON" "$skills_dir/orchestrate"
  [[ "$src" == "codex" ]] && ensure_codex_no_nesting
done

echo
echo "Done. Start a fresh session in each runtime and run /orchestrate (OpenCode: select the 'orchestrate' primary agent)."
