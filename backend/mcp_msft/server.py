"""stdio MCP server: one fixed read-only Microsoft tool, no external server account."""
from mcp.server.fastmcp import FastMCP
from .sources import fetch_update

server = FastMCP('HedgeHog Microsoft verifier', log_level='ERROR')


@server.tool()
def refresh_microsoft() -> dict:
    """Fetch Microsoft's market history, company news and verified earnings announcement."""
    return fetch_update()


if __name__ == '__main__':
    server.run(transport='stdio')
