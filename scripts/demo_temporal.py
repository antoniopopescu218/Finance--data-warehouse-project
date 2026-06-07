"""
Temporal demo: shows append-only versioning for MSFT.

Steps:
  1. Print the current MSFT version.
  2. Apply a temporal update (insert new version, seal the old one).
  3. Query as-of just before the update  -> old version.
     Query as-of now                     -> new version.
     Both rows are printed so valid_from / valid_to / description differ visibly.
"""
import asyncio
import json
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from storage.repository import get_asset_as_of, get_current_asset, insert_asset_version

MONGO_URL = "mongodb://localhost:27017"
MONGO_DB = "dwh"
ASSET_ID = "MSFT"

DESC_A = "Microsoft Corp."
DESC_B = "Microsoft Corporation"


def _fmt(doc: dict | None) -> str:
    if doc is None:
        return "  (not found)"
    out = {}
    for k, v in doc.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif k == "attributes":
            out[k] = "(omitted for brevity)"
        else:
            out[k] = v
    return json.dumps(out, indent=2, default=str)


async def main() -> None:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[MONGO_DB]

    # ── Step 1: current state ──────────────────────────────────────────────────
    current = await get_current_asset(db, ASSET_ID)
    if current is None:
        print("MSFT not found in database — run scripts/seed.py first.")
        client.close()
        return

    print("=" * 60)
    print("STEP 1 — Current MSFT version (before update)")
    print("=" * 60)
    print(_fmt(current))

    # Choose the new description based on what is stored now so the demo is
    # idempotent across multiple runs.
    new_desc = DESC_B if current.get("description") == DESC_A else DESC_A

    # ── Step 2: temporal update ────────────────────────────────────────────────
    # Capture a point-in-time strictly before the write so we can query it later.
    t_before = datetime.now(timezone.utc)

    # Small gap so t_before is guaranteed to be < valid_from of the new version.
    await asyncio.sleep(0.01)

    updated_data = {
        k: v
        for k, v in current.items()
        if k not in ("valid_from", "valid_to", "is_deleted")
    }
    updated_data["description"] = new_desc

    await insert_asset_version(db, ASSET_ID, updated_data)

    # Read back the new version to learn the exact update timestamp.
    new_version = await get_current_asset(db, ASSET_ID)
    update_time: datetime = new_version["valid_from"]  # type: ignore[index]

    print()
    print("=" * 60)
    print("STEP 2 — Temporal update applied")
    print(f"  description : '{current.get('description')}' -> '{new_desc}'")
    print(f"  update_time (new valid_from): {update_time.isoformat()}")
    print(f"  t_before                    : {t_before.isoformat()}")
    print("=" * 60)

    # ── Step 3: bi-temporal queries ────────────────────────────────────────────
    t_after = datetime.now(timezone.utc)

    old = await get_asset_as_of(db, ASSET_ID, t_before)
    new = await get_asset_as_of(db, ASSET_ID, t_after)

    print()
    print("STEP 3a — MSFT as-of BEFORE update")
    print(f"          query time: {t_before.isoformat()}")
    print(_fmt(old))

    print()
    print("STEP 3b — MSFT as-of NOW (after update)")
    print(f"          query time: {t_after.isoformat()}")
    print(_fmt(new))

    print()
    print("── Diff summary ──────────────────────────────────────────")
    if old and new:
        def _iso(v):
            return v.isoformat() if isinstance(v, datetime) else str(v)

        print(f"  old description : {old.get('description')}")
        print(f"  new description : {new.get('description')}")
        print(f"  old valid_from  : {_iso(old.get('valid_from'))}")
        print(f"  old valid_to    : {_iso(old.get('valid_to'))}")
        print(f"  new valid_from  : {_iso(new.get('valid_from'))}")
        print(f"  new valid_to    : {_iso(new.get('valid_to'))}")
    print("==========================================================")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
