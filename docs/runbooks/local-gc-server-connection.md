# Local GC server connection and reader validation

**Status:** Observed working connection; reader emits live GC player/actor data and auto-selects the committed GC assets
**Date:** 2026-08-26
**Scope:** Private LAN smoke test for one Galactic Contention server process and one Squad client

This runbook records the repeatable path from a staged GC server to a connected
client and a SquadReader capture. It is an operator test recipe, not a
production hosting guide.

## What this test proves

The test has separate gates. A successful client connection does not, by
itself, prove that SquadReader has complete GC coverage.

1. The server mounts the GC plugin and loads the selected cooked layer.
2. The server is reachable on the LAN game address.
3. The client joins the server and reaches an active round.
4. RCON and server logs confirm the player, team, role, and spawn path.
5. SquadReader attaches to the confirmed server binary PID and emits a
   snapshot containing GC map, team, vehicle, and deployable data.
6. Any mismatch between server-side player state and the reader model is
   recorded as a reader gap rather than hidden by the connection result.

## Known-good test record

The following values were observed in the live test on 2026-08-26:

| Item | Observed value |
| --- | --- |
| Squad / engine build | `v10.5.3` / `5.7.4-657966` |
| GC workshop item | `2428425228` |
| Server bind | `192.168.1.111` |
| Game port | `7787/udp` |
| Query port | `27165/udp` |
| Test RCON | `127.0.0.1:21114/tcp` |
| Loaded layer pool ID | `GC_BespinPlatforms_AAS_V2` |
| Loaded cooked asset | `GC_Bespin_Platforms_AAS_V2` |
| Server state | `InProgress` |
| Reader schema | `phase3-draft` |

The player connection was confirmed by RCON and by the server log. The initial
pre-fix snapshot reported `soldiersLive=1`, `vehicleSeatsLive=1`, and the
expected GC map/team/vehicle/deployable data, but `playerStatesNonCDO=0` and
`players=[]` while RCON showed one active player. The reader now accepts GC's
`GC_PlayerState_C` Blueprint subclass and emits the live player through the
same reflected base layout as stock Squad.

## Prerequisites and layout

Use an external server root. Do not stage server files or generated captures in
the Git checkout.

```bash
export FORK=/home/devotek/Documents/Projects/Unnamed/Server/squadreader-gc-maps
export SERVER_ROOT=/mnt/ExtraStorage/GC-local-test/server
export OBSERVER_TOOLS=/mnt/ExtraStorage/GC-local-test/tools
export CAPTURE_ROOT=/mnt/ExtraStorage/GC-squadreader-assets
export LAN_IP=192.168.1.111
export GAME_PORT=7787
export QUERY_PORT=27165
export RCON_PORT=21114
```

The GC package must be staged as a UE plugin:

```text
$SERVER_ROOT/SquadGame/Plugins/Mods/ANE_BASE/
  ANE_BASE.uplugin
  ANE_BASE.mi
  Content/Paks/LinuxServer/ANE_BASE*.pak|ucas|utoc
```

The server package revision, base dedicated-server build, and client workshop
package must match. Copying GC paks into the base
`SquadGame/Content/Paks` directory is not equivalent and produced mount or
signature failures in the earlier test.

## 1. Start the server

Use the fork's scoped launcher. It compiles and applies the ptrace observer
only to this server process:

```bash
cd "$FORK"
bash scripts/run_gc_server.sh \
  --server-root "$SERVER_ROOT" \
  --preload "$OBSERVER_TOOLS/gc_allow_ptrace_observer.so" \
  --port "$GAME_PORT" \
  --query-port "$QUERY_PORT" \
  --multi-home "$LAN_IP" \
  -- \
  -log -unattended
```

For a controlled local test, RCON may be enabled on loopback by adding these
server arguments before `-log`:

```text
RCONIP=127.0.0.1 RCONPORT=21114 RCONPASSWORD=<temporary-local-secret>
```

Never commit the RCON secret, put it in a tracked config file, or bind RCON to
the LAN address for this test.

## 2. Verify the actual process and sockets

Wait for the server to finish loading, then identify the game binary manually.
Do not use an unverified `pgrep -n -f`: a process-search command containing the
same path can be selected instead of the server.

