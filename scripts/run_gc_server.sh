#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

usage() {
    cat >&2 <<'EOF'
Usage:
  run_gc_server.sh --server-root PATH [options] [-- SERVER_ARGS...]

Options:
  --server-root PATH   External Linux Squad server installation (required)
  --preload PATH       Observer .so path; default is ../tools beside server-root
  --port PORT          Game port (default: 7787)
  --query-port PORT    Query port (default: 27165)
  --multi-home HOST    Bind address (default: 127.0.0.1)
  -h, --help           Show this help

Arguments after --, and unrecognised arguments, are passed to SquadGameServer.sh.
The server root and generated helper must be outside this Git checkout.
EOF
}

die() {
    printf 'run_gc_server.sh: %s\n' "$*" >&2
    exit 2
}

require_value() {
    (($# >= 2)) || die "missing value for $1"
    [[ -n $2 ]] || die "empty value for $1"
}

valid_port() {
    local value=$1
    [[ $value =~ ^[0-9]{1,5}$ ]] || return 1
    ((10#$value >= 1 && 10#$value <= 65535))
}

path_is_in_repo() {
    local candidate=$1
    [[ $candidate == "$repo_root" || $candidate == "$repo_root/"* ]]
}

server_root=''
preload=''
port=7787
query_port=27165
multi_home=127.0.0.1
server_args=()

while (($# > 0)); do
    case $1 in
        --server-root)
            require_value "$1" "${2-}"
            server_root=$2
            shift 2
            ;;
        --server-root=*)
            server_root=${1#*=}
            [[ -n $server_root ]] || die 'empty value for --server-root'
            shift
            ;;
        --preload)
            require_value "$1" "${2-}"
            preload=$2
            shift 2
            ;;
        --preload=*)
            preload=${1#*=}
            [[ -n $preload ]] || die 'empty value for --preload'
            shift
            ;;
        --port)
            require_value "$1" "${2-}"
            port=$2
            shift 2
            ;;
        --port=*)
            port=${1#*=}
            [[ -n $port ]] || die 'empty value for --port'
            shift
            ;;
        --query-port)
            require_value "$1" "${2-}"
            query_port=$2
            shift 2
            ;;
        --query-port=*)
            query_port=${1#*=}
            [[ -n $query_port ]] || die 'empty value for --query-port'
            shift
            ;;
        --multi-home)
            require_value "$1" "${2-}"
            multi_home=$2
            shift 2
            ;;
        --multi-home=*)
            multi_home=${1#*=}
            [[ -n $multi_home ]] || die 'empty value for --multi-home'
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            server_args+=("$@")
            break
            ;;
        *)
            # This keeps normal Squad flags such as -log and -unattended
            # usable without making the wrapper know every server option.
            server_args+=("$1")
            shift
            ;;
    esac
done

[[ -n $server_root ]] || die '--server-root is required'
valid_port "$port" || die "invalid --port: $port"
valid_port "$query_port" || die "invalid --query-port: $query_port"
((10#$port != 10#$query_port)) || die '--port and --query-port must differ'
[[ $multi_home != *[[:space:]]* ]] || die '--multi-home must not contain whitespace'
[[ -n $multi_home ]] || die '--multi-home must not be empty'

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_root=$(cd -- "$script_dir/.." && pwd -P)
[[ -d $server_root ]] || die "server root does not exist: $server_root"
server_root=$(realpath -e -- "$server_root")
path_is_in_repo "$server_root" && die '--server-root must be outside the Git checkout'

server_script=$server_root/SquadGameServer.sh
[[ -f $server_script && -x $server_script ]] || \
    die "executable server launcher not found: $server_script"
server_binary=$server_root/SquadGame/Binaries/Linux/SquadGameServer
[[ -f $server_binary && -x $server_binary ]] || \
    die "executable server binary not found: $server_binary"

if [[ -n $preload ]]; then
    preload=$(realpath -m -- "$preload")
else
    preload=$(dirname -- "$server_root")/tools/gc_allow_ptrace_observer.so
    preload=$(realpath -m -- "$preload")
fi
path_is_in_repo "$preload" && die '--preload must be outside the Git checkout'
[[ ! -d $preload ]] || die "observer path is a directory: $preload"

helper_source=$script_dir/gc_allow_ptrace_observer.c
[[ -r $helper_source ]] || die "observer source is not readable: $helper_source"
mkdir -p -- "$(dirname -- "$preload")"

temporary_so=''
cleanup() {
    if [[ -n $temporary_so && -e $temporary_so ]]; then
        rm -f -- "$temporary_so"
    fi
}
trap cleanup EXIT

if [[ ! -f $preload || $helper_source -nt $preload ]]; then
    command -v gcc >/dev/null 2>&1 || die 'gcc is required to build the observer helper'
    temporary_so=$(mktemp "${preload}.tmp.XXXXXX")
    gcc -shared -fPIC -O2 -Wall -Wextra \
        -o "$temporary_so" "$helper_source"
    chmod 0755 -- "$temporary_so"
    mv -f -- "$temporary_so" "$preload"
    temporary_so=''
fi
[[ -r $preload && -f $preload ]] || die "observer shared library not found: $preload"

printf 'server root: %s\n' "$server_root" >&2
printf 'observer:    %s\n' "$preload" >&2
printf 'ports:       game=%s query=%s bind=%s\n' "$port" "$query_port" "$multi_home" >&2

# LD_PRELOAD is scoped to this exec and the server's descendants. No global
# environment, sudo state, credentials, or repository files are changed.
exec env LD_PRELOAD="$preload" "$server_script" \
    "Port=$port" "QueryPort=$query_port" "MULTIHOME=$multi_home" \
    "${server_args[@]}"
