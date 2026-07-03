import asyncio
import os
from typing import Any

import httpx
from authplane_mcp import authplane_mcp_auth, require_scope
from mcp.server.fastmcp import FastMCP

NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"

# These must match the AuthPlane issuer and the canonical MCP resource URI.
AUTHPLANE_ISSUER = os.getenv("AUTHPLANE_ISSUER", "http://localhost:9000")
AUTHPLANE_RESOURCE = os.getenv(
    "AUTHPLANE_RESOURCE",
    "http://localhost:8000/mcp",
)
WEATHER_SCOPE = "weather:read"


async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None


def format_alert(feature: dict[str, Any]) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]

    return f"""
Event: {props.get("event", "Unknown")}
Area: {props.get("areaDesc", "Unknown")}
Severity: {props.get("severity", "Unknown")}
Description: {props.get("description", "No description available")}
Instructions: {props.get("instruction", "No specific instructions provided")}
"""


async def main() -> None:
    """Run the local weather MCP server with AuthPlane authentication."""

    auth_result = await authplane_mcp_auth(
        issuer=AUTHPLANE_ISSUER,
        resource=AUTHPLANE_RESOURCE,
        scopes=[WEATHER_SCOPE],
        enforce_scopes_on_all_requests=True,
        dev_mode=True,
    )

    mcp = FastMCP(
        "weather",
        host="127.0.0.1",
        port=8000,
        json_response=True,
        **auth_result,
    )

    @mcp.tool()
    async def get_alerts(state: str) -> str:
        """Get weather alerts for a two-letter US state code."""
        require_scope(WEATHER_SCOPE)

        url = f"{NWS_API_BASE}/alerts/active/area/{state}"
        data = await make_nws_request(url)

        if not data or "features" not in data:
            return "Unable to fetch alerts or no alerts found."

        if not data["features"]:
            return "No active alerts for this state."

        return "\n---\n".join(format_alert(feature) for feature in data["features"])

    @mcp.tool()
    async def get_forecast(latitude: float, longitude: float) -> str:
        """Get a weather forecast for a latitude and longitude."""
        require_scope(WEATHER_SCOPE)

        points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
        points_data = await make_nws_request(points_url)

        if not points_data:
            return "Unable to fetch forecast data for this location."

        forecast_url = points_data["properties"]["forecast"]
        forecast_data = await make_nws_request(forecast_url)

        if not forecast_data:
            return "Unable to fetch detailed forecast."

        forecasts = []
        for period in forecast_data["properties"]["periods"][:5]:
            forecasts.append(
                f"""
{period["name"]}:
Temperature: {period["temperature"]}°{period["temperatureUnit"]}
Wind: {period["windSpeed"]} {period["windDirection"]}
Forecast: {period["detailedForecast"]}
"""
            )

        return "\n---\n".join(forecasts)

    try:
        await mcp.run_streamable_http_async()
    finally:
        await auth_result.aclose()


if __name__ == "__main__":
    asyncio.run(main())
