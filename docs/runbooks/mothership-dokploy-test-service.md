# Mothership Dokploy test service

This service is a portable test target for the PSG SquadReader image path. It
keeps Squad and SquadReader in one container so the reader can inspect the
live Squad process. The GC asset bundle is baked into the image; the server
configuration is mounted separately so secrets never enter Git.

## Service layout

- Image build: `Dockerfile.squadreader-test`
- Compose definition: `docker-compose.test.yml`
- Entrypoint: `deploy/squadreader-test-entrypoint.sh`
- Non-secret config staging: `deploy/prepare_gc_config.sh`
- GC workshop item: `2428425228`
- Default test ports: game `7787/udp`, query `27165/tcp+udp`, beacon
  `15000/udp`, RCON target `21116/tcp`, reader `8766/tcp`

The container defaults use RCON `21116` and reader `8766`. On mothership, the
test service publishes RCON as host port `22116` because ports `21115` through
`21119` are already occupied by RustDesk.

## Dokploy

There are two supported deployment shapes:

1. The portable Compose path uses `docker-compose.test.yml`. It is the right
   choice when Dokploy's Compose API/UI is available because it preserves the
   host config bind and persistent volumes.
2. The current mothership Dokploy setup uses a single Docker Application built
   from `Dockerfile.squadreader-test`. This is equivalent for the first live
   test because the non-secret GC profile is baked into the image; recordings
   remain container-local until mounts are added.

For the Dokploy Application, use the **Game Services** project, the `main`
branch of this repository, build type `Dockerfile`, Dockerfile path
`Dockerfile.squadreader-test`, and build context `/`. Set the following in
Dokploy's environment/secret store:

```text
RCON_PASSWORD=<secret>
PORT=7787
QUERYPORT=27165
BEACONPORT=15000
RCONPORT=21116
READER_PORT=8766
SQREADER_DATA_DIR=/opt/sqreader/data/static
MOD_IDS=2428425228
```

Add these published ports to the Application's Advanced → Ports settings.
Use `host` publish mode, one replica, and do not put the game ports behind an
HTTP domain:

| Published | Target | Protocol |
| ---: | ---: | --- |
| 7787 | 7787 | UDP |
| 27165 | 27165 | UDP |
| 27165 | 27165 | TCP |
| 15000 | 15000 | UDP |
| 22116 | 21116 | TCP |
| 8766 | 8766 | TCP |

The Compose bind paths are host paths on mothership. They keep the large
Steam/Squad install and recordings outside the Git checkout. The Dokploy
Application path uses the same non-secret GC profile baked at
`/opt/gc-config`; a later Compose deployment can override it with the staged
host directory.

The first live Application deployment required explicit Swarm port bindings
and a host bind for the large Squad install. If the Dokploy Application is
redeployed, verify that its Advanced → Ports and Storage settings preserve
these bindings before scaling it back up; otherwise a fresh task can lose the
published game ports or reinstall the server into ephemeral container storage.

## Config policy

The PSG test server's non-secret `ServerConfig` files are staged into the
mothership host config directory with `prepare_gc_config.sh` for the portable
Compose path. The Dokploy Application image includes the same non-secret GC
rotation profile under `/opt/gc-config`. Do not copy `Rcon.cfg` or
`License.cfg`: RCON is injected through the environment and the test server
uses the reader's synthetic match IDs when no OWI license is present.

The server entrypoint downloads the Squad dedicated server and the GC
Workshop package on first start, then copies mounted settings when present
(otherwise it uses the baked profile) before launching the server. It starts
Squad with the scoped GC ptrace observer and starts SquadReader against the
confirmed `SquadGameServer` PID.

## Acceptance checks

1. The container remains healthy after the initial Steam/Workshop download.
2. `GET /health` responds on the reader port.
3. RCON `ShowNextMap` authenticates on the selected RCON port.
4. A client can join with the same GC Workshop package and server build.
5. The reader emits a GC map/team/player snapshot and creates a recording.
6. The UI serves the committed GC icons and map assets from the same origin.

The test service is intentionally local-only in terms of data persistence and
does not enable central replay pushing.
