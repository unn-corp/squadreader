"""Application-local TLS trust and credential-preserving redirect policy."""
from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import certifi


def _origin(url: str) -> tuple[str, str | None, int | None]:
    parts = urlsplit(url)
    return (parts.scheme.lower(), parts.hostname,
            parts.port or (443 if parts.scheme.lower() == "https" else 80))


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib copies custom authentication headers to redirects. Never send
        # them to another host/port or allow an HTTPS -> HTTP downgrade.
        if _origin(req.full_url) != _origin(newurl):
            raise urllib.error.HTTPError(req.full_url, code,
                                         "cross-origin redirect refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def tls_context() -> ssl.SSLContext:
    # Construct a clean context: create_default_context() plus load_verify_locations
    # would retain compromised roots from the host. Do not alter global SSL state.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=certifi.where())
    return context


def open_url(req: urllib.request.Request, *, timeout: float):
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=tls_context()), _SameOriginRedirect())
    return opener.open(req, timeout=timeout)
