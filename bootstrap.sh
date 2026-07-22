#!/usr/bin/env bash
# Cross-platform bootstrap for the safe Python/MCP path. It deliberately does
# not install system packages or start the Tauri desktop runtime.
set -euo pipefail

profile="auto"
skip_node=0
skip_codex_config=0
dry_run=0
json=0

step_names=()
step_statuses=()
step_details=()
warnings=()
isolated_environment=()

usage() {
    cat <<'EOF'
Usage: bash ./bootstrap.sh [options]

Create a repository-local Python environment, install the selected public
CreNexus extras, write the safe local Codex MCP configuration, and run the
safe Python checks.

Options:
  --profile PROFILE       auto, core, standard, or all (default: auto)
  --skip-node             Do not install optional Node bridge dependencies
  --skip-codex-config     Do not write .codex/config.toml
  --dry-run               Show the planned reversible operations only
  --json                  Emit a machine-readable result
  -h, --help              Show this help

macOS notes: Homebrew, Xcode Command Line Tools, Rosetta, and desktop software
are never installed or changed by this script. The script only reports missing
prerequisites and continues with the safe core path when possible. It never
invokes the Tauri desktop application or npm.cmd.
EOF
}

die() {
    printf 'CreNexus bootstrap failed: %s\n' "$*" >&2
    exit 1
}

warn() {
    warnings+=("$1")
    if (( ! json )); then
        printf 'WARN: %s\n' "$1" >&2
    fi
}

add_step() {
    step_names+=("$1")
    step_statuses+=("$2")
    step_details+=("$3")
}

command_display() {
    local part separator=""
    for part in "$@"; do
        printf '%s' "$separator"
        if [[ "$part" == *[[:space:]]* ]]; then
            printf '"%s"' "${part//\"/\\\"}"
        else
            printf '%s' "$part"
        fi
        separator=" "
    done
}

run_step() {
    local name="$1"
    shift
    local detail
    detail="$(command_display "$@")"

    if (( dry_run )); then
        add_step "$name" "planned" "$detail"
        return
    fi

    if (( json )); then
        local captured
        if ! captured="$("$@" 2>&1)"; then
            die "$name failed: $captured"
        fi
        add_step "$name" "completed" "${captured##*$'\n'}"
        return
    fi

    "$@"
    add_step "$name" "completed" "$detail"
}

prepare_python_environment() {
    local variable
    isolated_environment=(env)
    while IFS= read -r variable; do
        case "$variable" in
            PYTHON*|__PYVENV_LAUNCHER__) isolated_environment+=(-u "$variable") ;;
        esac
    done < <(compgen -e)
}

run_python_isolated() {
    local interpreter="$1"
    shift
    prepare_python_environment
    "${isolated_environment[@]}" "$interpreter" -I "$@"
}

run_python_step() {
    local name="$1" interpreter="$2"
    shift 2
    prepare_python_environment
    run_step "$name" "${isolated_environment[@]}" "$interpreter" -I "$@"
}

prepare_pip_environment() {
    local variable
    prepare_python_environment

    # PIP_CONFIG_FILE=os.devnull is pip's documented way to disable global,
    # user, site, and explicitly selected configuration files.  Do not use
    # --isolated here: it would also discard proxy, certificate, index, and
    # other network settings that a legitimate installation may require.
    # Instead, pass through a narrow network/authentication allowlist and
    # remove every other PIP_* option so no inherited option can redirect the
    # interpreter, install scheme, requirements, report, or log destination.
    while IFS= read -r variable; do
        case "$variable" in
            PIP_INDEX_URL|PIP_EXTRA_INDEX_URL|PIP_NO_INDEX|PIP_FIND_LINKS|\
            PIP_TRUSTED_HOST|PIP_PROXY|PIP_CERT|PIP_CLIENT_CERT|\
            PIP_TIMEOUT|PIP_DEFAULT_TIMEOUT|PIP_RETRIES|PIP_RESUME_RETRIES|\
            PIP_DISABLE_PIP_VERSION_CHECK|PIP_NO_INPUT|PIP_KEYRING_PROVIDER|\
            PIP_NETRC|PIP_REQUIRE_VIRTUALENV|PIP_REQUIRE_VENV)
                ;;
            PIP_*)
                isolated_environment+=(-u "$variable")
                ;;
        esac
    done < <(compgen -e)
    isolated_environment+=(PIP_CONFIG_FILE=/dev/null)
}

