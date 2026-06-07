from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.assets.create_index([("asset_id", 1), ("valid_from", 1)])
    await db.timeseries.create_index(
        [("asset_id", 1), ("source_id", 1), ("data_timestamp", 1)]
    )


# ── data_sources ──────────────────────────────────────────────────────────────

async def upsert_source(db: AsyncIOMotorDatabase, source: dict) -> None:
    await db.data_sources.update_one(
        {"source_id": source["source_id"]},
        {"$set": source},
        upsert=True,
    )


# ── assets (temporal / append-only) ──────────────────────────────────────────

async def insert_asset_version(
    db: AsyncIOMotorDatabase, asset_id: str, data: dict
) -> None:
    now = _now()
    await db.assets.update_one(
        {"asset_id": asset_id, "valid_to": None, "is_deleted": False},
        {"$set": {"valid_to": now}},
    )
    await db.assets.insert_one(
        {"asset_id": asset_id, "valid_from": now, "valid_to": None, "is_deleted": False, **data}
    )


async def mark_deleted(db: AsyncIOMotorDatabase, asset_id: str) -> None:
    now = _now()
    await db.assets.update_one(
        {"asset_id": asset_id, "valid_to": None},
        {"$set": {"valid_to": now}},
    )
    await db.assets.insert_one(
        {"asset_id": asset_id, "valid_from": now, "valid_to": None, "is_deleted": True}
    )


async def get_asset_as_of(
    db: AsyncIOMotorDatabase, asset_id: str, t: datetime
) -> dict | None:
    return await db.assets.find_one(
        {
            "asset_id": asset_id,
            "is_deleted": False,
            "valid_from": {"$lte": t},
            "$or": [{"valid_to": None}, {"valid_to": {"$gt": t}}],
        },
        {"_id": 0},
    )


async def get_current_asset(db: AsyncIOMotorDatabase, asset_id: str) -> dict | None:
    return await db.assets.find_one(
        {"asset_id": asset_id, "valid_to": None, "is_deleted": False},
        {"_id": 0},
    )


# ── timeseries (append-only) ──────────────────────────────────────────────────

async def insert_timeseries(db: AsyncIOMotorDatabase, records: list[dict]) -> int:
    if not records:
        return 0
    result = await db.timeseries.insert_many(records, ordered=False)
    return len(result.inserted_ids)


# ── query helpers (Phase 2) ───────────────────────────────────────────────────

async def list_current_assets(db: AsyncIOMotorDatabase) -> list[dict]:
    cursor = db.assets.find({"valid_to": None, "is_deleted": False}, {"_id": 0})
    return await cursor.to_list(length=None)


async def get_asset_history(db: AsyncIOMotorDatabase, asset_id: str) -> list[dict]:
    cursor = db.assets.find({"asset_id": asset_id}, {"_id": 0}).sort("valid_from", 1)
    return await cursor.to_list(length=None)


async def list_sources(db: AsyncIOMotorDatabase) -> list[dict]:
    cursor = db.data_sources.find({}, {"_id": 0})
    return await cursor.to_list(length=None)


async def get_source(db: AsyncIOMotorDatabase, source_id: str) -> dict | None:
    return await db.data_sources.find_one({"source_id": source_id}, {"_id": 0})


async def query_timeseries(
    db: AsyncIOMotorDatabase,
    asset_id: str,
    source_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 500,
) -> list[dict]:
    filt: dict[str, Any] = {"asset_id": asset_id}
    if source_id:
        filt["source_id"] = source_id
    if start or end:
        ts_filt: dict[str, Any] = {}
        if start:
            ts_filt["$gte"] = start
        if end:
            ts_filt["$lte"] = end
        filt["data_timestamp"] = ts_filt
    cursor = (
        db.timeseries.find(filt, {"_id": 0})
        .sort("data_timestamp", 1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)
