"""
Temporal correctness test.

Verifies the repository's append-only versioning by:
  1. Inserting an asset (v1).
  2. "Updating" it — inserting a new version (v2) which closes v1.
  3. "Deleting" it — inserting a tombstone which closes v2.

Then asserts get_asset_as_of returns the correct state at three timestamps:
  t_before_v1  -> None (asset didn't exist yet)
  t_during_v1  -> v1 data
  t_during_v2  -> v2 data
  t_after_del  -> None (asset logically deleted)

Run against a live MongoDB:
    uv run pytest tests/test_temporal.py -v
"""
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from storage.repository import (
    get_asset_as_of,
    insert_asset_version,
    mark_deleted,
)

MONGO_URL = "mongodb://localhost:27017"
MONGO_DB = "dwh_test"
ASSET_ID = "__temporal_test_asset__"


@pytest.fixture
async def db():
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[MONGO_DB]
    await database.assets.delete_many({"asset_id": ASSET_ID})
    yield database
    await database.assets.delete_many({"asset_id": ASSET_ID})
    client.close()


async def _recorded_insert(db, asset_id: str, data: dict) -> datetime:
    """Insert a new version and return a timestamp known to be inside that version."""
    t_before = datetime.now(timezone.utc)
    await insert_asset_version(db, asset_id, data)
    t_after = datetime.now(timezone.utc)
    # A timestamp safely inside this version window
    return t_before + (t_after - t_before) / 2


async def _recorded_delete(db, asset_id: str) -> datetime:
    """Mark asset deleted and return a timestamp known to be after the tombstone."""
    t_before = datetime.now(timezone.utc)
    await mark_deleted(db, asset_id)
    t_after = datetime.now(timezone.utc)
    return t_before + (t_after - t_before) / 2


@pytest.mark.asyncio
async def test_temporal_versioning(db):
    # ── Step 1: record a point in time before the asset ever exists ──────────
    t_before_v1 = datetime.now(timezone.utc) - timedelta(seconds=1)

    # ── Step 2: insert v1 ────────────────────────────────────────────────────
    t_during_v1 = await _recorded_insert(db, ASSET_ID, {
        "symbol": "TEST",
        "asset_class": "equity",
        "region": "US",
        "description": "version 1",
    })

    # ── Step 3: insert v2 (closes v1) ────────────────────────────────────────
    t_during_v2 = await _recorded_insert(db, ASSET_ID, {
        "symbol": "TEST",
        "asset_class": "equity",
        "region": "US",
        "description": "version 2",
    })

    # ── Step 4: mark deleted (closes v2) ─────────────────────────────────────
    t_after_del = await _recorded_delete(db, ASSET_ID)
    # Push a bit further past the deletion timestamp
    t_after_del = t_after_del + timedelta(seconds=1)

    # ── Assertions ───────────────────────────────────────────────────────────

    # Before the asset existed -> None
    result = await get_asset_as_of(db, ASSET_ID, t_before_v1)
    assert result is None, (
        f"Expected None before v1, got: {result}"
    )

    # During v1 -> description == "version 1"
    result = await get_asset_as_of(db, ASSET_ID, t_during_v1)
    assert result is not None, "Expected v1, got None"
    assert result["description"] == "version 1", (
        f"Expected 'version 1', got '{result['description']}'"
    )

    # During v2 -> description == "version 2"
    result = await get_asset_as_of(db, ASSET_ID, t_during_v2)
    assert result is not None, "Expected v2, got None"
    assert result["description"] == "version 2", (
        f"Expected 'version 2', got '{result['description']}'"
    )

    # After deletion -> None (is_deleted tombstone is excluded by get_asset_as_of)
    result = await get_asset_as_of(db, ASSET_ID, t_after_del)
    assert result is None, (
        f"Expected None after deletion, got: {result}"
    )
