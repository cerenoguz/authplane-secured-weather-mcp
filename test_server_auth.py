"""Integration tests for the local MCP authentication boundary.

These tests start the server only on 127.0.0.1 and never invoke weather tools.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

import httpx
import jwt

ROOT = Path(__file__).resolve().parent


def load_local_env() -> None:
    """Load the local development secret without committing it to source control."""
    env_file = ROOT / ".env"
    for line in env_file.read_text().splitlines():
        if line.startswith("MCP_JWT_SECRET="):
            os.environ.setdefault("MCP_JWT_SECRET", line.split("=", 1)[1])


load_local_env()

from auth import DEFAULT_AUDIENCE, DEFAULT_ISSUER  # noqa: E402


def make_token(scope: str) -> str:
    """Create a short-lived local development token."""
    now = int(time.time())
    return jwt.encode(
        {
            "sub": "demo-user",
            "client_id": "local-test-client",
            "iss": DEFAULT_ISSUER,
            "aud": DEFAULT_AUDIENCE,
            "iat": now,
            "exp": now + 300,
            "scope": scope,
        },
        os.environ["MCP_JWT_SECRET"],
        algorithm="HS256",
    )


class TestMCPAuthorizationBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = subprocess.Popen(
            [sys.executable, "weather.py"],
            cwd=ROOT,
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

        deadline = time.time() + 8
        while time.time() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError("The local MCP server stopped before tests could run.")

            try:
                httpx.get(
                    "http://127.0.0.1:8000/.well-known/oauth-protected-resource",
                    timeout=0.25,
                )
                return
            except httpx.HTTPError:
                time.sleep(0.1)

        raise RuntimeError("Timed out waiting for the local MCP server to start.")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        try:
            cls.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=5)

    @staticmethod
    def initialize(token: str | None = None) -> httpx.Response:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        return httpx.post(
            "http://127.0.0.1:8000/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "local-security-test",
                        "version": "1.0",
                    },
                },
            },
            timeout=5,
        )

    def test_missing_token_is_rejected(self) -> None:
        response = self.initialize()

        self.assertEqual(response.status_code, 401)
        self.assertIn("Authentication required", response.text)

    def test_valid_token_without_required_scope_is_rejected(self) -> None:
        response = self.initialize(make_token(scope=""))

        self.assertEqual(response.status_code, 403)
        self.assertIn("Required scope: weather:read", response.text)

    def test_valid_scoped_token_can_initialize(self) -> None:
        response = self.initialize(make_token(scope="weather:read"))

        self.assertEqual(response.status_code, 200)
        self.assertIn('"serverInfo"', response.text)


if __name__ == "__main__":
    unittest.main()
