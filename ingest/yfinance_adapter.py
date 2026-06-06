from datetime import datetime

import yfinance as yf

from ingest.base import VendorAdapter


class YFinanceAdapter(VendorAdapter):
    source_id = "yfinance"
    name = "Yahoo Finance"
    description = "Yahoo Finance via yfinance — OHLCV, adj_close, corporate metadata"
    api_endpoint = "https://query1.finance.yahoo.com"

    def fetch_timeseries(self, symbol: str, start: datetime, end: datetime) -> list[dict]:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start.date(), end=end.date(), auto_adjust=False)
        if df.empty:
            return []
        records = []
        for ts, row in df.iterrows():
            records.append({
                "source_id": self.source_id,
                "data_timestamp": ts.to_pydatetime(),
                "open": float(row.get("Open", 0) or 0),
                "high": float(row.get("High", 0) or 0),
                "low": float(row.get("Low", 0) or 0),
                "close": float(row.get("Close", 0) or 0),
                "adj_close": float(row.get("Adj Close", 0) or 0),
                "volume": int(row.get("Volume", 0) or 0),
            })
        return records

    def fetch_asset_attributes(self, symbol: str) -> dict:
        info = yf.Ticker(symbol).info or {}
        return {
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": info.get("marketCap"),
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "long_name": info.get("longName"),
        }