run_pip_step() {
    local name="$1"
    shift
    prepare_pip_environment

    # Python -I also blocks PYTHONPATH/PYTHONHOME/user-site injection without
    # affecting the local project path passed explicitly to pip.
    run_step "$name" "${isolated_environment[@]}" "$venv_python" -I -m pip "$@"
}

toml_escape() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '%s' "$value"
}

json_escape() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    printf '%s' "$value"
}

json_string_array() {
    local value
    local first=1
    printf '['
    for value in "$@"; do
        (( first )) || printf ','
        first=0
        printf '"%s"' "$(json_escape "$value")"
    done
    printf ']'
}

json_steps() {
    local index
    printf '['
    for index in "${!step_names[@]}"; do
        (( index == 0 )) || printf ','
        printf '{"name":"%s","status":"%s","detail":"%s"}' \
            "$(json_escape "${step_names[index]}")" \
            "$(json_escape "${step_statuses[index]}")" \
            "$(json_escape "${step_details[index]}")"
    done
    printf ']'
}

emit_result() {
    local codex_config_json="null"
    if (( ! skip_codex_config )); then
        codex_config_json='".codex/config.toml"'
    fi

    if (( json )); then
        printf '{\n'
        printf '  "ok": true,\n'
        printf '  "repo": "%s",\n' "$(json_escape "$repo_root")"
        printf '  "profile_requested": "%s",\n' "$(json_escape "$profile")"
        printf '  "profile_applied": "%s",\n' "$(json_escape "$effective_profile")"
        printf '  "python": "%s",\n' "$(json_escape "$python_version")"
        printf '  "venv": ".venv/bin/python",\n'
        printf '  "extras": '
        json_string_array "${extras[@]}"
        printf ',\n  "codex_config": %s,\n' "$codex_config_json"
        printf '  "steps": '
        json_steps
        printf ',\n  "warnings": '
        json_string_array "${warnings[@]}"
        printf ',\n  "next": ["Open a new Codex task in this repository so it reloads .codex/config.toml.","Use the version coordinator to probe capabilities; software version is advisory, not a whitelist.","Run bash ./bootstrap.sh --profile standard or --profile all when you need optional bridge dependencies."]\n'
        printf '}\n'
        return
    fi

    printf 'CreNexus bootstrap completed (%s).\n' "$effective_profile"
    printf 'Python: %s\n' "$python_version"
    printf 'Virtual environment: %s\n' "$venv_path"
    if (( skip_codex_config )); then
        printf 'Codex config: skipped\n'
    else
        printf 'Codex config: %s\n' "$config_path"
    fi
    local index
    for index in "${!step_names[@]}"; do
        printf -- '- %s: %s\n' "${step_names[index]}" "${step_statuses[index]}"
    done
    printf 'Next: start a new Codex task in this repository.\n'
}

feature_hint_present() {
    local name
    for name in PHOTOSHOP_EXE ILLUSTRATOR_EXE AUTOCAD_EXE BLENDER_EXE COMFY_ROOT \
        STARBRIDGE_COMFYUI_URL JIANYING_EXE CAPCUT_EXE; do
        if [[ -n "${!name:-}" ]]; then
            return 0
        fi
    done
    for name in blender acad photoshop illustrator jianying capcut; do
        if command -v "$name" >/dev/null 2>&1; then
            return 0
        fi
    done
    return 1
}

find_python() {
    local candidate version major minor
    for candidate in python3 python; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        version="$(run_python_isolated "$candidate" --version 2>&1 || true)"
        if [[ "$version" =~ Python[[:space:]]+([0-9]+)\.([0-9]+) ]]; then
            major="${BASH_REMATCH[1]}"
            minor="${BASH_REMATCH[2]}"
            if (( major > 3 || (major == 3 && minor >= 10) )); then
                python_command="$candidate"
                python_version="$version"
                return
            fi
        fi
    done
    die "Python 3.10+ was not found. Install Python manually, then run this command again."
}

