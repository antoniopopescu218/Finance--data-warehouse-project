"""
CSV Vendor adapter — simulates a second data provider that delivers
daily OHLCV CSV dumps (no adj_close; different schema with quality_score
and provider_version fields, proving heterogeneity).
"""
import csv
from datetime import datetime
from pathlib import Path

from ingest.base import VendorAdapter

CSV_DIR = Path(__file__).parent.parent / "data" / "csv_vendor"


class CsvVendorAdapter(VendorAdapter):
    source_id = "csv-vendor"
    name = "CSV Vendor"
    description = (
        "File-based CSV data provider — OHLCV + quality_score + provider_version; "
        "no adj_close. Represents a daily-dump delivery from a second data provider."
    )
    api_endpoint = "file://data/csv_vendor/"

    def fetch_timeseries(self, symbol: str, start: datetime, end: datetime) -> list[dict]:
        path = CSV_DIR / f"{symbol.replace('^', '_')}.csv"
        if not path.exists():
            return []
        records = []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                ts = datetime.fromisoformat(row["date"])
                if not (start <= ts.replace(tzinfo=start.tzinfo) <= end):
                    continue
                records.append({
                    "source_id": self.source_id,
                    "data_timestamp": ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "adj_close": None,                    # not provided
                    "volume": int(row["volume"]),
                    "quality_score": float(row["quality_score"]),   # extra field
                    "provider_version": row["provider_version"],     # extra field
                })
        return records

    def fetch_asset_attributes(self, symbol: str) -> dict:
        return {
            "source_note": "csv-daily-dump",
            "provider_version": "2.1",
            "delivery_format": "csv",
        }
