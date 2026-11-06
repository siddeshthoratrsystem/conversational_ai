"""Local stand-in identity provider for development ONLY (spec 008). Never use in production.

Used when mock-oauth2-server can't be pulled. It offers the same paths and claims, so the
backend and web settings don't change:

  POST /default/token                          password grant -> signed access token
  GET  /default/jwks                           public keys
  GET  /default/.well-known/openid-configuration

Any username works and the password is not checked. Run: python -m devtools.stand_in_idp
"""

import json
import logging
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger("stand_in_idp")

TOKEN_LIFETIME = 3600
KID = "stand-in-1"


class StandIn:
    def __init__(self, issuer: str, audience: str):
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        base, _, issuer_id = self.issuer.rpartition("/")
        self.prefix = "/" + issuer_id
        self.base = base

    def issue_token(self, username: str) -> str:
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "aud": [self.audience],
            "sub": username,
            "iat": now,
            "nbf": now,
            "exp": now + TOKEN_LIFETIME,
            "ai_planning": True,  # spec 009: every stand-in user may use AI planning
        }
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": KID})

    def jwks(self) -> dict:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [{**jwk, "kid": KID, "use": "sig", "alg": "RS256"}]}

    def handle(self, method: str, path: str, headers: dict, body: bytes):
        """Pure request handler: returns (status, headers, body bytes). Easy to test."""
        out = {"Content-Type": "application/json"}
        origin = headers.get("Origin")
        if origin:
            out["Access-Control-Allow-Origin"] = origin
            out["Access-Control-Allow-Credentials"] = "true"

        if method == "OPTIONS":
            out["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
            out["Access-Control-Allow-Headers"] = headers.get("Access-Control-Request-Headers", "*")
            return 204, out, b""

        if method == "POST" and path == f"{self.prefix}/token":
            form = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}
            username = form.get("username", "").strip()
            if form.get("grant_type") != "password" or not username:
                return 400, out, json.dumps({"error": "invalid_request"}).encode()
            token = {
                "access_token": self.issue_token(username),
                "token_type": "Bearer",
                "expires_in": TOKEN_LIFETIME,
            }
            return 200, out, json.dumps(token).encode()

        if method == "GET" and path == f"{self.prefix}/jwks":
            return 200, out, json.dumps(self.jwks()).encode()

        if method == "GET" and path == f"{self.prefix}/.well-known/openid-configuration":
            doc = {
                "issuer": self.issuer,
                "token_endpoint": f"{self.issuer}/token",
                "jwks_uri": f"{self.issuer}/jwks",
            }
            return 200, out, json.dumps(doc).encode()

        return 404, out, json.dumps({"error": "not_found"}).encode()


def make_server(idp: StandIn, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _serve(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            status, headers, payload = idp.handle(
                self.command, self.path.split("?")[0], dict(self.headers.items()), body
            )
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_OPTIONS = _serve

        def log_message(self, fmt, *args):  # one line per request; never the body or a token
            logger.info("%s %s -> %s", self.command, self.path.split("?")[0], args[1] if len(args) > 1 else "")

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
    port = int(os.getenv("STAND_IN_PORT", "8090"))
    idp = StandIn(
        issuer=os.getenv("STAND_IN_ISSUER", f"http://localhost:{port}/default"),
        audience=os.getenv("STAND_IN_AUDIENCE", "convai-api"),
    )
    logger.info("Stand-in identity provider on :%s (issuer %s, audience %s)", port, idp.issuer, idp.audience)
    make_server(idp, port).serve_forever()


if __name__ == "__main__":
    main()
