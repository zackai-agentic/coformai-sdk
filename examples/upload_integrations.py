"""Upload REST and MCP configurations. Requires integrations:write.

Set COFORM_* and COFORM_MCP_URL. Expected: parsed integration responses;
OAuth provider links are printed if user interaction is needed.
"""
import os
from pathlib import Path
from typing import Any
from coformai import Coform


def run(client: Coform, mcp_url: str) -> tuple[Any, Any]:
    """Upload the included REST spec and discover a public MCP server's tools."""
    rest = client.uploads.rest(Path(__file__).with_name("service.openapi.json"), name="SDK Example API")
    mcp = client.uploads.mcp("SDK Example MCP", "Example remote tools", {
        "servers": {"example": {"url": mcp_url, "type": "none"}},
    })
    return rest, mcp


if __name__ == "__main__":
    with Coform() as client:
        print(run(client, os.environ["COFORM_MCP_URL"]))
