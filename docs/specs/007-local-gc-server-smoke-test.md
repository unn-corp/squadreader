# Local GC Server Observer Smoke Test

**Status:** Experimental smoke test; live GC process verified
**Version:** 0.1
**Date:** 2026-08-26
**Scope:** Private local validation of SquadReader against one Linux Squad/GC server process

## Objective

Provide the smallest reproducible launch path for a local GC server process that
can be inspected by SquadReader. This is an observer/compatibility test, not a
production server recipe and not proof that GC runtime identifiers are mapped.

The launcher is `scripts/run_gc_server.sh`. It compiles
`scripts/gc_allow_ptrace_observer.c` into an external helper when the helper is
missing or older than the source, then applies that helper only to the server
launch through `LD_PRELOAD`.

The operator-facing LAN connection and live-join procedure is documented in
[`docs/runbooks/local-gc-server-connection.md`](../runbooks/local-gc-server-connection.md).

## Observed build and example paths

The local dedicated-server installation used for this smoke attempt reported:

```text
5.7.4-657966+//Squad/v10.5.3 1018 0
```

The following are exact paths from that machine, included as examples only:

```bash
FORK=/home/devotek/Documents/Projects/Unnamed/Server/squadreader-gc-maps
SERVER_ROOT=/mnt/ExtraStorage/GC-local-test/server
OBSERVER_TOOLS=/mnt/ExtraStorage/GC-local-test/tools
GC_SERVER_PAKS=/mnt/ExtraStorage/SteamLibrary/steamapps/workshop/content/393380/2428425228/Content/Paks/LinuxServer
```

The launcher does not assume these locations. `--server-root` is required, and
the server root must be outside the Git checkout. By default, the generated
observer library is placed in `../tools/gc_allow_ptrace_observer.so` beside the
server root. An explicit external `--preload` path can be used instead.

The GC server payload is installed as a UE plugin, not copied into the base
pak directory:

```text
SERVER_ROOT/SquadGame/Plugins/Mods/ANE_BASE/
  ANE_BASE.uplugin
  ANE_BASE.mi
  Content/Paks/LinuxServer/ANE_BASE*.pak|ucas|utoc
```

Copying the workshop package set directly into the base
`SquadGame/Content/Paks` directory produced invalid-signature and failed-mount
warnings. The plugin layout above mounted successfully on the observed build.
The staged package set must still match the base dedicated-server build;
successful mounting is not itself a compatibility proof.

## Prerequisites and safety boundary

- Linux, Bash, GCC, and a dynamically linked `SquadGameServer.sh` installation.
- A private test server root and a matching GC server package set.
- A SquadReader checkout with its virtual environment installed.
- Permission for the reader to inspect `/proc/$PID` and the target process
  memory. If the host's ptrace policy still blocks the reader, use an
  authorized reader invocation with the required capabilities or privilege.
- The observer constructor calls `prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY)` in
  the target process. This changes permission for that target process only; it
  does not change the host-wide `ptrace_scope`, grant host-wide ptrace access,
  or make an observer's writes safe. The intended observer behavior is
  read-only.

The launcher does not use `sudo`, credentials, Steam login state, `eval`, or a
global `LD_PRELOAD`. It rejects a server/helper path inside the checkout and
writes only the helper under the external test root. The server itself may
write its normal logs and `Saved` data under its own external installation.

## Start

From the fork, pass server arguments after `--`:

```bash
cd "$FORK"
bash scripts/run_gc_server.sh \
  --server-root "$SERVER_ROOT" \
  --port 7787 \
  --query-port 27165 \
  --multi-home 127.0.0.1 \
  -- \
  -log -unattended
```

This loopback topology is sufficient for the original reader-only smoke test;
it is not the working Proton-client connection topology. For a live client,
use the LAN bind and direct-console procedure in the
[local GC connection runbook](../runbooks/local-gc-server-connection.md).

The first run compiles the helper at:

```text
/mnt/ExtraStorage/GC-local-test/tools/gc_allow_ptrace_observer.so
```

That path is an example derived from `SERVER_ROOT`; it is not a required
installation path. Use `--preload /external/test-root/tools/observer.so` when
the helper should live elsewhere.

The launcher passes `Port=`, `QueryPort=`, and `MULTIHOME=` to
`SquadGameServer.sh`. It validates both ports as distinct values in the
1–65535 range and preserves all remaining server arguments as an array.

## Explicit PID discovery

Do not let the reader guess which process to attach to. In a second terminal,
identify the actual binary, check its command line, and then set the PID
manually:

```bash
pgrep -af "$SERVER_ROOT/SquadGameServer.sh|$SERVER_ROOT/SquadGame/Binaries/Linux/SquadGameServer"
ps -eo pid=,ppid=,user=,etime=,cmd= | grep -F "$SERVER_ROOT" | grep -v grep

# After confirming the executable and ports, replace the placeholder:
PID=<confirmed-SquadGameServer-binary-pid>
readlink -f "/proc/$PID/exe"
tr '\0' ' ' < "/proc/$PID/cmdline"
printf '\nPID=%s\n' "$PID"
```

The launcher uses `exec`, so signals sent to the terminal's foreground process
reach the server. For a separate-terminal stop, after confirming the PID:

```bash
kill -TERM "$PID"
```

Use `kill -0 "$PID"` to check whether it exited. Escalate only after verifying
that the PID is still the intended local test server.

## Reader smoke commands

Keep generated captures outside the checkout. `SQREADER_DATA_DIR` is the
reader's data override used by the current CLI:

