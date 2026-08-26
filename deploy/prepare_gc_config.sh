#!/usr/bin/env bash
# Stage only non-secret Squad settings for the portable test image.
# Usage: prepare_gc_config SOURCE_DIR DEST_DIR
set -Eeuo pipefail
IFS=$'\n\t'

source_dir=${1:?source directory required}
dest_dir=${2:?destination directory required}
[[ -d "$source_dir" ]] || { printf 'source directory not found: %s\n' "$source_dir" >&2; exit 2; }
mkdir -p "$dest_dir"

names=(
    Admins.cfg Bans.cfg CustomOptions.cfg ExcludedFactionSetups.cfg
    ExcludedFactions.cfg ExcludedLayers.cfg ExcludedLevels.cfg
    LayerRotation.cfg LayerVoting.cfg LayerVotingLowPlayers.cfg
    LayerVotingNight.cfg LevelRotation.cfg MOTD.cfg
    RemoteAdminListHosts.cfg RemoteBanListHosts.cfg Server.cfg
    ServerMessages.cfg VoteConfig.cfg
)

for name in "${names[@]}"; do
    [[ -f "$source_dir/$name" ]] || continue
    install -m 0644 "$source_dir/$name" "$dest_dir/$name"
done

printf 'staged non-secret Squad config in %s\n' "$dest_dir"
