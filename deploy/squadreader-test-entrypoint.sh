#!/usr/bin/env bash
# Start the upstream Squad container's install/mod flow, then run the game and
# this fork's reader in the same container. Keeping both processes here is
# intentional: SquadReader's complete mode reads the live Squad process memory.
set -Eeuo pipefail
IFS=$'\n\t'

: "${HOMEDIR:=/home/steam}"
: "${STEAMAPPDIR:=${HOMEDIR}/squad-dedicated}"
: "${STEAMCMDDIR:=${HOMEDIR}/steamcmd}"
: "${STEAMAPPID:=403240}"
: "${STEAM_BETA_APP:=774961}"
: "${STEAM_BETA_BRANCH:=}"
: "${STEAM_BETA_PASSWORD:=}"
: "${FORCE_STEAM_UPDATE:=0}"
: "${WORKSHOP_DOWNLOAD_ATTEMPTS:=20}"
: "${WORKSHOPID:=393380}"
: "${MODPATH:=${STEAMAPPDIR}/SquadGame/Plugins/Mods}"
: "${PORT:=7787}"
: "${QUERYPORT:=27165}"
: "${BEACONPORT:=15000}"
: "${RCONPORT:=21116}"
: "${RCONIP:=0.0.0.0}"
: "${RCONPASSWORD:=}"
: "${FIXEDMAXPLAYERS:=80}"
: "${FIXEDMAXTICKRATE:=50}"
: "${RANDOM:=NONE}"
: "${MULTIHOME:=0.0.0.0}"
: "${SERVER_NAME:=GC Maps SquadReader Test}"
: "${MOD_IDS:=2428425228}"
: "${GC_CONFIG_DIR:=/opt/gc-config}"
: "${OBSERVER_SO:=/opt/sqreader-runtime/gc_allow_ptrace_observer.so}"
: "${SQREADER_DATA_DIR:=/opt/sqreader/data/static}"
: "${READER_DATA_DIR:=/opt/sqreader-runtime}"
: "${READER_PORT:=8766}"
: "${READER_HZ:=0.5}"
: "${READER_RECORD_HZ:=2.0}"
: "${READER_SERVER_ID:=gc-mothership-test}"

SERVER_CONFIG_DIR="$STEAMAPPDIR/SquadGame/ServerConfig"
SERVER_LOG="$STEAMAPPDIR/SquadGame/Saved/Logs/SquadGame.log"
READER_BIN=/opt/sqreader-venv/bin/sqreader