```bash
pgrep -af "$SERVER_ROOT/SquadGame/Binaries/Linux/SquadGameServer"

# Set this only after confirming the executable and command-line ports.
export SERVER_PID=<confirmed-SquadGameServer-binary-pid>
readlink -f "/proc/$SERVER_PID/exe"
tr '\0' ' ' < "/proc/$SERVER_PID/cmdline"
printf '\nPID=%s\n' "$SERVER_PID"

ss -ltnup | rg "$GAME_PORT|$QUERY_PORT|$RCON_PORT"
```

Expected bindings:

```text
udp  192.168.1.111:7787
udp  192.168.1.111:27165
tcp  127.0.0.1:21114
```

The LAN bind is intentional. Binding the game and query sockets only to
`127.0.0.1` did not produce a client handshake from the Proton client in this
test, while the LAN bind did.

## 3. Verify the loaded map

```bash
export SERVER_LOG="$SERVER_ROOT/SquadGame/Saved/Logs/SquadGame.log"
rg -n \
  'Start Server with map|LoadMap Load map complete|currentmap|Match State Changed' \
  "$SERVER_LOG" | tail -n 40
```

Verify both names when comparing records:

- `GC_BespinPlatforms_AAS_V2` is the layer-pool/rotation identifier.
- `GC_Bespin_Platforms_AAS_V2` is the cooked map asset path component shown by
  the server's `Start Server with map` line.

Confusing those names caused false `SQLayer not found` warnings during RCON
map experiments.

The observed `Join request` also contained a legacy
`/Game/Maps/Logar_Valley/LogarValley_AAS_v1` URL while the server was loading
Bespin V2. Do not use that request URL as map identity. Use the server's
`Start Server with map`, `currentmap`, and `LoadMap` lines, plus the reader's
`gameState.mapName`.

## 4. Connect the client

Confirm that the client has the same GC workshop package mounted and the same
Squad build. If the client was previously connected to a restarted server,
wait for the new server map to finish loading before reconnecting.

In Squad, open the developer console by double-tapping `~` and enter:

```text
open 192.168.1.111:7787
```

The in-game console path is the validation path for this test. Server-browser
discovery showed unreliable layer metadata (`Layer Unknown`) and did not
provide a dependable connection signal. A failed browser attempt that leaves
no `Login request` in the server log is a client/discovery initiation failure,
not a server-side rejection.

If the console is unavailable, the chat input can be used as a fallback: press
`J`, clear the chat command, type the same `open` command, and submit it.

## 5. Confirm the live join

### Server log

```bash
rg -n \
  'Login request|Join request|PostLogin|Match State Changed|RestartPlayer|Join succeeded' \
  "$SERVER_LOG" | tail -n 60
```

The minimum successful sequence is:

```text
Login request
Join request
PostLogin: NewPlayer: BP_GC_PlayerController_C
Match State Changed ... to InProgress
RestartPlayer()
Join succeeded
```

### RCON

The GC Maps tooling can query the local RCON endpoint without writing a
password file. Enter the temporary secret when prompted by the server launcher
or retrieve it from the local secret store used for this test; do not paste it
into a repository command or document.

```bash
read -r -s RCON_SECRET
printf '\n'
RCON_HOST=127.0.0.1 \
RCON_CFG=<(printf 'Port=%s\nPassword=%s\n' "$RCON_PORT" "$RCON_SECRET") \
  timeout 20 python3 \
  /home/devotek/Documents/Projects/Unnamed/Server/GC-config/tooling/rcon.py \
  ListPlayers
unset RCON_SECRET
```

Expected result is one active player with a team, squad, and role. The observed
test returned one active player on team 1, squad 1, role
`GAR_P1_Rifleman`.

## 6. Capture with SquadReader

Use the confirmed PID from step 2. Create a unique external capture directory;
the snapshot `--out` option appends NDJSON, so reusing a file mixes runs.

