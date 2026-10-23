# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for a security problem. Use GitHub's
private ["Report a vulnerability"](https://github.com/cagrianilokumus/squadreader/security/advisories/new)
advisory flow, or contact the maintainer privately.

Include: the affected version or commit, your OS, the Squad server version, and
steps to reproduce. You'll get an acknowledgement within a reasonable time and
we'll coordinate a fix and disclosure.

## Scope

sqreader reads local process memory and serves a local HTTP endpoint. The most
relevant areas are:

- the `serve` HTTP surface — authentication is intentionally delegated to your
  reverse proxy (see `deploy/`); running it exposed without one is misuse, not a
  vulnerability;
- path handling for served static files (`/icons`, `/sqmaps`, the SPA);
- the stats database, which stores player identifiers (see `PRIVACY.md`).

## Supported versions

Outbound enrollment, push, update and notification requests use the application's
certifi CA bundle (2026.10.19 or newer), without adding host or environment CA
stores. Custom host roots must not re-enable distrusted issuers. Redirects stay
on the same scheme, hostname and port; cross-origin redirects, including HTTPS
to HTTP downgrades, are refused before forwarding authentication headers. Point
the configured central/webhook URL directly at its final origin. Explicit local
HTTP development endpoints remain supported.

The shell installer refuses all download redirects, including same-origin ones;
configure its central URL with the final endpoint. Its bootstrap downloads use
host curl and system CA trust, so a vendor-patched curl/TLS runtime and CA store
are prerequisites. The agent's certifi bundle does not patch the installer or
the initial command used to download it.

Rebuild the committed frontend after dependency changes. Compiled agents must
include certifi's data bundle; `sqreader selftest` checks it without networking.
Updating this source does not patch already distributed binaries, host Python /
OpenSSL, reverse-proxy NGINX or a game-server container. Verify those artifacts
and their vendor security updates separately before deployment.

Only the latest release receives security fixes.
