"""Outbound HTTP security through owned loopback servers; no provider calls."""
from __future__ import annotations

import datetime
import ipaddress
import json
import ssl
import threading
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import certifi
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from sqreader import ingest_client as ic
from sqreader.plugins.notify import DiscordNotifier


@pytest.fixture(autouse=True)
def isolated_transport(monkeypatch):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    monkeypatch.setattr(ic.time, "sleep", lambda _: None)


@contextmanager
def server(reply, context=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):  # noqa: N802
            reply(self)

        do_POST = do_GET

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if context is not None:
        srv.socket = context.wrap_socket(srv.socket, server_side=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"{'https' if context else 'http'}://127.0.0.1:{srv.server_port}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=3)


def respond(req, body=b"ok"):
    req.send_response(200)
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)


def certificate(tmp_path, name):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.KeyUsage(True, False, True, False, False, True, True,
                                         False, False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                           critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),
                           critical=False)
            .sign(key, hashes.SHA256()))
    pem = tmp_path / f"{name}.pem"
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile = tmp_path / f"{name}.key"
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(pem, keyfile)
    return pem, context


@pytest.mark.parametrize("tls", [False, True])
def test_authenticated_download_refuses_foreign_redirect(tmp_path, monkeypatch, tls):
    received = []
    context = None
    if tls:
        ca, context = certificate(tmp_path, "redirect-fixture")
        monkeypatch.setattr(certifi, "where", lambda: str(ca))

    def destination(req):
        received.append(req.headers.get("X-Sqr-Auth"))
        respond(req)

    with server(destination) as foreign:
        def redirect(req):
            req.send_response(302)
            req.send_header("Location", foreign + "/capture")
            req.end_headers()

        with server(redirect, context) as central:
            req = urllib.request.Request(central + "/download",
                                         headers={"X-Sqr-Auth": "synthetic-auth"})
            with pytest.raises(ic.PushError, match="HTTP 302"):
                ic._send(req, timeout=1)
    assert received == []


def test_same_origin_redirect_preserves_download():
    def reply(req):
        if req.path == "/start":
            req.send_response(302)
            req.send_header("Location", "/artifact")
            req.end_headers()
        else:
            assert req.headers.get("X-Sqr-Auth") == "synthetic-auth"
            respond(req, b"synthetic-artifact")

    with server(reply) as central:
        req = urllib.request.Request(central + "/start",
                                     headers={"X-Sqr-Auth": "synthetic-auth"})
        assert ic._send(req, timeout=1) == b"synthetic-artifact"


def test_host_added_ca_cannot_override_application_trust(tmp_path, monkeypatch):
    host_ca, context = certificate(tmp_path, "host-only")
    app_ca, _ = certificate(tmp_path, "application-only")
    monkeypatch.setenv("SSL_CERT_FILE", str(host_ca))
    monkeypatch.setattr(certifi, "where", lambda: str(app_ca))
    with server(lambda req: respond(req), context) as central:
        with pytest.raises(ic.PushError, match="CERTIFICATE_VERIFY_FAILED"):
            ic._send(urllib.request.Request(central), timeout=1)


def test_trusted_tls_preserves_enrollment_and_notification(tmp_path, monkeypatch):
    ca, context = certificate(tmp_path, "trusted-fixture")
    monkeypatch.setattr(certifi, "where", lambda: str(ca))
    received = []

    def reply(req):
        received.append((req.path, json.loads(req.rfile.read(int(req.headers["Content-Length"])))))
        respond(req, json.dumps({"agent_id": "fixture-agent", "secret_hex": "a" * 64}).encode())

    with server(reply, context) as central:
        creds = ic.enroll(central, "synthetic-token", "synthetic-hw", timeout=1)
        assert creds["SQREADER_AGENT_ID"] == "fixture-agent"
        notifier = DiscordNotifier.__new__(DiscordNotifier)
        notifier._url = central + "/hook"
        notifier._replay_base = None
        notifier._server_label = None
        notifier._timeout = 1
        notifier._stop = threading.Event()
        notifier._post([{"player_name": "Synthetic", "alert_type": "fixture"}])
    assert received[0][0] == "/api/enroll"
    assert received[0][1]["token"] == "synthetic-token"
    assert received[1][0] == "/hook"
    assert len(received[1][1]["embeds"]) == 1
