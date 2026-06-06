"""
Seed script: inserts data_sources, asset versions, and timeseries from
yfinance and csv-vendor for 5 symbols. Safe to re-run (skips existing assets).
"""
import asyncio
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from ingest.yfinance_adapter import YFinanceAdapter
from ingest.csv_vendor_adapter import CsvVendorAdapter
from storage.repository import (
    ensure_indexes,
    upsert_source,
    insert_asset_version,
    get_current_asset,
    insert_timeseries,
)

MONGO_URL = "mongodb://localhost:27017"
MONGO_DB = "dwh"

SYMBOLS = [
    {"symbol": "AAPL",  "asset_class": "equity", "region": "US", "description": "Apple Inc."},
    {"symbol": "MSFT",  "asset_class": "equity", "region": "US", "description": "Microsoft Corp."},
    {"symbol": "TSLA",  "asset_class": "equity", "region": "US", "description": "Tesla Inc."},
    {"symbol": "^GSPC", "asset_class": "index",  "region": "US", "description": "S&P 500 Index"},
    {"symbol": "GLD",   "asset_class": "etf",    "region": "US", "description": "SPDR Gold Shares ETF"},
]

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END   = datetime(2024, 12, 31, tzinfo=timezone.utc)


async def main() -> None:
    # Generate CSV vendor files first if not present
    from scripts.generate_csv_vendor import generate
    generate()

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[MONGO_DB]
    await ensure_indexes(db)

    yf_adapter  = YFinanceAdapter()
    csv_adapter = CsvVendorAdapter()

    # 1. Seed data_sources
    for adapter in (yf_adapter, csv_adapter):
        await upsert_source(db, adapter.source_record())
        print(f"[source] upserted: {adapter.source_id}")

    totals: dict[str, int] = {}

    for sym_info in SYMBOLS:
        symbol = sym_info["symbol"]
        print(f"\n── {symbol} ──")

        # 2. Insert asset version if not already present
        existing = await get_current_asset(db, symbol)
        if not existing:
            yf_attrs  = yf_adapter.fetch_asset_attributes(symbol)
            csv_attrs = csv_adapter.fetch_asset_attributes(symbol)
            await insert_asset_version(db, symbol, {
                "symbol": symbol,
                "asset_class": sym_info["asset_class"],
                "region": sym_info["region"],
                "description": sym_info["description"],
                "attributes": {
                    "yfinance": yf_attrs,
                    "csv-vendor": csv_attrs,
                },
            })
            print(f"  [asset] inserted new version")
        else:
            print(f"  [asset] already exists, skipping")

        # 3. Ingest timeseries from both vendors
        for adapter in (yf_adapter, csv_adapter):
            records = adapter.fetch_timeseries(symbol, START, END)
            if not records:
                print(f"  [{adapter.source_id}] no data returned")
                continue
            for r in records:
                r["asset_id"] = symbol
            inserted = await insert_timeseries(db, records)
            key = f"{symbol}/{adapter.source_id}"
            totals[key] = inserted
            print(f"  [{adapter.source_id}] inserted {inserted} rows")

    print("\n── Summary ──")
    for k, v in totals.items():
        print(f"  {k}: {v} timeseries rows")
    total_rows = sum(totals.values())
    print(f"  TOTAL: {total_rows} rows across {len(SYMBOLS)} assets × 2 sources")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
