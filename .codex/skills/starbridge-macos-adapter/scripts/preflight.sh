#!/bin/zsh
set -u

soft_exit=0
repo_override=""

while (( $# > 0 )); do
  case "$1" in
    --soft-exit)
      soft_exit=1
      shift
      ;;
    --repo)
      (( $# >= 2 )) || { print -u2 -- "--repo requires a path"; exit 2; }
      repo_override="$2"
      shift 2
      ;;
    -h|--help)
      print -- "Usage: $0 [--repo PATH] [--soft-exit]"
      exit 0
      ;;
    *)
      print -u2 -- "Unknown option: $1"
      exit 2
      ;;
  esac
done

script_dir="${0:A:h}"
default_repo="${script_dir:h:h:h:h}"
repo_root="${repo_override:-$default_repo}"
repo_root="${repo_root:A}"
failures=0

pass() { print -- "PASS $1"; }
warn() { print -- "WARN $1"; }
fail() { print -- "FAIL $1"; failures=$((failures + 1)); }

if [[ "$(uname -s)" == "Darwin" ]]; then
  pass "platform=macOS"
else
  fail "platform=unsupported expected=Darwin actual=$(uname -s)"
fi

pass "architecture=$(uname -m)"

if [[ -f "$repo_root/pyproject.toml" && -f "$repo_root/package.json" && -d "$repo_root/starbridge_mcp" ]]; then
  pass "repository=$(basename "$repo_root")"
else
  fail "repository=invalid use --repo with the CreNexus checkout"
fi

for command_name in python3 node npm git; do
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "$command_name=available"
  else
    warn "$command_name=missing"
  fi
done

for relative_path in \
  "scripts/security_check.py" \
  "scripts/starbridge_preflight.py" \
  "examples/bridge_status.py" \
  "node_proxy/illustrator-bridge/package.json" \
  "plugins/starbridge-version-coordinator/scripts/version_coordinator_mcp.py"; do
  if [[ -f "$repo_root/$relative_path" ]]; then
    pass "file=$relative_path"
  else
    fail "file_missing=$relative_path"
  fi
done

if [[ -x "$repo_root/.venv/bin/python" ]]; then
  pass "python_venv=ready"
else
  warn "python_venv=missing"
fi

if git -C "$repo_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ -n "$(git -C "$repo_root" status --porcelain 2>/dev/null)" ]]; then
    warn "git_worktree=dirty preserve_existing_changes"
  else
    pass "git_worktree=clean"
  fi
else
  fail "git_worktree=unavailable"
fi

if (( failures > 0 )); then
  print -- "RESULT not_ready failures=$failures"
  (( soft_exit )) && exit 0
  exit 1
fi

print -- "RESULT ready failures=0"
