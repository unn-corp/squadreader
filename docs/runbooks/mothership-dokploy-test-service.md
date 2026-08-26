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
  `15000/udp`, RCON `21116/tcp`, reader `8766/tcp`

The defaults intentionally use RCON `21116` and reader `8766`; mothership
already has another service using `21115`.

## Dokploy

Create a separate Compose service in the Dokploy **Game Services** project.
Use this repository and `docker-compose.test.yml` as the compose path. Set
the following in Dokploy's environment/secret store:

```text
RCON_PASSWORD=<secret>
SQUAD_GAME_PORT=7787
SQUAD_QUERY_PORT=27165
SQUAD_BEACON_PORT=15000
RCON_PORT=21116
READER_PORT=8766
MOD_IDS=2428425228
```

The bind paths in the Compose file are host paths on mothership. They keep
the large Steam/Squad install and recordings outside the Git checkout.

## Config policy

Stage the PSG test server's non-secret `ServerConfig` files into the host
config directory with `prepare_gc_config.sh`. Do not copy `Rcon.cfg` or
`License.cfg`: RCON is injected through the environment and the test server
uses the reader's synthetic match IDs when no OWI license is present.

The server entrypoint downloads the Squad dedicated server and the GC
Workshop package on first start, then copies the staged settings before
launching the server. It starts Squad with the scoped GC ptrace observer and
starts SquadReader against the confirmed `SquadGameServer` PID.

## Acceptance checks

1. The container remains healthy after the initial Steam/Workshop download.
2. `GET /health` responds on the reader port.
3. RCON `ShowNextMap` authenticates on the selected RCON port.
4. A client can join with the same GC Workshop package and server build.
5. The reader emits a GC map/team/player snapshot and creates a recording.
6. The UI serves the committed GC icons and map assets from the same origin.

The test service is intentionally local-only in terms of data persistence and
does not enable central replay pushing.
