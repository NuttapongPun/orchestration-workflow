#!/usr/bin/env bash
# Install or update the orchestration workflow (shared /orchestrate skill + worker subagents)
# into every supported runtime found on this machine: Claude Code, Codex, Antigravity CLI, OpenCode.
#
# One-line install / update (copy mode):
#   curl -fsSL https://raw.githubusercontent.com/NuttapongPun/orchestration-workflow/main/install.sh | bash
#
# From a clone (link mode: runtime files become symlinks into the clone, `git pull` updates them;
# Codex agent files are the exception and are always copied, since Codex rejects symlinked roles):
#   ./install.sh
#
# Flags:  --yes                    replace existing installed files without asking
#         --copy                   force copy mode even when run from a clone
#         --link                   force link mode (the default when run from a clone)
#         --opencode-stack=<name>  which OpenCode model stack to install (default: free).
#                                  <name> is a plain directory name under agents/opencode/
#                                  (no slash, no leading dot). The names there today are:
#                                  free, openai, openai-openrouter, claude, claude-openrouter, cheap-openrouter
#         --uninstall  remove everything this script installed
set -euo pipefail

main() {

REPO_SLUG="NuttapongPun/orchestration-workflow"
TARBALL="https://github.com/$REPO_SLUG/archive/refs/heads/main.tar.gz"
CANON="$HOME/.agents/skills/orchestrate"        # canonical skill location (what the `skills` CLI uses)

YES=0; MODE=""; UNINSTALL=0; OC_STACK="free"
for a in "$@"; do case "$a" in
  --yes|-y) YES=1;; --copy) MODE="copy";; --link) MODE="link";; --uninstall) UNINSTALL=1;;
  --opencode-stack=*) OC_STACK="${a#*=}";;
  *) echo "unknown flag: $a" >&2; exit 2;;
esac; done