```bash
export SQREADER_DATA_DIR="$FORK/data"
RUN_ROOT=/mnt/ExtraStorage/GC-local-test/reader-runs/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$RUN_ROOT"

"$FORK/.venv/bin/sqreader" doctor --pid "$PID"

"$FORK/.venv/bin/sqreader" snapshot \
  --pid "$PID" \
  --server-id gc \
  --pretty \
  > "$RUN_ROOT/snapshot.json"

"$FORK/.venv/bin/sqreader" watch \
  --pid "$PID" \
  --server-id gc \
  --hz 1 \
  --duration 60 \
  --out "$RUN_ROOT/watch.ndjson" \
  --sqrx-out "$RUN_ROOT/watch.sqrx"
```

If the helper is present but `/proc` or attach permissions still fail, rerun
the reader command only with the host's approved privilege/capability path.
Do not move server startup into `sudo`, and do not put credentials in this
workflow.

## Gates observed in the verified live run

These gates passed before interpreting compatibility:

1. SteamCMD installed a Linux dedicated-server build into the isolated server
   root.
2. `SquadGame/Binaries/Linux/SquadGameServer` was present and executable.
3. The server process launched with the GC plugin mounted and registered.
4. The active layer was
   `GC_BespinPlatforms_AAS_V1` and the server loaded GC faction/team data.
5. SquadReader attached to the explicit game-process PID, resolved the object
   pools, and produced a snapshot.
6. A bounded 1 Hz watch completed 16 ticks with no reader crash, producing both
   NDJSON and SQRX output.

Observed live values:

```text
server:       Squad v10.5.3 / SDK 5.7.4
build:        5.7.4-657966+//Squad/v10.5.3 1018 0
layer:        GC_BespinPlatforms_AAS_V1
snapshot:     54K NDJSON
watch:        16 ticks / 16.0s / effective 1.00 Hz
watch state:  WaitingToStart, players=0, vehicles=12
```

These gates establish that the reader can inspect this local live GC process.
They do not establish complete GC metadata enrichment or production readiness.

## Follow-up: direct LAN client connection

After the initial no-player smoke run, the server was restarted with the
deterministic `GC_BespinPlatforms_AAS_V2` layer and bound to
`192.168.1.111`. A Squad client joined through the in-game console with:

```text
open 192.168.1.111:7787
```

The server log recorded `Login request`, `Join request`, `PostLogin`, the
transition to `InProgress`, `RestartPlayer`, and `Join succeeded`. Loopback
binding did not produce this Proton-client handshake; the LAN bind did.

RCON `ListPlayers` showed one active player with team, squad, and
`GAR_P1_Rifleman` role. A reader snapshot taken against the confirmed binary
PID reported `matchState=InProgress`, `soldiersLive=1`, and
`vehicleSeatsLive=1`, but still reported `players=[]` and
`playerStatesNonCDO=0`. The connection gate therefore passes while reader
player-state enrichment remains an explicit compatibility gap.

The new harness also passed local non-server checks: Bash syntax validation,
GCC compilation of the shared library with warnings enabled, and a disposable
external launcher check that observed the scoped `LD_PRELOAD` plus the three
derived server arguments. A second run reused the same helper without
recompiling it.

## Current result and remaining gaps

The result is **pass for the local process/read smoke test** and **not yet
ready for integration sign-off**.

- The reader's hardcoded Squad offsets target v10.4 / SDK v10.4.1, while this
  server is v10.5.3 / SDK 5.7.4. The live doctor resolved the object pools and
  all ten hardcoded class-layout checks, but it exits non-zero because no
  players were connected for player-stat gates and vanilla static-geometry
  gates do not cover the GC layer. Build-specific offset validation is still
  required.
- The live process exposed vehicle and deployable objects. A controlled player
  connection is now verified by server logs and RCON, but the reader snapshot
  still does not emit a player entry; kits and weapons therefore still need a
  player-state mapping/capture path before their exact runtime classes can be
  considered reader-verified.
- The current reader metadata loader does not consume the GC bundle under
  `data/static/gc/*.json`. The raw snapshot is usable, but GC icons, map
  catalog enrichment, faction labels, role metadata, and vehicle profiles are
  not automatically joined yet.
- The smoke commands are currently manual. A dedicated
  `gc_compatibility_test.py` harness should turn the doctor/snapshot/watch
  sequence and acceptance gates into one repeatable report.

The live process observed these exact runtime classes:

```text
Vehicles:
  BP_Emplaced_ZU23-2_Laser_Antiaircannon_Base_C
  BP_HMP_Carrier_C
  BP_HMP_Skirmish_Child_C
  BP_LAAT_Carrier2_C
  BP_LAAT_DEV_Skirmish_Child_C
  BP_VWing_C

Deployables:
  BP_ANE_Ammocrate_CIS_C
  BP_ANE_Ammocrate_Republic_C
  BP_CR_FOBRadio_C
  BP_CloneBlue_FOBRadio_C
  BP_ShieldBubble_Hangar_C
  BP_helicopter_repair_zoneInvisible_C
```

This confirms that exact runtime vehicle and deployable class names can be
obtained from the live process. It does not yet cover every GC asset or the
kit/weapon classes emitted by a connected player.

## Reproducibility record

Record these values with every run:

- fork commit and reader data directory fingerprint;
- server executable version and hash;
- exact GC package manifest and source revision;
- server root, ports, bind address, and confirmed binary PID;
- selected exact layer and the layer actually loaded;
- doctor, snapshot, and bounded watch exit codes;
- log excerpts for package mounts, missing dependencies, and map travel.

The verified run artifacts are outside the checkout at:

```text
/mnt/ExtraStorage/GC-squadreader-assets/2026-08-26/live-smoke/
```

No run should be called complete GC compatibility validation until the loaded
layer, reader build gate, and controlled player/kit/weapon fixtures are all
independently verified.
