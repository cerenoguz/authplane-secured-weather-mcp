# Securing a Public MCP Server with AuthPlane


## Overview

This project secures the public `weather-server-python` tutorial from the Model Context Protocol quickstart repository.

The original server exposes two weather tools:

* `get_alerts(state)`
* `get_forecast(latitude, longitude)`

Originally, the server ran locally over stdio and did not validate bearer tokens, identify callers, require scopes, or enforce an authorization boundary. That is appropriate for a tutorial, but an HTTP-exposed version would allow any reachable client to invoke its tools.

## Repository Selection and Security Posture

**Source repository:** [`modelcontextprotocol/quickstart-resources`](https://github.com/modelcontextprotocol/quickstart-resources)
**Selected component:** `weather-server-python`

I selected this server because it is a small official MCP tutorial project with a limited, understandable codebase and weather-only tools. It does not access email, files, databases, Slack, browser automation, or other sensitive systems.

The original implementation creates `FastMCP("weather")` and registers tools without a token verifier, bearer-token processing, user identity, required scopes, or authorization checks.

All MCP and AuthPlane work in this project was performed locally. The authorized weather-tool test calls the public U.S. National Weather Service API through the tutorial server’s normal functionality; it does not interact with a live third-party MCP deployment.

## AuthPlane Implementation

I ran the actual AuthPlane authorization server locally in Docker, bound only to `127.0.0.1` on ports 9000 and 9001. I registered `http://localhost:8000/mcp` as an AuthPlane Mint Resource with the `weather:read` scope, then created a confidential client using the client-credentials grant. In `weather.py`, I replaced the custom local JWT verifier with AuthPlane’s official `authplane-mcp` adapter. `authplane_mcp_auth(...)` discovers AuthPlane authorization-server metadata, retrieves JWKS signing keys, configures JWT validation for the registered resource URI, and returns the verifier and authentication settings passed into `FastMCP`. The server publishes MCP protected-resource metadata, and each weather tool calls `require_scope("weather:read")` before executing.

The secured MCP endpoint remains local-only:

```text
http://127.0.0.1:8000/mcp
```

## Files Changed

| File                     | Purpose                                                                                      |
| ------------------------ | -------------------------------------------------------------------------------------------- |
| `weather.py`             | Local Streamable HTTP MCP server protected by AuthPlane                                      |
| `weather_original.py`    | Preserved baseline implementation                                                            |
| `pyproject.toml`         | Adds `authplane-mcp` and pins a compatible MCP SDK version                                   |
| `.env.authplane.example` | Safe template for local AuthPlane configuration                                              |
| `.gitignore`             | Prevents secrets, temporary credential output, and virtual environments from being committed |
| `README.md`              | Setup, verification, tradeoffs, and implementation notes                                     |

## Local Setup

Tested with Python 3.13, Docker Desktop, `curl`, and `jq`.

Create the Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Create local AuthPlane secrets:

```bash
python -c "import secrets; print('AUTHPLANE_ADMIN_API_KEY=' + secrets.token_hex(32)); print('AUTHPLANE_SESSION_SECRET=' + secrets.token_hex(32))" > .env.authplane
```

Start AuthPlane locally:

```bash
docker run -d \
  --name authplane-weather \
  --env-file .env.authplane \
  -p 127.0.0.1:9000:9000 \
  -p 127.0.0.1:9001:9001 \
  -e AUTHPLANE_CLIENT_CREDENTIALS_ENABLED=true \
  -e AUTHPLANE_DPOP_ENABLED=true \
  -e AUTHPLANE_TOKEN_EXCHANGE_ENABLED=true \
  -v authplane-weather-data:/data \
  authplane/authserver:latest serve
```

Confirm that the local AuthPlane server is healthy:

```bash
curl -sS http://localhost:9000/health
```

Register the MCP Resource. The URI must remain identical in the AuthPlane Resource registration, `weather.py`, and token requests:

```bash
source .env.authplane

curl -sS -X POST http://localhost:9001/admin/resources \
  -H "Authorization: Bearer $AUTHPLANE_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "weather-mcp",
    "uri": "http://localhost:8000/mcp",
    "backend_kind": "mint",
    "display_name": "AuthPlane Weather MCP",
    "scopes": [
      {
        "name": "weather:read",
        "description": "Read weather alerts and forecasts"
      }
    ]
  }'
```

Create a client-credentials client:

```bash
curl -sS -X POST http://localhost:9001/admin/clients \
  -H "Authorization: Bearer $AUTHPLANE_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "weather-mcp-test-client",
    "grant_types": ["client_credentials"],
    "token_endpoint_auth_method": "client_secret_post",
    "scope": "weather:read"
  }' > .authplane-client.json

CLIENT_ID="$(jq -r '.client_id' .authplane-client.json)"
CLIENT_SECRET="$(jq -r '.client_secret' .authplane-client.json)"

printf '\nAUTHPLANE_CLIENT_ID=%s\nAUTHPLANE_CLIENT_SECRET=%s\n' \
  "$CLIENT_ID" "$CLIENT_SECRET" >> .env.authplane

rm -f .authplane-client.json
```

Start the protected MCP server:

```bash
python weather.py
```

## Verification

In a separate Terminal, mint an AuthPlane-issued access token:

```bash
source .env.authplane

TOKEN_RESPONSE="$(curl -sS -X POST http://localhost:9000/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=$AUTHPLANE_CLIENT_ID" \
  -d "client_secret=$AUTHPLANE_CLIENT_SECRET" \
  -d "resource=http://localhost:8000/mcp" \
  -d "scope=weather:read")"

ACCESS_TOKEN="$(printf '%s' "$TOKEN_RESPONSE" | jq -r '.access_token')"

printf '%s' "$TOKEN_RESPONSE" | jq '{token_type, expires_in, scope}'
```

Verify that unauthenticated MCP initialization is rejected:

```bash
curl -i -sS -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

Verify that an AuthPlane-issued token is accepted:

```bash
curl -i -sS -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

Completed local verification results:

| Case                                       | Result                                 |
| ------------------------------------------ | -------------------------------------- |
| No bearer token during MCP initialization  | `401 Unauthorized`                     |
| AuthPlane-issued token with `weather:read` | `200 OK` during MCP initialization     |
| Authenticated `tools/list` request         | `200 OK`; both weather tools available |
| Authenticated `get_alerts("CA")` call      | `200 OK`; successful tool result       |

The successful weather-tool call used an AuthPlane-issued bearer token, not a locally self-signed HMAC token.

## Comparison

| Dimension                    | Original Server                                 | Secured Version                                                                                                             |
| ---------------------------- | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Authentication model         | None                                            | AuthPlane-issued bearer JWT required                                                                                        |
| Developer effort             | Minimal tutorial setup                          | Local AuthPlane server, Resource/client registration, SDK integration, and end-to-end verification                          |
| Security posture             | No caller identity, token validation, or scopes | AuthPlane JWKS-backed JWT validation, audience binding, protected-resource metadata, and scope enforcement                  |
| Deployment complexity        | Low                                             | Low for local development; higher in production with HTTPS and operational controls                                         |
| Documentation quality        | Tutorial-focused                                | Setup, validation evidence, tradeoffs, and production considerations                                                        |
| Auditability / observability | No authorization decisions                      | Authorization outcomes visible through `401` and `200` responses; structured audit logging remains a production requirement |
| Known limitations            | No authentication layer                         | Local Docker configuration, localhost HTTP development mode, machine identity only, and no production lifecycle operations  |

## Developer-Experience Notes

The AuthPlane adapter fit the existing MCP Python SDK cleanly: the central code change was creating `authplane_mcp_auth(...)` once and unpacking its result into `FastMCP`. The main integration challenge was keeping the canonical Resource URI identical across AuthPlane Resource registration, SDK configuration, and the client token request, because that URI is also the token audience. For local development, `dev_mode=True` is required because the issuer and MCP server use localhost HTTP rather than production HTTPS.

## Production Considerations

This is a local evaluation prototype. A production deployment should use HTTPS, a non-development issuer, durable AuthPlane configuration, structured audit logging, monitoring, rate limits, client lifecycle management, secret rotation, and more granular authorization policy. It should also avoid relying on a broadly shared machine credential when end-user or agent identity is needed.

## Attribution

This project adapts the public `weather-server-python` tutorial from the Model Context Protocol `quickstart-resources` repository. The upstream license notice is preserved in `LICENSE`.
