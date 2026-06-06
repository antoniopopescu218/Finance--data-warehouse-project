"""
Generates CSV vendor data files in data/csv_vendor/ from yfinance data,
applying a small price perturbation (+/-0.5%) to simulate a different feed.
Run once before seed.py (seed.py calls this automatically).
"""
import csv
import random
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

SYMBOLS = ["AAPL", "MSFT", "TSLA", "^GSPC", "GLD"]
OUT_DIR = Path(__file__).parent.parent / "data" / "csv_vendor"
START = "2024-01-01"
END = "2024-12-31"
PROVIDER_VERSION = "2.1"
SEED = 42


def generate() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    for symbol in SYMBOLS:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=START, end=END, auto_adjust=False)
        if df.empty:
            print(f"  [csv-vendor] no data for {symbol}, skipping")
            continue

        filename = OUT_DIR / f"{symbol.replace('^', '_')}.csv"
        rows_written = 0
        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["date", "open", "high", "low", "close",
                            "volume", "quality_score", "provider_version"],
            )
            writer.writeheader()
            for ts, row in df.iterrows():
                factor = 1 + rng.uniform(-0.005, 0.005)
                writer.writerow({
                    "date": ts.to_pydatetime().replace(tzinfo=timezone.utc).isoformat(),
                    "open": round(float(row["Open"]) * factor, 4),
                    "high": round(float(row["High"]) * factor, 4),
                    "low": round(float(row["Low"]) * factor, 4),
                    "close": round(float(row["Close"]) * factor, 4),
                    "volume": int(row["Volume"]),
                    "quality_score": round(rng.uniform(0.95, 1.0), 4),
                    "provider_version": PROVIDER_VERSION,
                })
                rows_written += 1
        print(f"  [csv-vendor] wrote {rows_written} rows → {filename.name}")


if __name__ == "__main__":
    generate()
