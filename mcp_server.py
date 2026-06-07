"""MCP server — exposes the entire Financial Markets DWH API as MCP tools.

Usage (stdio transport, for Claude Desktop):
    uv run python mcp_server.py

Usage (Inspector / HTTP):
    uv run fastmcp dev mcp_server.py
"""

from contextlib import asynccontextmanager

from fastmcp import FastMCP
from motor.motor_asyncio import AsyncIOMotorClient

from api.config import settings
from api.main import app
from storage.repository import ensure_indexes


@asynccontextmanager
async def _db_lifespan(server: FastMCP):
    app.state.mongo = AsyncIOMotorClient(settings.mongo_url)
    app.state.db = app.state.mongo[settings.mongo_db]
    await ensure_indexes(app.state.db)
    yield
    app.state.mongo.close()


mcp: FastMCP = FastMCP.from_fastapi(
    app=app,
    name="Financial Markets DWH",
    lifespan=_db_lifespan,
)

if __name__ == "__main__":
    mcp.run()
