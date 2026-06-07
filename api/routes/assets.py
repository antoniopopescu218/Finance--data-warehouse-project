import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict

from analytics.metrics import (
    compute_forecast,
    compute_risk,
    compute_summary,
    compute_trend,
    daily_returns,
    rolling_mean,
    rolling_std,
)
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


# ── Phase 3 analytics ─────────────────────────────────────────────────────────

@router.get("/{asset_id}/analytics/summary", operation_id="get_summary")
async def get_summary(
    asset_id: str,
    source_id: str | None = Query(None, description="Filter by data source"),
    from_: datetime | None = Query(None, alias="from", description="Start of window (inclusive), ISO 8601"),
    to: datetime | None = Query(None, description="End of window (inclusive), ISO 8601"),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Return count, min, max, and average of close prices over a date window.

    Optionally filter by source_id and a from/to date range.
    """
    if not await get_current_asset(db, asset_id):
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    records = await query_timeseries(db, asset_id, source_id, from_, to, limit=5000)
    if not records:
        raise HTTPException(status_code=404, detail="No timeseries data found for the given filters")
    closes = [r["close"] for r in records]
    return {
        "asset_id": asset_id,
        "source_id": source_id,
        "from": from_,
        "to": to,
        **compute_summary(closes),
    }


@router.get("/{asset_id}/analytics/trend", operation_id="get_trend")
async def get_trend(
    asset_id: str,
    source_id: str | None = Query(None, description="Filter by data source"),
    from_: datetime | None = Query(None, alias="from", description="Start of window (inclusive), ISO 8601"),
    to: datetime | None = Query(None, description="End of window (inclusive), ISO 8601"),
    window: int = Query(20, ge=2, le=252, description="Moving-average window in trading days"),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Return the period percentage change and a per-day list of close price with moving average.

    period_change_pct is (last_close - first_close) / first_close * 100.
    Each item in data contains date, close, and moving_avg computed over `window` days.
    """
    if not await get_current_asset(db, asset_id):
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    records = await query_timeseries(db, asset_id, source_id, from_, to, limit=5000)
    if not records:
        raise HTTPException(status_code=404, detail="No timeseries data found for the given filters")
    closes = [r["close"] for r in records]
    dates = [r["data_timestamp"] for r in records]
    return {
        "asset_id": asset_id,
        "source_id": source_id,
        **compute_trend(closes, dates, window),
    }


@router.get("/{asset_id}/analytics/forecast", operation_id="get_forecast")
async def get_forecast(
    asset_id: str,
    source_id: str | None = Query(None, description="Filter by data source"),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Return a naive last-close forecast and a linear-regression next-day prediction.

    Both forecasts are labeled so callers can distinguish them.
    naive_forecast repeats the last observed close price.
    linear_regression_forecast is an OLS trend extrapolated one period ahead.
    """
    if not await get_current_asset(db, asset_id):
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    records = await query_timeseries(db, asset_id, source_id, None, None, limit=5000)
    if not records:
        raise HTTPException(status_code=404, detail="No timeseries data found for the given filters")
    closes = [r["close"] for r in records]
    return {
        "asset_id": asset_id,
        "source_id": source_id,
        "n_observations": len(closes),
        **compute_forecast(closes),
    }


@router.get("/{asset_id}/analytics/risk", operation_id="get_risk")
async def get_risk(
    asset_id: str,
    source_id: str | None = Query(None, description="Filter by data source"),
    from_: datetime | None = Query(None, alias="from", description="Start of window (inclusive), ISO 8601"),
    to: datetime | None = Query(None, description="End of window (inclusive), ISO 8601"),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Return the most-recent 20-day rolling volatility and the maximum drawdown.

    rolling_20d_volatility is the annualisable standard deviation of daily returns
    over the last 20-day rolling window.
    max_drawdown is expressed as a negative fraction (e.g. -0.15 means -15%).
    """
    if not await get_current_asset(db, asset_id):
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    records = await query_timeseries(db, asset_id, source_id, from_, to, limit=5000)
    if not records:
        raise HTTPException(status_code=404, detail="No timeseries data found for the given filters")
    closes = [r["close"] for r in records]
    return {
        "asset_id": asset_id,
        "source_id": source_id,
        **compute_risk(closes),
    }


@router.get("/{asset_id}/timeseries/export", operation_id="export_timeseries")
async def export_timeseries(
    asset_id: str,
    source_id: str | None = Query(None, description="Filter by data source"),
    from_: datetime | None = Query(None, alias="from", description="Start of window (inclusive), ISO 8601"),
    to: datetime | None = Query(None, description="End of window (inclusive), ISO 8601"),
    format: str = Query("json", pattern="^(json|csv)$", description="Output format: json or csv"),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> object:
    """Export flat timeseries records for ML pipelines or Spark ingestion.

    Supports JSON (default) and CSV output. CSV sets Content-Type text/csv
    and a Content-Disposition attachment header. All numeric fields are included.
    """
    if not await get_current_asset(db, asset_id):
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    records = await query_timeseries(db, asset_id, source_id, from_, to, limit=5000)
    if not records:
        raise HTTPException(status_code=404, detail="No timeseries data found for the given filters")

    # Normalise datetime objects to ISO strings for serialisation
    flat = []
    for r in records:
        row = {}
        for k, v in r.items():
            row[k] = v.isoformat() if isinstance(v, datetime) else v
        flat.append(row)

    if format == "json":
        return flat

    # CSV output
    buf = io.StringIO()
    fieldnames = list(flat[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(flat)
    buf.seek(0)
    filename = f"{asset_id}_{source_id or 'all'}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
