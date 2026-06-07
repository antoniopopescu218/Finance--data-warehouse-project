"""MCP server — exposes the entire Financial Markets DWH API as MCP tools.

Usage (stdio transport, for Claude Desktop):
    uv run python mcp_server.py

Usage (Inspector / HTTP):
    uv run fastmcp dev mcp_server.py
"""

from fastmcp import FastMCP

from api.main import app

mcp: FastMCP = FastMCP.from_fastapi(app=app, name="Financial Markets DWH")

if __name__ == "__main__":
    mcp.run()