validate_repository_path() {
    local control_byte control_code escaped
    # NUL cannot appear in a POSIX path. Reject the other C0 controls and DEL
    # before building TOML so a failed bootstrap leaves configuration untouched.
    for control_code in {1..31} 127; do
        printf -v escaped '\\%03o' "$control_code"
        printf -v control_byte '%b' "$escaped"
        if [[ "$repo_root" == *"$control_byte"* ]]; then
            die "Repository paths containing ASCII control characters are not supported; rename or move the checkout before bootstrapping."
        fi
    done
}

physical_directory() {
    (cd -P -- "$1" 2>/dev/null && pwd -P)
}

validate_repo_directory() {
    local label="$1"
    local path="$2"
    local required="$3"
    local physical

    if [[ -L "$path" ]]; then
        die "$label must be a real directory inside the repository; symlinks are not allowed."
    fi
    if [[ ! -e "$path" ]]; then
        if (( required )); then
            die "$label was not created inside the repository."
        fi
        return
    fi
    if [[ ! -d "$path" ]]; then
        die "$label must be a real directory inside the repository."
    fi
    physical="$(physical_directory "$path")" \
        || die "$label could not be resolved to a physical repository path."
    if [[ "$physical" != "$path" ]]; then
        die "$label must resolve exactly to $path; external or aliased directories are not allowed."
    fi
    case "$physical" in
        "$repo_root"/*) ;;
        *) die "$label must remain inside the physical repository root." ;;
    esac
}

validate_config_target() {
    if [[ -e "$config_path" || -L "$config_path" ]]; then
        if [[ -L "$config_path" || ! -f "$config_path" ]]; then
            die ".codex/config.toml must be a regular non-symlink file; no configuration changes were made."
        fi
    fi
}

validate_existing_local_paths() {
    validate_repo_directory ".codex" "$config_dir" 0
    validate_config_target
    validate_repo_directory ".venv" "$venv_path" 0
}

ensure_config_directory() {
    if [[ ! -e "$config_dir" && ! -L "$config_dir" ]]; then
        if ! mkdir -- "$config_dir"; then
            die "Could not create the repository-local .codex directory."
        fi
    fi
    validate_repo_directory ".codex" "$config_dir" 1
    validate_config_target
}

validate_venv_identity() {
    local expected_prefix identity identity_code reported_prefix reported_base_prefix
    local reported_version major minor candidate python_dir site_packages
    local identity_lines=()
    validate_repo_directory ".venv" "$venv_path" 1
    if [[ -L "$venv_path/pyvenv.cfg" || ! -f "$venv_path/pyvenv.cfg" ]]; then
        die ".venv must contain a regular repository-local pyvenv.cfg before its Python is used."
    fi

    validate_repo_directory ".venv/bin" "$venv_path/bin" 1
    validate_repo_directory ".venv/lib" "$venv_path/lib" 1
    if [[ -e "$venv_path/include" || -L "$venv_path/include" ]]; then
        validate_repo_directory ".venv/include" "$venv_path/include" 1
    fi
    for python_dir in "$venv_path/lib"/python*; do
        if [[ -e "$python_dir" || -L "$python_dir" ]]; then
            validate_repo_directory ".venv/lib Python directory" "$python_dir" 1
            site_packages="$python_dir/site-packages"
            if [[ -e "$site_packages" || -L "$site_packages" ]]; then
                validate_repo_directory ".venv site-packages" "$site_packages" 1
            fi
        fi
    done
    if [[ ! -f "$venv_python" || ! -x "$venv_python" ]]; then
        die "The virtual environment exists but does not contain an executable $venv_python. Remove it manually only if it is safe to do so, then rerun."
    fi
    expected_prefix="$(physical_directory "$venv_path")" \
        || die "The repository-local .venv path could not be resolved."
    identity_code='import os
import platform
import sys
import sysconfig

from pip._internal.locations import get_scheme

if sys.prefix == sys.base_prefix:
    raise SystemExit(2)
scheme = get_scheme("starbridge-bootstrap-probe")
values = (
    os.path.realpath(sys.prefix),
    os.path.realpath(sys.base_prefix),
    "Python " + platform.python_version(),
    os.path.realpath(sysconfig.get_path("scripts")),
    os.path.realpath(sysconfig.get_path("purelib")),
    os.path.realpath(sysconfig.get_path("platlib")),
    os.path.realpath(sysconfig.get_path("data")),
    os.path.realpath(sysconfig.get_path("include")),
    os.path.realpath(scheme.scripts),
    os.path.realpath(scheme.purelib),
    os.path.realpath(scheme.platlib),
    os.path.realpath(scheme.data),
    os.path.realpath(scheme.headers),
)
if any(not isinstance(value, str) or not value or "\n" in value or "\r" in value for value in values):
    raise SystemExit(3)
print("\n".join(values))  # STARBRIDGE_VENV_PREFIX_CHECK'
    if ! identity="$(run_python_isolated "$venv_python" -c "$identity_code" 2>/dev/null)"; then
        die ".venv Python did not identify itself as an isolated virtual environment; no dependency commands were run."
    fi
    while IFS= read -r candidate; do
        identity_lines[${#identity_lines[@]}]="$candidate"
    done <<< "$identity"
    if (( ${#identity_lines[@]} != 13 )); then
        die ".venv Python returned an incomplete installation scheme; no dependency commands were run."
    fi
    reported_prefix="${identity_lines[0]}"
    reported_base_prefix="${identity_lines[1]}"
    reported_version="${identity_lines[2]}"
    if [[ "$reported_prefix" != "$expected_prefix" ]]; then
        die ".venv Python reported sys.prefix outside the repository-local .venv; no dependency commands were run."
    fi
    if [[ "$reported_base_prefix" == "$reported_prefix" || "$reported_base_prefix" != /* ]]; then
        die ".venv Python reported an invalid sys.base_prefix; no dependency commands were run."
    fi
    if [[ "$reported_version" =~ ^Python[[:space:]]+([0-9]+)\.([0-9]+) ]]; then
        major="${BASH_REMATCH[1]}"
        minor="${BASH_REMATCH[2]}"
    else
        die ".venv Python reported an invalid version; no dependency commands were run."
    fi
    if (( major < 3 || (major == 3 && minor < 10) )); then
        die ".venv Python must be Python 3.10 or newer; no dependency commands were run."
    fi

    # sysconfig scripts/purelib/platlib/data and pip's actual writable install
    # scheme must resolve into this venv.  sysconfig include may identify the
    # base interpreter's read-only headers, while pip's headers target below
    # is the location an installation can actually write.
    for candidate in "${identity_lines[3]}" "${identity_lines[4]}" "${identity_lines[5]}" \
        "${identity_lines[6]}" "${identity_lines[8]}" "${identity_lines[9]}" \
        "${identity_lines[10]}" "${identity_lines[11]}" "${identity_lines[12]}"; do
        case "$candidate" in
            "$expected_prefix"|"$expected_prefix"/*) ;;
            *) die ".venv installation scheme resolved outside the repository-local .venv; no dependency commands were run." ;;
        esac
    done
    case "${identity_lines[7]}" in
        "$expected_prefix"|"$expected_prefix"/*|"$reported_base_prefix"|"$reported_base_prefix"/*) ;;
        *) die ".venv sysconfig include path was unrelated to the venv or its base interpreter; no dependency commands were run." ;;
    esac
    python_version="$reported_version"
}

check_platform_prerequisites() {
    local platform architecture
    platform="$(uname -s)"
    architecture="$(uname -m)"
    case "$platform" in
        Darwin|Linux) ;;
        *) die "Unsupported platform: $platform. Use bootstrap.ps1 on Windows." ;;
    esac

    if ! command -v git >/dev/null 2>&1; then
        warn "Git was not found. Bootstrap can continue, but clone/update operations must be done manually."
    fi

    if [[ "$platform" == "Darwin" ]]; then
        if ! command -v brew >/dev/null 2>&1; then
            warn "Homebrew was not found. It is optional and will not be installed automatically; install Python/Node manually if they are missing."
        fi
        if ! xcode-select -p >/dev/null 2>&1; then
            warn "Xcode Command Line Tools were not found. They are not installed automatically; some native Python packages may require a manual installation."
        fi
        if [[ "$architecture" == "arm64" ]] && ! /usr/bin/arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
            warn "Rosetta 2 is unavailable. It is only needed for Intel-only third-party tools and will not be installed automatically."
        fi
    fi
}

toml_file_is_valid() {
    local file_path="$1"
    run_python_isolated "$venv_python" - "$file_path" >/dev/null 2>&1 <<'PY'
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

with Path(sys.argv[1]).open("rb") as source:
    tomllib.load(source)
PY
}

prepare_config_base() {
    local file_path="$1"
    run_python_isolated "$venv_python" - "$file_path" "$venv_python" "$repo_root" \
        "$repo_root/plugins/starbridge-version-coordinator/scripts/version_coordinator_mcp.py" <<'PY'
import copy
import io
import ntpath
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

source_path, python_path, repo_root, coordinator_path = sys.argv[1:]
data = Path(source_path).read_bytes()

try:
    document = tomllib.load(io.BytesIO(data))
    text = data.decode("utf-8")
except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
    raise SystemExit(1)

begin_markers = {
    "# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh)": ("newline", "posix"),
    "# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh; prefix-lf=0)": (
        "none",
        "posix",
    ),
    "# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh; prefix-lf=1)": (
        "newline",
        "posix",
    ),
    "# BEGIN STARBRIDGE QUICKSTART (managed by scripts/quickstart.ps1)": (
        "newline",
        "windows",
    ),
}
end_marker = "# END STARBRIDGE QUICKSTART"


def advance_toml_lexical_state(line: str, state: str | None) -> str | None:
    index = 0
    while index < len(line):
        if state == "multiline_basic":
            if line.startswith('"""', index):
                backslashes = 0
                cursor = index - 1
                while cursor >= 0 and line[cursor] == "\\":
                    backslashes += 1
                    cursor -= 1
                if backslashes % 2 == 0:
                    state = None
                    index += 3
                    continue
            index += 1
            continue
        if state == "multiline_literal":
            if line.startswith("'''", index):
                state = None
                index += 3
                continue
            index += 1
            continue

        character = line[index]
        if character == "#":
            break
        if line.startswith('"""', index):
            state = "multiline_basic"
            index += 3
            continue
        if line.startswith("'''", index):
            state = "multiline_literal"
            index += 3
            continue
        if character == '"':
            index += 1
            while index < len(line):
                if line[index] == "\\":
                    index += 2
                elif line[index] == '"':
                    index += 1
                    break
                else:
                    index += 1
            continue
        if character == "'":
            end = line.find("'", index + 1)
            index = len(line) if end == -1 else end + 1
            continue
        index += 1
    return state


starts: list[tuple[int, int, str, str]] = []
ends: list[tuple[int, int]] = []
offset = 0
state: str | None = None
for line in text.splitlines(keepends=True):
    body = line.rstrip("\r\n")
    if state is None:
        if body in begin_markers:
            separator, schema = begin_markers[body]
            starts.append((offset, offset + len(line), separator, schema))
        elif body == end_marker:
            ends.append((offset, offset + len(line)))
    state = advance_toml_lexical_state(line, state)
    offset += len(line)

if state is not None:
    raise SystemExit(1)

if not starts and not ends:
    sys.stdout.buffer.write(data)
    raise SystemExit(0)
if len(starts) != 1 or len(ends) != 1:
    raise SystemExit(1)

start_offset, _, separator, schema = starts[0]
end_offset, end_after = ends[0]
if end_offset <= start_offset:
    raise SystemExit(1)
if separator == "none" and start_offset != 0:
    raise SystemExit(1)
remove_start = start_offset
if separator == "newline":
    if text[:remove_start].endswith("\r\n"):
        remove_start -= 2
    elif text[:remove_start].endswith("\n"):
        remove_start -= 1
    else:
        raise SystemExit(1)

base_text = text[:remove_start] + text[end_after:]
base_data = base_text.encode("utf-8")
try:
    base_document = tomllib.load(io.BytesIO(base_data))
except tomllib.TOMLDecodeError:
    raise SystemExit(1)

servers = document.get("mcp_servers")
if not isinstance(servers, dict):
    raise SystemExit(1)
safe_environment = {
    "STARBRIDGE_PHOTOSHOP_SAFE_ONLY": "1",
    "STARBRIDGE_PHOTOSHOP_DEFAULT_DRY_RUN": "1",
    "STARBRIDGE_PHOTOSHOP_ALLOW_DESTRUCTIVE": "0",
}


def canonical_windows_root(value: object) -> str:
    if not isinstance(value, str) or not value or "/" in value:
        raise ValueError
    if any(ord(character) < 32 or character in '<>"|?*' for character in value):
        raise ValueError
    drive, tail = ntpath.splitdrive(value)
    def validate_segment(segment: str) -> None:
        if (
            not segment
            or segment in (".", "..")
            or segment.endswith((" ", "."))
            or ":" in segment
        ):
            raise ValueError
        # Win32 device matching also ignores an extension and normalizes
        # spaces/dots immediately before it (for example, "CON .txt").
        device_stem = segment.split(".", 1)[0].rstrip(" .").upper()
        if device_stem in {"CON", "PRN", "AUX", "NUL"}:
            raise ValueError
        if re.fullmatch(r"(?:COM|LPT)(?:[1-9¹²³])", device_stem):
            raise ValueError
        if device_stem in {"CONIN$", "CONOUT$"}:
            raise ValueError

    if value.startswith("\\\\"):
        share_parts = drive[2:].split("\\")
        if len(share_parts) != 2 or not all(share_parts):
            raise ValueError
        if ":" in drive or (tail and not tail.startswith("\\")):
            raise ValueError
        for share_part in share_parts:
            validate_segment(share_part)
        root_only = tail in ("", "\\")
    else:
        if not re.fullmatch(r"[A-Z]:", drive) or not tail.startswith("\\"):
            raise ValueError
        root_only = tail == "\\"
        if ":" in tail:
            raise ValueError
    if ntpath.normpath(value) != value:
        raise ValueError
    if value.endswith("\\") and not root_only:
        raise ValueError
    segments = [segment for segment in tail.split("\\") if segment]
    for segment in segments:
        validate_segment(segment)
    return value


if schema == "windows":
    managed = servers.get("starbridge")
    if not isinstance(managed, dict):
        raise SystemExit(1)
    try:
        managed_root = canonical_windows_root(managed.get("cwd"))
    except ValueError:
        raise SystemExit(1)
    managed_python = ntpath.join(managed_root, ".venv", "Scripts", "python.exe")
    managed_coordinator = ntpath.join(
        managed_root,
        "plugins",
        "starbridge-version-coordinator",
        "scripts",
        "version_coordinator_mcp.py",
    )
    expected_starbridge = {
        "command": managed_python,
        "args": ["-m", "starbridge_mcp.mcp_server"],
        "cwd": managed_root,
        "env": safe_environment,
    }
    expected_coordinator = {
        "command": managed_python,
        "args": [managed_coordinator],
        "cwd": managed_root,
    }
else:
    expected_starbridge = {
        "command": python_path,
        "args": ["-m", "starbridge_mcp.mcp_server"],
        "cwd": repo_root,
        "env": safe_environment,
    }
    expected_coordinator = {
        "command": python_path,
        "args": [coordinator_path],
        "cwd": repo_root,
    }
if servers.get("starbridge") != expected_starbridge:
    raise SystemExit(1)
if servers.get("starbridge-version-coordinator") != expected_coordinator:
    raise SystemExit(1)

normalized = copy.deepcopy(document)
normalized_servers = normalized["mcp_servers"]
del normalized_servers["starbridge"]
del normalized_servers["starbridge-version-coordinator"]
if not normalized_servers and "mcp_servers" not in base_document:
    del normalized["mcp_servers"]
if normalized != base_document:
    raise SystemExit(1)

sys.stdout.buffer.write(base_data)
PY
}

external_mcp_config_is_unclaimed() {
    local file_path="$1"
    run_python_isolated "$venv_python" - "$file_path" >/dev/null 2>&1 <<'PY'
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

with Path(sys.argv[1]).open("rb") as source:
    document = tomllib.load(source)

servers = document.get("mcp_servers")
if servers is not None:
    if not isinstance(servers, dict):
        raise SystemExit(1)
    if "starbridge" in servers or "starbridge-version-coordinator" in servers:
        raise SystemExit(1)
PY
}

write_codex_config() {
    if (( skip_codex_config )); then
        add_step "configure Codex MCP" "skipped" "--skip-codex-config"
        return
    fi
    if (( dry_run )); then
        add_step "configure Codex MCP" "planned" "$config_path"
        return
    fi

    ensure_config_directory

    local temporary_config temporary_parent
    if ! temporary_config="$(mktemp "$config_dir/.config.toml.XXXXXX")"; then
        die "Could not create a repository-local temporary Codex configuration."
    fi
    temporary_parent="$(physical_directory "$(dirname -- "$temporary_config")")" || {
        rm -f -- "$temporary_config"
        die "Could not verify the temporary Codex configuration parent directory."
    }
    if [[ "$temporary_parent" != "$config_dir" || -L "$temporary_config" || ! -f "$temporary_config" ]]; then
        rm -f -- "$temporary_config"
        die "The temporary Codex configuration escaped the verified repository-local .codex directory."
    fi
    if [[ -f "$config_path" ]]; then
        if ! prepare_config_base "$config_path" > "$temporary_config"; then
            rm -f -- "$temporary_config"
            die "Existing .codex/config.toml has invalid TOML or an ambiguous managed block; no configuration changes were made."
        fi
    else
        : > "$temporary_config"
    fi

    if ! toml_file_is_valid "$temporary_config"; then
        rm -f -- "$temporary_config"
        die "Existing .codex/config.toml outside the managed block is not valid TOML; no configuration changes were made."
    fi
    if ! external_mcp_config_is_unclaimed "$temporary_config"; then
        rm -f -- "$temporary_config"
        die "Existing .codex/config.toml already defines a Starbridge MCP server or a conflicting mcp_servers structure; refusing to overwrite it."
    fi

    local python_toml root_toml coordinator_toml prefix_lf begin_marker
    python_toml="$(toml_escape "$venv_python")"
    root_toml="$(toml_escape "$repo_root")"
    coordinator_toml="$(toml_escape "$repo_root/plugins/starbridge-version-coordinator/scripts/version_coordinator_mcp.py")"
    prefix_lf=0
    if [[ -s "$temporary_config" ]]; then
        prefix_lf=1
    fi
    begin_marker="# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh; prefix-lf=$prefix_lf)"
    if ! {
        if (( prefix_lf )); then
            printf '\n'
        fi
        cat <<EOF
$begin_marker
[mcp_servers.starbridge]
command = "$python_toml"
args = ["-m", "starbridge_mcp.mcp_server"]
cwd = "$root_toml"

[mcp_servers.starbridge.env]
STARBRIDGE_PHOTOSHOP_SAFE_ONLY = "1"
STARBRIDGE_PHOTOSHOP_DEFAULT_DRY_RUN = "1"
STARBRIDGE_PHOTOSHOP_ALLOW_DESTRUCTIVE = "0"

[mcp_servers.starbridge-version-coordinator]
command = "$python_toml"
args = ["$coordinator_toml"]
cwd = "$root_toml"
# END STARBRIDGE QUICKSTART
EOF
    } >> "$temporary_config"; then
        rm -f -- "$temporary_config"
        die "Could not generate .codex/config.toml; no configuration changes were made."
    fi
    if ! toml_file_is_valid "$temporary_config"; then
        rm -f -- "$temporary_config"
        die "Generated .codex/config.toml is not valid TOML; no configuration changes were made."
    fi
    if ! run_python_isolated "$venv_python" - "$temporary_config" "$config_path" >/dev/null 2>&1 <<'PY'
import os
import stat
import sys

source, destination = sys.argv[1:]
try:
    target = os.lstat(destination)
except FileNotFoundError:
    target = None

if target is not None and (stat.S_ISLNK(target.st_mode) or not stat.S_ISREG(target.st_mode)):
    raise SystemExit(1)
os.replace(source, destination)
target = os.lstat(destination)
if stat.S_ISLNK(target.st_mode) or not stat.S_ISREG(target.st_mode):
    raise SystemExit(1)
PY
    then
        rm -f -- "$temporary_config"
        die "Could not atomically replace .codex/config.toml; no configuration changes were made."
    fi
    add_step "configure Codex MCP" "completed" "$config_path"
}

install_node_bridges() {
    if (( skip_node )); then
        add_step "install optional Node bridge dependencies" "skipped" "--skip-node"
        return
    fi
    if [[ "$effective_profile" != "standard" && "$effective_profile" != "all" ]]; then
        add_step "install optional Node bridge dependencies" "skipped_profile" "$effective_profile"
        return
    fi
    if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
        warn "Node.js/npm were not found; optional Node bridge dependencies were not installed. Python/MCP flows remain available."
        return
    fi

    local proxy_root package_lock
    for proxy_root in "$repo_root/node_proxy/photoshop-bridge" "$repo_root/node_proxy/illustrator-bridge"; do
        [[ -f "$proxy_root/package.json" ]] || continue
        package_lock="$proxy_root/package-lock.json"
        if [[ -f "$package_lock" ]]; then
            run_step "install Node bridge $(basename "$proxy_root")" npm ci --prefix "$proxy_root" --no-audit --no-fund
        else
            run_step "install Node bridge $(basename "$proxy_root")" npm install --prefix "$proxy_root" --no-package-lock --no-audit --no-fund
        fi
    done
}

while (( $# > 0 )); do
    case "$1" in
        --profile)
            (( $# >= 2 )) || die "--profile requires a value"
            profile="$2"
            shift 2
            ;;
        --profile=*)
            profile="${1#*=}"
            shift
            ;;
        --skip-node)
            skip_node=1
            shift
            ;;
        --skip-codex-config)
            skip_codex_config=1
            shift
            ;;
        --dry-run)
            dry_run=1
            shift
            ;;
        --json)
            json=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *) die "Unknown option: $1" ;;
    esac
done

case "$profile" in
    auto|core|standard|all) ;;
    *) die "Invalid profile '$profile'. Choose auto, core, standard, or all." ;;
esac

script_dir="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$script_dir"
[[ -f "$repo_root/pyproject.toml" && -f "$repo_root/package.json" && -d "$repo_root/starbridge_mcp" ]] \
    || die "bootstrap.sh must run from a CreNexus repository checkout."

venv_path="$repo_root/.venv"
venv_python="$venv_path/bin/python"
config_dir="$repo_root/.codex"
config_path="$config_dir/config.toml"

validate_repository_path
validate_existing_local_paths
check_platform_prerequisites

effective_profile="$profile"
if [[ "$profile" == "auto" ]]; then
    if feature_hint_present; then
        effective_profile="standard"
    else
        effective_profile="core"
    fi
fi

extras=(dev vectorization)
if [[ "$effective_profile" == "standard" || "$effective_profile" == "all" ]]; then
    extras+=(cad comfy adobe illustrator-vector)
fi
if [[ "$effective_profile" == "all" ]]; then
    extras+=(illustrator-trace vector-refinement vector-app)
fi
extras_csv="$(IFS=,; printf '%s' "${extras[*]}")"

if [[ -d "$venv_path" ]]; then
    add_step "create virtual environment" "skipped_existing" "$venv_path"
    if (( dry_run )); then
        python_version="not probed (existing .venv; dry-run)"
    else
        validate_venv_identity
    fi
else
    find_python
    run_python_step "create virtual environment" "$python_command" -m venv "$venv_path"
    if (( ! dry_run )); then
        validate_venv_identity
    fi
fi

run_pip_step "upgrade pip" install --upgrade pip
run_pip_step "install Python extras" install ".[${extras_csv}]"
install_node_bridges
write_codex_config

if [[ "$effective_profile" == "standard" || "$effective_profile" == "all" ]]; then
    warn "Desktop software is not probed, installed, opened, or granted permissions by bootstrap.sh; verify optional desktop capabilities separately."
fi

run_python_step "verify Python package" "$venv_python" -c "import starbridge_mcp; print('starbridge_mcp import: ok')"
run_python_step "verify version coordinator" "$venv_python" "$repo_root/plugins/starbridge-version-coordinator/scripts/version_coordinator_mcp.py" self-test
run_python_step "verify safe MCP tools" "$venv_python" -m starbridge_mcp.server tools --json --safe-only

emit_result
