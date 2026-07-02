"""Local JWT validation for the secured MCP weather-server prototype.

This is an AuthPlane-compatible resource-server layer for local evaluation.
It validates bearer JWTs before the MCP server accepts protected requests.
"""

from __future__ import annotations

import os
from typing import Any

import jwt
from jwt import InvalidTokenError
from mcp.server.auth.provider import AccessToken, TokenVerifier

JWT_ALGORITHM = "HS256"
DEFAULT_ISSUER = "http://127.0.0.1:9000"
DEFAULT_AUDIENCE = "weather-mcp"


class LocalJWTVerifier(TokenVerifier):
    """Validate locally issued development JWTs for the MCP resource server."""

    def __init__(
        self,
        *,
        issuer: str = DEFAULT_ISSUER,
        audience: str = DEFAULT_AUDIENCE,
        secret: str | None = None,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.secret = secret or os.getenv("MCP_JWT_SECRET")

        if not self.secret:
            raise RuntimeError(
                "MCP_JWT_SECRET is not set. Set a local development secret before starting the server."
            )

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return an AccessToken only when the JWT passes all required checks."""
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self.secret,
                algorithms=[JWT_ALGORITHM],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except InvalidTokenError:
            return None

        raw_scope = claims.get("scope", "")
        scopes = raw_scope.split() if isinstance(raw_scope, str) else list(raw_scope)

        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id", claims["sub"])),
            scopes=scopes,
            expires_at=int(claims["exp"]),
            subject=str(claims["sub"]),
            claims=claims,
        )
