#!/usr/bin/env bash
# Install or update the orchestration workflow (shared /orchestrate skill + worker subagents)
# into every supported runtime found on this machine: Claude Code, Codex, Antigravity CLI, OpenCode.
#
# One-line install / update (copy mode):
#   curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
#
# From a clone (link mode: runtime files become symlinks into the clone, `git pull` updates them):
#   ./install.sh
#
# Flags:  --yes        replace existing worker agents without asking
#         --copy       force copy mode even when run from a clone
#         --uninstall  remove everything this script installed
set -euo pipefail

main() {

REPO_SLUG="NuttapongPun/orchestration-workflow"
TARBALL="https://github.com/$REPO_SLUG/archive/refs/heads/main.tar.gz"
CANON="$HOME/.agents/skills/orchestrate"        # canonical skill location (what the `skills` CLI uses)

YES=0; MODE=""; UNINSTALL=0
for a in "$@"; do case "$a" in
  --yes|-y) YES=1;; --copy) MODE="copy";; --link) MODE="link";; --uninstall) UNINSTALL=1;;
  *) echo "unknown flag: $a" >&2; exit 2;;
esac; done

# name | detect dir | agents dir | agents source subdir | skills dir ("" = runtime reads ~/.agents/skills itself)
RUNTIMES=(
  "Claude Code|$HOME/.claude|$HOME/.claude/agents|claude|$HOME/.claude/skills"
  "Codex|$HOME/.codex|$HOME/.codex/agents|codex|$HOME/.codex/skills"
  "Antigravity CLI|$HOME/.gemini/config|$HOME/.gemini/config/agents|antigravity|$HOME/.gemini/config/skills"
  "OpenCode|$HOME/.config/opencode|$HOME/.config/opencode/agents|opencode|"
)

say()  { printf '%s\n' "$*"; }
HAVE_TTY=0; ( : < /dev/tty ) 2>/dev/null && HAVE_TTY=1   # can we actually open the keyboard? (curl | bash still can)
ask()  { # ask "question" -> 0 yes / 1 no. Reads the keyboard even when piped through bash.
  [[ $YES -eq 1 ]] && return 0
  local reply
  if [[ $HAVE_TTY -eq 1 ]]; then read -r -p "$1 [y/N] " reply < /dev/tty; else reply="n"; say "$1 [y/N] n  (no terminal, pass --yes to accept)"; fi
  [[ "$reply" =~ ^[Yy]$ ]]
}
same_target() { [[ -L "$1" && "$(readlink "$1")" == "$2" ]]; }

# ------------------------------------------------------------------ uninstall
if [[ $UNINSTALL -eq 1 ]]; then
  for rt in "${RUNTIMES[@]}"; do
    IFS='|' read -r name detect agents_dir src skills_dir <<<"$rt"
    for w in investigate easy-worker hard-worker review review-hard orchestrate; do
      for ext in md toml; do f="$agents_dir/$w.$ext"; [[ -e "$f" || -L "$f" ]] && rm -f "$f" && say "removed $f"; done
    done
    [[ -n "$skills_dir" && -L "$skills_dir/orchestrate" ]] && rm -f "$skills_dir/orchestrate" && say "removed $skills_dir/orchestrate"
  done
  [[ -e "$CANON" || -L "$CANON" ]] && rm -rf "$CANON" && say "removed $CANON"
  say "Done. (Codex [agents] max_depth line left in place.)"
  exit 0
fi

# ------------------------------------------------------------------ source: clone next to script, or download
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -z "$MODE" ]]; then
  if [[ -n "$SCRIPT_DIR" && -d "$SCRIPT_DIR/agents" && -d "$SCRIPT_DIR/skills" ]]; then MODE="link"; else MODE="copy"; fi
fi
if [[ "$MODE" == "link" ]]; then
  SRC="$SCRIPT_DIR"
else
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  say "Downloading $REPO_SLUG..."
  curl -fsSL "$TARBALL" | tar -xz -C "$TMP"
  SRC="$(find "$TMP" -maxdepth 1 -mindepth 1 -type d | head -1)"
fi
say "Mode: $MODE   Source: $SRC"