```bash
export SQREADER_DATA_DIR="$CAPTURE_ROOT/reader-data"
export RUN_ROOT="$CAPTURE_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-gc-live"
mkdir -p "$RUN_ROOT"

set +e
"$FORK/.venv/bin/sqreader" doctor \
  --pid "$SERVER_PID" \
  > "$RUN_ROOT/doctor.txt" 2>&1
DOCTOR_RC=$?

"$FORK/.venv/bin/sqreader" snapshot \
  --pid "$SERVER_PID" \
  --server-id gc \
  --out "$RUN_ROOT/snapshot.ndjson" \
  > "$RUN_ROOT/snapshot.stdout" \
  2> "$RUN_ROOT/snapshot.stderr"
SNAPSHOT_RC=$?

"$FORK/.venv/bin/sqreader" watch \
  --pid "$SERVER_PID" \
  --server-id gc \
  --hz 1 \
  --duration 30 \
  --out "$RUN_ROOT/watch.ndjson" \
  --sqrx-out "$RUN_ROOT/watch.sqrx" \
  > "$RUN_ROOT/watch.stdout" \
  2> "$RUN_ROOT/watch.stderr"
WATCH_RC=$?
set -e

printf 'doctor_rc=%s snapshot_rc=%s watch_rc=%s\n' \
  "$DOCTOR_RC" "$SNAPSHOT_RC" "$WATCH_RC" | tee "$RUN_ROOT/exit-codes.txt"
test "$SNAPSHOT_RC" -eq 0 && test "$WATCH_RC" -eq 0
```

The `doctor` command can be non-zero when its generic player or vanilla-map
gates do not apply to the GC fixture. Preserve its output; do not use that
alone to reject the lower-level snapshot. The snapshot and bounded watch must
still exit successfully and show the expected GC map and actors.

For this run, attaching with the confirmed PID resolved cached `GUObjectArray`
and `FNamePool` addresses and emitted a snapshot. A discovery failure with
`no mappings found for module 'SquadGameServer'` was caused by using the wrong
PID selected by an unverified process search; rerun with the confirmed binary
PID before diagnosing the reader.

### Playback recording

`watch --sqrx-out` produces a valid SQRX stream, but it does not create the
finalized metadata sidecar used by the web viewer. For a replay that the local
viewer can advertise, run the managed recorder during the match:

```bash
REPLAY_DIR="$CAPTURE_ROOT/live-recordings"
mkdir -p "$REPLAY_DIR"

"$FORK/.venv/bin/sqreader" serve \
  --pid "$SERVER_PID" \
  --server-id gc \
  --host 127.0.0.1 \
  --port 8765 \
  --hz 1 \
  --record-hz 4 \
  --recordings-dir "$REPLAY_DIR" \
  --squad-log "$SERVER_ROOT/SquadGame/Saved/Logs/SquadGame.log" \
  --icons-dir "$FORK/icons" \
  --sqmaps-dir "$FORK/sqmaps" \
  --frontend-dir "$FORK/frontend/dist"
```

The extracted GC catalog is auto-loaded from `$FORK/data/static/gc` (or the
`gc/` child of `SQREADER_DATA_DIR`). A live GC display name such as
`Bespin Platforms AAS V2` is normalized against the catalog's
`GC_BespinPlatforms_AAS_V2` key. The resulting layer points at the packaged
map hash, while the HTTP server resolves that hash under `sqmaps/gc/`; no
manual map selection is required. The same server root exposes the extracted
`icons/gc/` files under `/icons/gc/`.

The service is available at `http://127.0.0.1:8765/viewer-next`. The
`/api/recordings` list remains empty while the match is active; this is
intentional. When the match transitions to a confirmed end, the recorder
writes a finalized `.meta.json` sidecar and the recording becomes selectable in
the viewer. A forced stop during an active match leaves the recording
unverified and the viewer refuses to serve it.

The pre-fix 2026-08-26 live test produced 61 one-Hz frames in `watch.sqrx`;
those frames were deliberately retained as a diagnostic artifact. The fixed
recording was started in
`$CAPTURE_ROOT/fixed-live-recordings/2026-08-26_065623_BespinPlatformsAASV2_AAS_v0_065a8350.sqrx`.
Its first 262 decoded frames contain `players=[Devotek]`, the GC layer metadata,
12 vehicles, and 23 deployables. While it is active, the sidecar remains
`recordingState=active` and `/api/recordings` remains empty; after a confirmed
match end, the sidecar is finalized and the viewer can play it back.

