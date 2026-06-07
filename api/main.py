from contextlib import asynccontextmanager

from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from api.config import settings
from api.routes.analytics import router as analytics_router
from api.routes.assets import router as assets_router
from api.routes.sources import router as sources_router
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
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(sources_router)
app.include_router(assets_router)
app.include_router(analytics_router)


@app.get("/health", operation_id="health_check", tags=["meta"])
async def health() -> dict:
    await app.state.db.command("ping")
    return {"status": "ok", "db": settings.mongo_db}
