# Securing a Public MCP Server with an AuthPlane-Compatible JWT Layer

## Overview

This project secures the public `weather-server-python` MCP tutorial server from the Model Context Protocol quickstart repository.

The original server exposes two tools:

- `get_alerts(state)`
- `get_forecast(latitude, longitude)`

The original implementation runs locally over stdio and has no bearer-token validation, caller identity check, scope requirement, or authorization boundary. That is acceptable for a tutorial example, but it would be unsafe if exposed over a network.

This prototype converts the server to local Streamable HTTP and adds an AuthPlane-compatible JWT resource-server layer. Clients must provide a valid bearer JWT with the `weather:read` scope.

## Repository and Security Posture

Source repository: `modelcontextprotocol/quickstart-resources`  
Selected component: `weather-server-python`

I selected this server because it is a small public MCP tutorial project with harmless weather tools and a limited codebase. The original source creates `FastMCP("weather")` and registers tools without a token verifier, authorization provider, bearer-token parser, identity check, or required scope.

The original server is appropriate for local learning, but an HTTP-exposed version would allow any reachable client to invoke its tools unless authentication and authorization were added.

## Implementation

The secured server:

- binds only to `127.0.0.1:8000`;
- uses Streamable HTTP at `/mcp`;
- requires `Authorization: Bearer <JWT>`;
- validates JWT signature, issuer, audience, issued-at time, expiration, and subject;
- requires `weather:read` before MCP initialization or tool access;
- uses the MCP SDK protected-resource metadata support.

`auth.py` provides `LocalJWTVerifier`, which returns an MCP `AccessToken` only after a JWT passes validation. `weather.py` wires that verifier into `FastMCP` and configures `required_scopes=["weather:read"]`.

This separates:

1. Authentication: Is the bearer token valid?
2. Authorization: Does the valid token include `weather:read`?

## Files Changed

| File | Purpose |
|---|---|
| `weather.py` | Secured Streamable HTTP MCP server configuration |
| `auth.py` | Local JWT validation layer |
| `test_server_auth.py` | Automated authorization-boundary tests |
| `weather_original.py` | Preserved original baseline |
| `.env.example` | Safe example environment variable |
| `.gitignore` | Prevents secrets and `.venv` from being committed |
| `pyproject.toml` | Explicit `PyJWT` dependency |

## Setup

Requirements: Python 3.10+. No Docker, cloud account, card, or public deployment is required.

Create and activate the environment:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e .

Create a local development secret:

    python -c "import secrets; print('MCP_JWT_SECRET=' + secrets.token_urlsafe(32))" > .env
    set -a
    source .env
    set +a

Start the secured server:

    python weather.py

The server is local only:

    http://127.0.0.1:8000/mcp

## Tests

Run:

    python -m unittest -v test_server_auth.py

Verified results:

| Case | Result |
|---|---|
| No bearer token | `401 Unauthorized` |
| Valid JWT without `weather:read` | `403 Forbidden` |
| Valid JWT with `weather:read` | `200 OK` |
| Valid JWT calls `get_alerts("CA")` | `200 OK`, successful MCP tool result |

The automated tests do not invoke the weather tools or contact the National Weather Service API. A separate manual end-to-end test confirmed an authorized tool call succeeds.

## Comparison

| Dimension | Original server | Secured prototype |
|---|---|---|
| Authentication model | None | Bearer JWT required |
| Developer effort | Minimal tutorial setup | Verifier, config, tests, local secret |
| Security posture | No caller identity or scopes | Signature, claims, and scope checks |
| Deployment complexity | Low | Moderate; issuer and secret configuration |
| Documentation quality | Brief tutorial README | Setup, tests, tradeoffs, limitations |
| Auditability | No auth decisions | HTTP auth outcomes visible; production logging still needed |
| Limitations | No auth layer | Local HS256 secret; no JWKS, OAuth flow, rotation, or revocation |

## Production Considerations

This local prototype is for evaluation only. Production use should replace the local shared secret with an authorization server such as AuthPlane, asymmetric signing keys and JWKS discovery, HTTPS, key rotation, revocation, secure secret storage, structured audit logs, rate limiting, and more granular authorization policies.

## AuthPlane Developer-Experience Observation

The MCP SDK made the resource-server model clear: a verifier validates a bearer token, while `AuthSettings` expresses resource metadata and required scopes.

AuthPlane would be valuable in production as the centralized issuer and policy layer, replacing the local development secret with OAuth token issuance, JWKS discovery, key rotation, and managed scope policy. The local compatible verifier made it possible to validate the resource-server behavior without Docker or a cloud deployment.

## Attribution

This project adapts the public `weather-server-python` tutorial from the Model Context Protocol `quickstart-resources` repository. The upstream license notice is preserved in `LICENSE`.