log() { printf '[squadreader-test] %s\n' "$*"; }
die() { printf '[squadreader-test] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -x "$READER_BIN" ]] || die "reader executable missing: $READER_BIN"
[[ -f "$OBSERVER_SO" ]] || die "ptrace observer missing: $OBSERVER_SO"

install_squad() {
    mkdir -p "$STEAMAPPDIR"
    if [[ "$FORCE_STEAM_UPDATE" != "1" && -x "$STEAMAPPDIR/SquadGameServer.sh" ]]; then
        log "Squad already installed; skipping update"
        return 0
    fi

    if [[ -n "$STEAM_BETA_BRANCH" ]]; then
        log "updating Squad beta branch $STEAM_BETA_BRANCH"
        bash "$STEAMCMDDIR/steamcmd.sh" \
            +force_install_dir "$STEAMAPPDIR" \
            +login anonymous \
            +app_update "$STEAM_BETA_APP" \
            -beta "$STEAM_BETA_BRANCH" \
            -betapassword "$STEAM_BETA_PASSWORD" \
            +quit
    else
        log "updating Squad release app $STEAMAPPID"
        bash "$STEAMCMDDIR/steamcmd.sh" \
            +force_install_dir "$STEAMAPPDIR" \
            +login anonymous \
            +app_update "$STEAMAPPID" \
            +quit
    fi
    [[ -x "$STEAMAPPDIR/SquadGameServer.sh" ]] || \
        die "SquadGameServer.sh was not installed under $STEAMAPPDIR"
}

copy_test_config() {
    mkdir -p "$SERVER_CONFIG_DIR"
    [[ -d "$GC_CONFIG_DIR" ]] || {
        log "no mounted GC config directory at $GC_CONFIG_DIR; using image defaults"
        return
    }

    # These files are gameplay/server settings. Credentials and the license
    # key are intentionally excluded and must be supplied separately.
    local names=(
        Admins.cfg Bans.cfg CustomOptions.cfg ExcludedFactionSetups.cfg
        ExcludedFactions.cfg ExcludedLayers.cfg ExcludedLevels.cfg
        LayerRotation.cfg LayerVoting.cfg LayerVotingLowPlayers.cfg
        LayerVotingNight.cfg LevelRotation.cfg MOTD.cfg
        RemoteAdminListHosts.cfg RemoteBanListHosts.cfg Server.cfg
        ServerMessages.cfg VoteConfig.cfg
    )
    local name
    for name in "${names[@]}"; do
        if [[ -f "$GC_CONFIG_DIR/$name" ]]; then
            install -m 0644 "$GC_CONFIG_DIR/$name" "$SERVER_CONFIG_DIR/$name"
        fi
    done
}

configure_rcon() {
    [[ -n "$RCONPASSWORD" ]] || die "RCONPASSWORD must be set"
    [[ "$RCONPASSWORD" != *$'\n'* && "$RCONPASSWORD" != *$'\r'* ]] || \
        die "RCONPASSWORD must not contain newlines"

    RCON_CONFIG_PATH="$SERVER_CONFIG_DIR/Rcon.cfg" \
        RCON_IP_VALUE="$RCONIP" \
        RCON_PORT_VALUE="$RCONPORT" \
        RCON_PASSWORD_VALUE="$RCONPASSWORD" \
        python3 - <<'PY'
import os
import re
from pathlib import Path

path = Path(os.environ["RCON_CONFIG_PATH"])
lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) \
    if path.exists() else []

values = {
    "IP": os.environ["RCON_IP_VALUE"],
    "Port": os.environ["RCON_PORT_VALUE"],
    "Password": os.environ["RCON_PASSWORD_VALUE"],
}

for key, value in values.items():
    pattern = re.compile(rf"^(\s*){re.escape(key)}\s*=.*(?:\r?\n)?$", re.IGNORECASE)
    replacement = f"{key}={value}\n"
    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("".join(lines), encoding="utf-8")
PY
    chmod 0600 "$SERVER_CONFIG_DIR/Rcon.cfg"
    log "configured RCON on $RCONIP:$RCONPORT"
}