## 7. Map-roll test

For a deterministic startup test, set the external layer rotation file to one
known GC layer and restart the test server:

```text
$SERVER_ROOT/SquadGame/ServerConfig/LayerRotation.cfg
```

The observed reliable startup procedure was to select
`GC_BespinPlatforms_AAS_V2` in that file, restart, and verify the loaded cooked
asset in the server log. This external change is test state, not a repository
change.

During an active round, the RCON sequence to test next-layer handling is:

```text
AdminSetNextLayer GC_BespinPlatforms_AAS_V2
AdminEndMatch
```

Verify the subsequent `Start Server with map`, `LoadMap`, and
`Match State Changed` lines. `AdminSetNextLayer` by itself only sets the next
layer. `AdminEndMatch` did not travel while the server had no active player or
round in the earlier test, so perform this test after the live-join gate and
record the exact commands and result.

## Failure signatures

| Symptom | Likely boundary | Next check |
| --- | --- | --- |
| No `Login request` in server log | Client/browser/console did not initiate the handshake | Use direct `open` against the LAN address; verify client log and server bind |
| Client times out after a restart | Old session lost its server connection | Wait for map load, then issue `open` again |
| File mismatch | Client/server GC package or Squad build differs | Validate client files and compare package revision/build/manifest |
| `Layer Unknown` in browser | Browser metadata/session discovery is stale or incomplete | Do not use discovery for this gate; use direct console connection |
| `players=[]` but RCON has an active player | Reader player-state mapping or filtering gap | Preserve snapshot and logs; treat actor/map coverage and player enrichment separately |
| `GUObjectArray` discovery says no module mappings | Wrong PID or unconfirmed process selection | Inspect `/proc/$SERVER_PID/exe` and `/proc/$SERVER_PID/maps`, then retry |
| Server binds only to loopback | Proton client cannot reach the test server | Restart with `--multi-home 192.168.1.111` or the host's LAN address |
| `SQLayer not found` during a layer command | Pool ID/cooked asset name was mixed up | Use the exact rotation ID for admin commands and the cooked path only for log comparison |
| `RCON was not setup ... password not specified` | RCON is disabled | Enable a temporary loopback-only RCON secret for the test, if needed |

## Acceptance checklist

- [ ] GC plugin is staged under `SquadGame/Plugins/Mods/ANE_BASE`.
- [ ] Client and server package/build revisions match.
- [ ] Server binds game/query to the LAN address and RCON only to loopback.
- [ ] Confirmed PID is the actual `SquadGameServer` binary.
- [ ] Server log confirms the intended cooked GC layer loaded.
- [ ] Direct console `open` reaches the server.
- [ ] Server log contains `PostLogin`, `InProgress`, `RestartPlayer`, and
      `Join succeeded`.
- [ ] RCON `ListPlayers` shows the connected player and role.
- [ ] SquadReader snapshot exits successfully and contains GC map/team/actor
      data.
- [ ] A bounded watch completes and is stored outside the checkout.
- [ ] Any `players=[]`/player-state discrepancy is filed as a reader gap.
- [ ] Map-roll commands, exact layer IDs, logs, snapshot, and package/build
      fingerprints are preserved.

## Cleanup

After the run, stop the server only after rechecking that `SERVER_PID` is the
intended local test binary. If temporary RCON was enabled, restart without the
RCON arguments or rotate the secret, and ensure it remains bound to loopback.
Do not move the secret into tracked configuration or expose it on the LAN.

## Evidence locations

Keep these artifacts outside the fork:

```text
$SERVER_ROOT/SquadGame/Saved/Logs/SquadGame.log
/mnt/ExtraStorage/SteamLibrary/steamapps/compatdata/393380/pfx/drive_c/users/steamuser/AppData/Local/SquadGame/Saved/Logs/SquadGame.log
$RUN_ROOT/doctor.txt
$RUN_ROOT/snapshot.ndjson
$RUN_ROOT/watch.ndjson
$RUN_ROOT/watch.sqrx
```

Related design and compatibility notes are in
[`docs/specs/007-local-gc-server-smoke-test.md`](../specs/007-local-gc-server-smoke-test.md).
