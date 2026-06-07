from datetime import datetime

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from analytics.metrics import correlation
from api.deps import get_db
from storage.repository import query_timeseries

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/correlation", operation_id="get_correlation")
async def get_correlation(
    asset_a: str = Query(...),
    asset_b: str = Query(...),
    source_id: str | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    records_a = await query_timeseries(db, asset_a, source_id, start, end, limit=5000)
    records_b = await query_timeseries(db, asset_b, source_id, start, end, limit=5000)

    closes_a = {r["data_timestamp"]: r["close"] for r in records_a}
    closes_b = {r["data_timestamp"]: r["close"] for r in records_b}
    common = sorted(set(closes_a) & set(closes_b))

    corr = correlation([closes_a[d] for d in common], [closes_b[d] for d in common])
    return {
        "asset_a": asset_a,
        "asset_b": asset_b,
        "source_id": source_id,
        "n_common_dates": len(common),
        "correlation": corr,
    }
