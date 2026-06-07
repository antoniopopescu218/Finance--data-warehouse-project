"""
Smoke test: exercises the 5 required API queries and one analytics endpoint
against a running API (default http://localhost:8000). Exit non-zero on failure.

Usage:
    uv run python scripts/smoke.py [--base-url http://localhost:8000]
"""
import argparse
import sys
import httpx


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def check(condition: bool, msg: str) -> None:
    if not condition:
        fail(msg)


def run(base: str) -> None:
    client = httpx.Client(base_url=base, timeout=15)

    print("Q1  GET /assets ...")
    r = client.get("/assets")
    check(r.status_code == 200, f"/assets returned {r.status_code}")
    assets = r.json()
    check(isinstance(assets, list) and len(assets) > 0, "/assets returned empty list")
    first = assets[0]
    check("asset_id" in first, "/assets item missing asset_id")
    check("symbol" in first, "/assets item missing symbol")
    check("asset_class" in first, "/assets item missing asset_class")
    check("region" in first, "/assets item missing region")
    asset_id = "AAPL"
    print(f"    OK — {len(assets)} assets")

    print(f"Q2  GET /assets/{asset_id} ...")
    r = client.get(f"/assets/{asset_id}")
    check(r.status_code == 200, f"/assets/{asset_id} returned {r.status_code}")
    detail = r.json()
    check(detail.get("asset_id") == asset_id, "asset_id mismatch")
    check("valid_from" in detail, "missing valid_from in asset detail")
    check(detail.get("is_deleted") is False, "current asset has is_deleted=true")
    print(f"    OK — symbol={detail['symbol']}")

    print(f"Q2b GET /assets/{asset_id}?as_of=2024-06-01 (temporal) ...")
    r = client.get(f"/assets/{asset_id}", params={"as_of": "2024-06-01T00:00:00Z"})
    check(r.status_code == 200, f"as_of query returned {r.status_code}")
    check(r.json().get("asset_id") == asset_id, "as_of response has wrong asset_id")
    print("    OK")

    print("Q3  GET /sources ...")
    r = client.get("/sources")
    check(r.status_code == 200, f"/sources returned {r.status_code}")
    sources = r.json()
    check(isinstance(sources, list) and len(sources) > 0, "/sources returned empty list")
    check("source_id" in sources[0], "/sources item missing source_id")
    source_id = "yfinance"
    print(f"    OK — {len(sources)} sources")

    print(f"Q4  GET /sources/{source_id} ...")
    r = client.get(f"/sources/{source_id}")
    check(r.status_code == 200, f"/sources/{source_id} returned {r.status_code}")
    src = r.json()
    check(src.get("source_id") == source_id, "source_id mismatch")
    print(f"    OK — name={src.get('name')}")

    print(f"Q5  GET /assets/{asset_id}/timeseries?source_id={source_id}&from=2024-01-01&to=2024-12-31 ...")
    r = client.get(
        f"/assets/{asset_id}/timeseries",
        params={"source_id": source_id, "from": "2024-01-01", "to": "2024-12-31", "limit": 5000},
    )
    check(r.status_code == 200, f"/timeseries returned {r.status_code}")
    ts = r.json()
    count = ts.get("count", 0)
    check(count > 200, f"expected ~251 timeseries rows, got {count}")
    check(len(ts.get("records", [])) == count, "count vs records length mismatch")
    row = ts["records"][0]
    check("asset_id" in row, "timeseries row missing asset_id")
    check("source_id" in row, "timeseries row missing source_id")
    check("close" in row, "timeseries row missing close")
    print(f"    OK — {count} rows")

    print(f"AN  GET /assets/{asset_id}/analytics/summary ...")
    r = client.get(
        f"/assets/{asset_id}/analytics/summary",
        params={"source_id": source_id, "from": "2024-01-01", "to": "2024-12-31"},
    )
    check(r.status_code == 200, f"/analytics/summary returned {r.status_code}")
    summary = r.json()
    check(summary.get("count", 0) > 200, f"summary count too low: {summary.get('count')}")
    check(summary.get("min", 0) > 100, f"AAPL min close seems too low: {summary.get('min')}")
    check(summary.get("max", 0) > summary.get("min", 0), "max <= min")
    check(summary.get("avg", 0) > 0, "avg <= 0")
    print(f"    OK — count={summary['count']} min={summary['min']} max={summary['max']} avg={summary['avg']}")

    print("\nAll checks passed.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    try:
        run(args.base_url)
    except httpx.ConnectError:
        fail(f"Cannot connect to API at {args.base_url} — is the server running?")


if __name__ == "__main__":
    main()