# ------------------------------------------------------------------ detect runtimes
FOUND=(); MISSING=()
for rt in "${RUNTIMES[@]}"; do IFS='|' read -r name detect _ _ _ <<<"$rt"; if [[ -d "$detect" ]]; then FOUND+=("$rt"); else MISSING+=("$name"); fi; done
[[ ${#FOUND[@]} -eq 0 ]] && { say "No supported runtime found (Claude Code, Codex, Antigravity CLI, OpenCode). Nothing to do."; exit 1; }
say "Runtimes found: $(for rt in "${FOUND[@]}"; do IFS='|' read -r n _ <<<"$rt"; printf '%s; ' "$n"; done)"
[[ ${#MISSING[@]} -gt 0 ]] && say "Not installed (skipped): ${MISSING[*]}"

# ------------------------------------------------------------------ existing workers -> ask once
EXISTING=()
for rt in "${FOUND[@]}"; do
  IFS='|' read -r name detect agents_dir src skills_dir <<<"$rt"
  for f in "$SRC/agents/$src"/*; do
    dest="$agents_dir/$(basename "$f")"
    [[ -e "$dest" || -L "$dest" ]] || continue
    if [[ "$MODE" == "link" ]]; then same_target "$dest" "$f" && continue
    else [[ ! -L "$dest" ]] && cmp -s "$f" "$dest" && continue; fi
    EXISTING+=("$dest")
  done
done
REPLACE=1
if [[ ${#EXISTING[@]} -gt 0 ]]; then
  say "Worker agents already exist and differ from this version (${#EXISTING[@]} files), e.g. ${EXISTING[0]}"
  if ask "Replace them with the new version (update)?"; then REPLACE=1; else REPLACE=0; say "Keeping existing worker agents."; fi
fi

place() { # place <src> <dest>   (link or copy depending on MODE; respects REPLACE)
  local s="$1" d="$2"
  if [[ -e "$d" || -L "$d" ]]; then
    if [[ "$MODE" == "link" ]]; then same_target "$d" "$s" && return 0; else [[ ! -L "$d" ]] && cmp -s "$s" "$d" && return 0; fi
    [[ $REPLACE -eq 1 ]] || return 0
    rm -rf "$d"
  fi
  mkdir -p "$(dirname "$d")"
  if [[ "$MODE" == "link" ]]; then ln -s "$s" "$d"; else cp -R "$s" "$d"; fi
  say "  installed $d"
}

# ------------------------------------------------------------------ skill
say "Skill:"
SKILL_VIA_CLI=0
if [[ "$MODE" == "copy" ]] && command -v npx >/dev/null 2>&1; then
  say "  skills CLI available (npx). Installing the skill through it so 'npx skills update' can refresh it."
  yflag=""; [[ $YES -eq 1 ]] && yflag="-y"
  if [[ $HAVE_TTY -eq 1 ]]; then npx -y skills add "$REPO_SLUG" --global --skill orchestrate $yflag < /dev/tty && SKILL_VIA_CLI=1 || true
  else npx -y skills add "$REPO_SLUG" --global --skill orchestrate -y < /dev/null && SKILL_VIA_CLI=1 || true; fi
  [[ $SKILL_VIA_CLI -eq 1 && -d "$CANON" ]] || { SKILL_VIA_CLI=0; say "  skills CLI install did not produce $CANON; falling back to a direct copy."; }
fi
if [[ $SKILL_VIA_CLI -eq 0 ]]; then
  if [[ "$MODE" == "link" ]]; then
    same_target "$CANON" "$SRC/skills/orchestrate" || { rm -rf "$CANON"; mkdir -p "$(dirname "$CANON")"; ln -s "$SRC/skills/orchestrate" "$CANON"; say "  linked $CANON"; }
  else
    rm -rf "$CANON"; mkdir -p "$(dirname "$CANON")"; cp -R "$SRC/skills/orchestrate" "$CANON"; say "  copied to $CANON"
  fi
fi

# ------------------------------------------------------------------ per-runtime
for rt in "${FOUND[@]}"; do
  IFS='|' read -r name detect agents_dir src skills_dir <<<"$rt"
  say "$name:"
  for f in "$SRC/agents/$src"/*; do place "$f" "$agents_dir/$(basename "$f")"; done
  if [[ -n "$skills_dir" ]]; then
    same_target "$skills_dir/orchestrate" "$CANON" || { rm -rf "$skills_dir/orchestrate"; mkdir -p "$skills_dir"; ln -s "$CANON" "$skills_dir/orchestrate"; say "  linked $skills_dir/orchestrate -> $CANON"; }
  fi
  if [[ "$src" == "codex" ]]; then
    cfg="$HOME/.codex/config.toml"
    if [[ -f "$cfg" ]] && ! grep -q '^\[agents\]' "$cfg"; then printf '\n[agents]\nmax_depth = 1\n' >> "$cfg"; say "  appended [agents] max_depth = 1 to $cfg"
    elif [[ -f "$cfg" ]] && ! grep -q '^max_depth' "$cfg"; then say "  NOTE: [agents] exists in $cfg without max_depth; add 'max_depth = 1' to stop workers spawning workers"; fi
  fi
done

cat <<EOF

Done. Start a FRESH session and run /orchestrate (OpenCode: select the 'orchestrate' primary agent).

Run the orchestrator on the strongest model you have. Suggested:
  Claude Code      /model -> Fable 5.1 (or Opus 5)
  Codex            /model -> GPT-6 Astra if available, else GPT-5.6 Sol
  Antigravity CLI  session model -> Gemini 3.1 Pro (High)
  OpenCode         the 'orchestrate' primary agent pins its model in agents/opencode/orchestrate.md

Update later: re-run this command$( [[ "$MODE" == "link" ]] && printf ', or git pull in the clone' ).
EOF
}

# Everything above is parsed before this line runs, so `curl | bash` cannot be cut short by a child reading stdin.
main "$@"
