# SquadReader GC Maps Specs

Specs for adapting SquadReader to Galactic Contention and validating it against one controlled live server build.

## Documents

- [GC compatibility spike](./001-gc-compatibility-spike.md) — scope, capabilities, constraints, and success criteria.
- [Runtime inventory and metadata adapter](./002-runtime-inventory-and-metadata.md) — identifiers, manifests, mappings, and coverage rules.
- [Live server validation plan](./003-live-server-validation.md) — test environment, fixture matrix, failure classification, and go/no-go rules.
- [Local asset extraction and live test build](./004-local-asset-extraction-and-test-build.md) — package inputs, derived assets, adapter generation, harness phases, and failure codes.
- [GC Maps pattern traceability](./005-gc-maps-patterns-traceability.md) — learned extractor patterns mapped to SquadReader requirements and verification.

## Current boundary

This branch contains specifications only. Runtime extraction, live-server testing, catalog changes, and frontend integration start after the compatibility spike scope is reviewed.
