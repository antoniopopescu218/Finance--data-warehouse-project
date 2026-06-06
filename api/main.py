from contextlib import asynccontextmanager

from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from api.config import settings
from storage.repository import ensure_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mongo = AsyncIOMotorClient(settings.mongo_url)
    app.state.db = app.state.mongo[settings.mongo_db]
    await ensure_indexes(app.state.db)
    yield
    app.state.mongo.close()


app = FastAPI(
    title="Financial Markets DWH",
    description="Temporal NoSQL data warehouse for financial market data.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", operation_id="health_check", tags=["meta"])
async def health() -> dict:
    await app.state.db.command("ping")
    return {"status": "ok", "db": settings.mongo_db}