install_mods() {
    mkdir -p "$MODPATH"
    [[ "$WORKSHOP_DOWNLOAD_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || \
        die "WORKSHOP_DOWNLOAD_ATTEMPTS must be a positive integer"

    # Remove only numeric workshop links/directories, leaving any image-baked
    # plugin metadata intact.
    find "$MODPATH" -mindepth 1 -maxdepth 1 \
        -regextype posix-extended -regex '.*/[0-9]+' \
        -exec rm -rf -- {} + 2>/dev/null || true

    local -a ids=()
    read -r -a ids <<< "$MOD_IDS"
    local id target
    for id in "${ids[@]}"; do
        [[ "$id" =~ ^[0-9]+$ ]] || die "invalid workshop id: $id"
        target="$STEAMAPPDIR/steamapps/workshop/content/$WORKSHOPID/$id"
        local ready_marker="$STEAMAPPDIR/.sqreader-workshop-${WORKSHOPID}-${id}.ready"
        if [[ -f "$ready_marker" && -d "$target" ]]; then
            log "workshop item $id already installed; skipping update"
            ln -sfn "$target" "$MODPATH/$id"
            continue
        fi

        local downloaded=0 status=0 attempt
        for ((attempt = 1; attempt <= WORKSHOP_DOWNLOAD_ATTEMPTS; attempt++)); do
            log "installing workshop item $id (attempt $attempt/$WORKSHOP_DOWNLOAD_ATTEMPTS)"
            if bash "$STEAMCMDDIR/steamcmd.sh" \
                +force_install_dir "$STEAMAPPDIR" \
                +login anonymous \
                +workshop_download_item "$WORKSHOPID" "$id" \
                +quit; then
                downloaded=1
                break
            else
                status=$?
                log "workshop item $id download failed with status $status; retrying"
                (( attempt < WORKSHOP_DOWNLOAD_ATTEMPTS )) && sleep 5
            fi
        done

        [[ "$downloaded" == "1" ]] || \
            die "workshop item $id failed after $WORKSHOP_DOWNLOAD_ATTEMPTS attempts"
        [[ -d "$target" ]] || die "workshop item $id did not download"
        touch "$ready_marker"
        ln -sfn "$target" "$MODPATH/$id"
    done
}

set_server_name() {
    [[ -f "$SERVER_CONFIG_DIR/Server.cfg" ]] || return 0
    SERVER_CONFIG_PATH="$SERVER_CONFIG_DIR/Server.cfg" SERVER_NAME_VALUE="$SERVER_NAME" \
        python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["SERVER_CONFIG_PATH"])
name = os.environ["SERVER_NAME_VALUE"]
lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
for index, line in enumerate(lines):
    if line.startswith("ServerName="):
        lines[index] = f'ServerName="{name.replace(chr(34), chr(39))}"\n'
        break
else:
    lines.append(f'ServerName="{name.replace(chr(34), chr(39))}"\n')
path.write_text("".join(lines), encoding="utf-8")
PY
}

game_pid_for_port() {
    local entry exe cmdline
    for entry in /proc/[0-9]*; do
        exe=$(readlink "$entry/exe" 2>/dev/null || true)
        [[ "${exe##*/}" == "SquadGameServer" ]] || continue
        cmdline=$(tr '\0' ' ' < "$entry/cmdline" 2>/dev/null || true)
        [[ "$cmdline" == *"Port=$PORT"* ]] || continue
        printf '%s\n' "${entry##*/}"
        return 0
    done
    return 1
}

run_game() {
    local args=(
        "Port=$PORT"
        "QueryPort=$QUERYPORT"
        "RCONPORT=$RCONPORT"
        "FIXEDMAXPLAYERS=$FIXEDMAXPLAYERS"
        "FIXEDMAXTICKRATE=$FIXEDMAXTICKRATE"
        "beaconport=$BEACONPORT"
        "RANDOM=$RANDOM"
    )
    [[ -n "$MULTIHOME" && "$MULTIHOME" != "0.0.0.0" && "$MULTIHOME" != "127.0.0.1" ]] && \
        args+=("MULTIHOME=$MULTIHOME")

    log "starting Squad on game=$PORT query=$QUERYPORT rcon=$RCONPORT"
    # The helper makes the target process dumpable for the read-only reader.
    # It is scoped to SquadGameServer.sh and its descendants.
    env LD_PRELOAD="$OBSERVER_SO" \
        bash "$STEAMAPPDIR/SquadGameServer.sh" "${args[@]}"
}

wait_for_game_pid() {
    local pid
    for _ in $(seq 1 300); do
        if pid=$(game_pid_for_port); then
            printf '%s\n' "$pid"
            return 0
        fi
        if ! kill -0 "$GAME_LAUNCHER_PID" 2>/dev/null; then
            wait "$GAME_LAUNCHER_PID" || true
            return 1
        fi
        sleep 1
    done
    return 1
}

run_reader() {
    mkdir -p "$READER_DATA_DIR/recordings" "$READER_DATA_DIR/stats"
    local pid=$1
    local args=(
        serve
        --pid "$pid"
        --server-id "$READER_SERVER_ID"
        --host 0.0.0.0
        --port "$READER_PORT"
        --hz "$READER_HZ"
        --record-hz "$READER_RECORD_HZ"
        --recordings-dir "$READER_DATA_DIR/recordings"
        --stats-db "$READER_DATA_DIR/stats/player_stats.db"
        --icons-dir /opt/sqreader/icons
        --sqmaps-dir /opt/sqreader/sqmaps
        --frontend-dir /opt/sqreader/frontend/dist
        --squad-log "$SERVER_LOG"
    )
    log "starting SquadReader on http://0.0.0.0:$READER_PORT for pid=$pid"
    cd /opt/sqreader
    # The package is installed into a virtualenv, so its source-relative
    # metadata discovery cannot see the checkout's static catalog by itself.
    # Keep the static catalog separate from the persistent recording output.
    SQREADER_DATA_DIR="$SQREADER_DATA_DIR" exec "$READER_BIN" "${args[@]}"
}

install_squad
copy_test_config
configure_rcon
set_server_name
install_mods

run_game &
GAME_LAUNCHER_PID=$!
GAME_PID=$(wait_for_game_pid) || die "SquadGameServer did not start"

run_reader "$GAME_PID" &
READER_PID=$!

shutdown() {
    trap - EXIT INT TERM
    kill "$READER_PID" "$GAME_LAUNCHER_PID" 2>/dev/null || true
    wait "$READER_PID" "$GAME_LAUNCHER_PID" 2>/dev/null || true
}
trap shutdown EXIT INT TERM

set +e
wait -n "$GAME_LAUNCHER_PID" "$READER_PID"
status=$?
set -e
log "one of the processes exited with status $status; stopping the other"
exit "$status"
