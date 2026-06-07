from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict

from analytics.metrics import daily_returns, rolling_mean, rolling_std
from api.deps import get_db
from storage.repository import (
    get_asset_as_of,
    get_asset_history,
    get_current_asset,
    list_current_assets,
    query_timeseries,
)

router = APIRouter(prefix="/assets", tags=["assets"])


class AssetSummary(BaseModel):
    asset_id: str
    symbol: str
    asset_class: str
    region: str


class AssetDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset_id: str
    symbol: str
    asset_class: str
    region: str
    description: str | None = None
    valid_from: datetime
    valid_to: datetime | None = None
    is_deleted: bool
    attributes: dict | None = None


class TimeseriesRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset_id: str
    source_id: str
    data_timestamp: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    adj_close: float | None = None
    volume: int | None = None


class TimeseriesResponse(BaseModel):
    asset_id: str
    count: int
    records: list[TimeseriesRow]


@router.get("", operation_id="list_assets", response_model=list[AssetSummary])
async def list_assets(db: AsyncIOMotorDatabase = Depends(get_db)) -> list:
    """Return a summary list of all current (non-deleted) assets.

    Each item includes asset_id, symbol, asset_class, and region.
    Use GET /assets/{asset_id} for full details.
    """
    return await list_current_assets(db)


@router.get("/{asset_id}", operation_id="get_asset", response_model=AssetDetail)
async def get_asset(
    asset_id: str,
    as_of: datetime | None = Query(
        None,
        description=(
            "ISO 8601 timestamp. When provided, returns the asset version that was "
            "active at that point in time (valid_from <= t AND valid_to > t or null). "
            "Omit to get the current active version."
        ),
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Return full details of a single asset.

    Supports point-in-time lookup via ?as_of=<ISO8601>. Without as_of, returns
    the current active version. Returns 404 if the asset is not found or deleted.
    """
    if as_of is not None:
        asset = await get_asset_as_of(db, asset_id, as_of)
        if not asset:
            raise HTTPException(
                status_code=404,
                detail=f"Asset '{asset_id}' not found at {as_of.isoformat()}",
            )
    else:
        asset = await get_current_asset(db, asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    return asset


@router.get(
    "/{asset_id}/timeseries",
    operation_id="get_timeseries",
    response_model=TimeseriesResponse,
)
async def get_timeseries(
    asset_id: str,
    source_id: str | None = Query(None, description="Filter by data source (e.g. yfinance, csv-vendor)"),
    from_: datetime | None = Query(None, alias="from", description="Start of date range (inclusive), ISO 8601"),
    to: datetime | None = Query(None, description="End of date range (inclusive), ISO 8601"),
    limit: int = Query(500, ge=1, le=5000, description="Maximum number of rows to return"),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Return time series rows for a given asset within an optional date range.

    Optionally filter by source_id (data vendor) and/or a from/to date window.
    Results are sorted by data_timestamp ascending and capped at limit (default 500, max 5000).
    """
    if not await get_current_asset(db, asset_id):
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    records = await query_timeseries(db, asset_id, source_id, from_, to, limit)
    return {"asset_id": asset_id, "count": len(records), "records": records}


@router.get("/{asset_id}/history", operation_id="get_asset_history")
async def asset_history(
    asset_id: str, db: AsyncIOMotorDatabase = Depends(get_db)
) -> list:
    """Return all temporal versions of an asset, sorted by valid_from ascending."""
    history = await get_asset_history(db, asset_id)
    if not history:
        raise HTTPException(status_code=404, detail="Asset not found")
    return history


@router.get("/{asset_id}/analytics/returns", operation_id="get_returns")
async def get_returns(
    asset_id: str,
    source_id: str | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Return daily percentage returns for the asset's close prices."""
    if not await get_current_asset(db, asset_id):
        raise HTTPException(status_code=404, detail="Asset not found")
    records = await query_timeseries(db, asset_id, source_id, start, end, limit=5000)
    closes = [r["close"] for r in records]
    return {
        "asset_id": asset_id,
        "source_id": source_id,
        "count": len(records),
        "dates": [r["data_timestamp"] for r in records],
        "closes": closes,
        "daily_returns": daily_returns(closes),
    }


@router.get("/{asset_id}/analytics/rolling", operation_id="get_rolling")
async def get_rolling(
    asset_id: str,
    window: int = Query(20, ge=2, le=252),
    metric: str = Query("mean", pattern="^(mean|std)$"),
    source_id: str | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Return rolling mean or standard deviation of close prices."""
    if not await get_current_asset(db, asset_id):
        raise HTTPException(status_code=404, detail="Asset not found")
    records = await query_timeseries(db, asset_id, source_id, start, end, limit=5000)
    closes = [r["close"] for r in records]
    values = rolling_mean(closes, window) if metric == "mean" else rolling_std(closes, window)
    return {
        "asset_id": asset_id,
        "metric": metric,
        "window": window,
        "source_id": source_id,
        "count": len(records),
        "dates": [r["data_timestamp"] for r in records],
        "values": values,
    }
