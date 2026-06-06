from datetime import datetime
from io import StringIO

import pandas as pd
import requests

from ingest.base import VendorAdapter

# yfinance symbol -> Stooq symbol mapping
STOOQ_SYMBOL_MAP = {
    "AAPL": "aapl.us",
    "MSFT": "msft.us",
    "TSLA": "tsla.us",
    "^GSPC": "^spx",
    "GLD": "gld.us",
}

STOOQ_CSV_URL = "https://stooq.com/q/d/l/?s={symbol}&d1={d1}&d2={d2}&i=d"


class StooqAdapter(VendorAdapter):
    source_id = "stooq"
    name = "Stooq"
    description = "Stooq CSV feed (direct HTTP) — OHLCV only, no adj_close"
    api_endpoint = "https://stooq.com/q/d/l/"

    def _stooq_symbol(self, symbol: str) -> str:
        return STOOQ_SYMBOL_MAP.get(symbol, symbol.lower())

    def fetch_timeseries(self, symbol: str, start: datetime, end: datetime) -> list[dict]:
        url = STOOQ_CSV_URL.format(
            symbol=self._stooq_symbol(symbol),
            d1=start.strftime("%Y%m%d"),
            d2=end.strftime("%Y%m%d"),
        )
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text), parse_dates=["Date"])
        except Exception:
            return []
        if df.empty or "Close" not in df.columns:
            return []
        df = df.sort_values("Date")
        records = []
        for _, row in df.iterrows():
            records.append({
                "source_id": self.source_id,
                "data_timestamp": row["Date"].to_pydatetime(),
                "open": float(row.get("Open", 0) or 0),
                "high": float(row.get("High", 0) or 0),
                "low": float(row.get("Low", 0) or 0),
                "close": float(row.get("Close", 0) or 0),
                "adj_close": None,
                "volume": int(row.get("Volume", 0) or 0),
            })
        return records

    def fetch_asset_attributes(self, symbol: str) -> dict:
        return {
            "source_note": "stooq-csv",
            "stooq_symbol": self._stooq_symbol(symbol),
        }
