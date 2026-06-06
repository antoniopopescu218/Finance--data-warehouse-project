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
            "valid_from": {"$lte": t},
            "$or": [{"valid_to": None}, {"valid_to": {"$gt": t}}],
        }
    )


async def get_current_asset(db: AsyncIOMotorDatabase, asset_id: str) -> dict | None:
    return await db.assets.find_one(
        {"asset_id": asset_id, "valid_to": None, "is_deleted": False}
    )


# ── timeseries (append-only) ──────────────────────────────────────────────────

async def insert_timeseries(db: AsyncIOMotorDatabase, records: list[dict]) -> int:
    if not records:
        return 0
    result = await db.timeseries.insert_many(records, ordered=False)
    return len(result.inserted_ids)