# name | detect dir | agents dir | agents source subdir | skills dir ("" = runtime reads ~/.agents/skills itself)
# OpenCode's source subdir carries the chosen model stack; every stack is pre-generated under agents/opencode/.
RUNTIMES=(
  "Claude Code|$HOME/.claude|$HOME/.claude/agents|claude|$HOME/.claude/skills"
  "Codex|$HOME/.codex|$HOME/.codex/agents|codex|$HOME/.codex/skills"
  "Antigravity CLI|$HOME/.gemini/config|$HOME/.gemini/config/agents|antigravity|$HOME/.gemini/config/skills"
  "OpenCode|$HOME/.config/opencode|$HOME/.config/opencode/agents|opencode/$OC_STACK|"
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
points_to() { # 0 = $1 is a symlink that resolves to the same directory as $2 (the `skills` CLI
  [[ -L "$1" ]] || return 1   # writes relative links, so a literal comparison is not enough)
  local a b
  a="$(cd -P "$1" 2>/dev/null && pwd -P)" || return 1
  b="$(cd -P "$2" 2>/dev/null && pwd -P)" || return 1
  [[ -n "$a" && "$a" == "$b" ]]
}
# Codex (0.155) opens role files under ~/.codex/agents/ with O_NOFOLLOW at spawn time and rejects
# a symlink there ("agent type is currently not available"), so its agent files are always copied,
# even in link mode.
copy_only() { [[ "$1" == "codex" ]]; }

# ------------------------------------------------------------------ uninstall
if [[ $UNINSTALL -eq 1 ]]; then
  for rt in "${RUNTIMES[@]}"; do
    IFS='|' read -r name detect agents_dir src skills_dir <<<"$rt"
    # File names, not the source subdir: the OpenCode agents are removed whichever stack installed them.
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

# ------------------------------------------------------------------ OpenCode stack
# The stack name is used as a path component, so it must be a plain directory name: not empty
# (which would resolve to agents/opencode/ itself and install the stack dirs as agent files),
# no slash (../antigravity would install another runtime's files), no leading dot. That also
# keeps the -d test below from being talked into anything outside agents/opencode/.
oc_stack_name_ok() { [[ -n "$1" && "$1" != */* && "$1" != .* ]]; }
if ! oc_stack_name_ok "$OC_STACK" || [[ ! -d "$SRC/agents/opencode/$OC_STACK" ]]; then
  OC_AVAIL=""
  for d in "$SRC/agents/opencode"/*/; do [[ -d "$d" ]] && OC_AVAIL+=" $(basename "$d")"; done
  { printf 'unknown OpenCode stack: %s\n' "$OC_STACK"
    if [[ -n "$OC_AVAIL" ]]; then printf 'available stacks:%s\n' "$OC_AVAIL"
    else printf 'no stacks found in %s (run python3 build.py in the clone)\n' "$SRC/agents/opencode"; fi; } >&2
  exit 2
fi

# ------------------------------------------------------------------ detect runtimes
FOUND=(); MISSING=()
for rt in "${RUNTIMES[@]}"; do IFS='|' read -r name detect _ _ _ <<<"$rt"; if [[ -d "$detect" ]]; then FOUND+=("$rt"); else MISSING+=("$name"); fi; done
[[ ${#FOUND[@]} -eq 0 ]] && { say "No supported runtime found (Claude Code, Codex, Antigravity CLI, OpenCode). Nothing to do."; exit 1; }
say "Runtimes found: $(for rt in "${FOUND[@]}"; do IFS='|' read -r n _ <<<"$rt"; printf '%s; ' "$n"; done)"
[[ ${#MISSING[@]} -gt 0 ]] && say "Not installed (skipped): ${MISSING[*]}"

# ------------------------------------------------------------------ existing installed files -> ask once
EXISTING=()
for rt in "${FOUND[@]}"; do
  IFS='|' read -r name detect agents_dir src skills_dir <<<"$rt"
  for f in "$SRC/agents/$src"/*; do
    dest="$agents_dir/$(basename "$f")"
    [[ -e "$dest" || -L "$dest" ]] || continue
    # A symlinked copy-only (Codex) destination has to be converted to a real file, which is
    # destructive, so it counts as "differs" and goes through the same confirmation.
    if [[ "$MODE" == "link" ]] && ! copy_only "$src"; then same_target "$dest" "$f" && continue
    else [[ ! -L "$dest" ]] && cmp -s "$f" "$dest" && continue; fi
    EXISTING+=("$dest")
  done
done
# The canonical skill directory and the per-runtime pointers to it are replaced in place, so
# anything already there that is not what we would place joins the same one confirmation.
skill_differs() { # 0 = installed and differs from what we would place; 1 = absent or identical
  [[ -e "$CANON" || -L "$CANON" ]] || return 1
  if [[ "$MODE" == "link" ]]; then
    same_target "$CANON" "$SRC/skills/orchestrate" && return 1
  else
    [[ ! -L "$CANON" ]] && diff -qr "$SRC/skills/orchestrate" "$CANON" >/dev/null 2>&1 && return 1
  fi
  return 0
}
CANON_DIFFERS=0; SKILL_DIFFERS=0
if skill_differs; then CANON_DIFFERS=1; SKILL_DIFFERS=1; EXISTING+=("$CANON"); fi
for rt in "${FOUND[@]}"; do
  IFS='|' read -r name detect agents_dir src skills_dir <<<"$rt"
  [[ -n "$skills_dir" ]] || continue          # OpenCode reads ~/.agents/skills itself; no pointer
  link="$skills_dir/orchestrate"
  [[ -e "$link" || -L "$link" ]] || continue  # absent: placed silently below
  if same_target "$link" "$CANON" || points_to "$link" "$CANON"; then continue; fi
  SKILL_DIFFERS=1; EXISTING+=("$link")
done

REPLACE=1
if [[ ${#EXISTING[@]} -gt 0 ]]; then
  subject="Worker agents"; subject_lc="worker agents"
  if [[ $SKILL_DIFFERS -eq 1 ]]; then subject="Installed files"; subject_lc="installed files"; fi
  say "$subject already exist and differ from this version (${#EXISTING[@]} files), e.g. ${EXISTING[0]}"
  if ask "Replace them with the new version (update)?"; then REPLACE=1; else REPLACE=0; say "Keeping existing $subject_lc."; fi
fi
# Declined skill paths: the `skills` CLI relinks every runtime's skills dir itself, so it must not
# run when the user kept one of those.
SKILL_KEEP=0
if [[ $SKILL_DIFFERS -eq 1 && $REPLACE -eq 0 ]]; then SKILL_KEEP=1; fi

place() { # place <src> <dest> [copyonly]   (link or copy depending on MODE; respects REPLACE)
  local s="$1" d="$2" copyonly="${3:-0}"
  if [[ -e "$d" || -L "$d" ]]; then
    if [[ "$copyonly" -eq 1 && -L "$d" ]]; then
      # A symlinked Codex role can never work, but converting it destroys the link, so it
      # needs the same consent as any other replacement.
      if [[ $REPLACE -eq 1 ]]; then
        rm -f "$d"; mkdir -p "$(dirname "$d")"; cp -R "$s" "$d"; say "  replaced symlink $d"
      else
        say "  WARNING: kept symlink $d - Codex cannot load a symlinked role file; re-run with --yes to convert it to a real file."
      fi
      return 0
    fi
    if [[ "$MODE" == "link" && "$copyonly" -ne 1 ]]; then same_target "$d" "$s" && return 0
    else [[ ! -L "$d" ]] && cmp -s "$s" "$d" && return 0; fi
    [[ $REPLACE -eq 1 ]] || return 0
    rm -rf "$d"
  fi
  mkdir -p "$(dirname "$d")"
  if [[ "$MODE" == "link" && "$copyonly" -ne 1 ]]; then ln -s "$s" "$d"; else cp -R "$s" "$d"; fi
  say "  installed $d"
}

# ------------------------------------------------------------------ skill
say "Skill:"
SKILL_VIA_CLI=0
if [[ $CANON_DIFFERS -eq 1 && $REPLACE -eq 0 ]]; then
  say "  kept existing $CANON (not replaced)."
else
  if [[ "$MODE" == "copy" && $SKILL_KEEP -eq 1 ]] && command -v npx >/dev/null 2>&1; then
    say "  skipping the skills CLI: it would relink the skill dirs you chose to keep. Copying $CANON directly. Re-run with --yes to let the skills CLI manage it."
  elif [[ "$MODE" == "copy" ]] && command -v npx >/dev/null 2>&1; then
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
fi

# ------------------------------------------------------------------ per-runtime
for rt in "${FOUND[@]}"; do
  IFS='|' read -r name detect agents_dir src skills_dir <<<"$rt"
  if [[ "$src" == opencode/* ]]; then say "$name (stack: ${src#opencode/}):"; else say "$name:"; fi
  co=0; copy_only "$src" && co=1
  for f in "$SRC/agents/$src"/*; do place "$f" "$agents_dir/$(basename "$f")" "$co"; done
  if [[ -n "$skills_dir" ]]; then
    link="$skills_dir/orchestrate"
    if same_target "$link" "$CANON" || points_to "$link" "$CANON"; then :
    elif [[ ( -e "$link" || -L "$link" ) && $REPLACE -eq 0 ]]; then say "  kept existing $link (not replaced)."
    else rm -rf "$link"; mkdir -p "$skills_dir"; ln -s "$CANON" "$link"; say "  linked $link -> $CANON"; fi
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
  Claude Code      /model -> Fable 5.1 (or Opus 5.5)
  Codex            /model -> GPT-6 Astra if available, else GPT-6 Sol
  Antigravity CLI  session model -> Gemini 3.1 Pro (High)
  OpenCode         the 'orchestrate' primary agent pins its model in agents/opencode/$OC_STACK/orchestrate.md
                   (installed stack: $OC_STACK; re-run with --opencode-stack=<name> to switch)

Update later: re-run this command$( [[ "$MODE" == "link" ]] && printf ', or git pull in the clone' ).
EOF
}

# Everything above is parsed before this line runs, so `curl | bash` cannot be cut short by a child reading stdin.
main "$@"
