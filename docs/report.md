# Project Report: Financial Markets Data Warehouse

## 1. What Was Built

A fully functional, end-to-end temporal data warehouse for financial market data, implemented with Python 3.11, FastAPI, MongoDB 7, and Docker Compose. The system covers the complete pipeline from raw vendor data through storage, querying, analytics, and an LLM-accessible interface.

**Components:**

| Layer | Module | Description |
|---|---|---|
| Ingestion | `ingest/` | Vendor adapters (yfinance, csv-vendor) with provenance |
| Storage | `storage/repository.py` | Motor async repository; append-only temporal model |
| API | `api/` | FastAPI REST; 5 core queries + analytics endpoints |
| Analytics | `analytics/metrics.py` | pandas/numpy — summary, trend, forecast, risk, export |
| MCP | `mcp_server.py` | FastMCP wraps the entire API as LLM-callable tools |

**Data seeded:** 5 symbols (AAPL, MSFT, TSLA, ^GSPC, GLD), two vendors, ~2510 timeseries rows.

---

## 2. Design Choices

### 2.1 Temporal Model (Append-Only Versioning)

Every asset record carries `valid_from`, `valid_to`, and `is_deleted` fields. The invariant is:

- **No document is ever updated or deleted in place.**
- An "update" inserts a new version and closes the previous one by setting `valid_to = now`.
- A "delete" inserts a sentinel document with `is_deleted = True`.
- A point-in-time query (`as_of(t)`) retrieves the version where `valid_from ≤ t AND (valid_to IS NULL OR valid_to > t)`.

This model provides a complete audit trail at no extra cost — historical state is always recoverable. MongoDB's flexible document model makes it straightforward to append new versions without schema migrations.

### 2.2 Heterogeneous Provider Fields

Provider-specific fields (e.g., `adj_close` from yfinance; `quality_score` and `provider_version` from the csv-vendor) are stored in an `attributes` sub-document rather than forcing a fixed schema across all vendors. Core OHLCV fields are top-level for consistent querying; anything vendor-specific is nested under `attributes`. This keeps queries uniform while preserving all provenance data.

### 2.3 Provenance

Every timeseries record carries a `source_id` that references the `data_sources` collection. Every analytics and query endpoint accepts `source_id` as an optional filter, so results are always traceable to their origin. The API never mixes vendors silently — the caller controls which source they query.

---

## 3. Vendor Swap: Stooq → CSV Vendor

The original plan used Stooq as Vendor B. During implementation, Stooq began returning a JavaScript challenge page rather than downloadable CSV data, which cannot be handled by a simple HTTP client. Rather than introduce a headless browser dependency or a fragile scraper, a file-based CSV vendor was substituted.

The CSV vendor reads pre-downloaded files from `data/csv_vendor/` and intentionally exposes different fields than yfinance:

- **yfinance fields:** `open`, `high`, `low`, `close`, `adj_close`, `volume`
- **csv-vendor fields:** `open`, `high`, `low`, `close`, `volume`, `quality_score`, `provider_version` (no `adj_close`)

This difference is preserved in the `attributes` sub-document and actually strengthens the heterogeneity demonstration — the storage layer and API handle both schemas without modification.

---

## 4. Architecture

```
data/csv_vendor/*.csv ──┐
                        ├──> ingest/ (adapters)
yfinance (live API) ────┘         │
                                  ▼
                        storage/repository.py  (Motor + MongoDB)
                                  │
                                  ▼
                        api/main.py  (FastAPI + Uvicorn)
                        ├── /assets          (temporal CRUD)
                        ├── /sources         (provenance lookup)
                        └── /assets/{id}/analytics/*  (pandas metrics)
                                  │
                                  ▼
                        mcp_server.py  (FastMCP.from_fastapi)
                                  │
                                  ▼
                        Claude Desktop / MCP Inspector
```

**Key technology choices:**

- **MongoDB 7** — flexible schema for heterogeneous fields; native support for the temporal query pattern via compound indexes on `(asset_id, valid_from)` and `(asset_id, source_id, data_timestamp)`.
- **Motor** — async MongoDB driver; keeps FastAPI fully non-blocking.
- **FastMCP** — converts the entire FastAPI app to MCP tools using the `operation_id` field of each route as the tool name. No separate MCP schema is maintained.
- **pandas/numpy** — analytics computed in-process on query results; no separate analytics service needed for this scale.

---

## 5. How to Reproduce

### Prerequisites

- Docker & Docker Compose v2
- Python 3.11+
- `uv` (`pip install uv`)

### Steps

```bash
# 1. Clone / unzip the project
cd 24project

# 2. Start MongoDB + API container
docker compose up -d

# 3. Seed data (both vendors, all 5 symbols)
~/.local/bin/uv run python scripts/seed.py

# 4. Verify the API
curl http://localhost:8000/health
curl http://localhost:8000/assets
curl "http://localhost:8000/assets/AAPL/timeseries?source_id=yfinance&from=2024-01-01&to=2024-03-31"

# 5. Run analytics
curl "http://localhost:8000/assets/AAPL/analytics/summary?source_id=yfinance&from=2024-01-01&to=2024-12-31"

# 6. Run smoke tests
~/.local/bin/uv run python scripts/smoke.py

# 7. Run temporal correctness test
~/.local/bin/uv run pytest tests/test_temporal.py -v

# 8. Start MCP Inspector
~/.local/bin/uv run fastmcp dev mcp_server.py
```

The API interactive documentation is available at `http://localhost:8000/docs`.

---

## 6. Temporal Correctness Test Summary

The test in `tests/test_temporal.py` performs the following:

1. Inserts an initial asset version (v1) with `symbol = "TEST"`.
2. Inserts a new version (v2) with `symbol = "TEST-UPDATED"`, which closes v1 by setting `valid_to`.
3. Marks the asset deleted (v3 sentinel with `is_deleted = True`).
4. Asserts that `get_asset_as_of(t1)` — a timestamp between v1 insertion and v2 insertion — returns v1.
5. Asserts that `get_asset_as_of(t2)` — a timestamp between v2 insertion and deletion — returns v2.
6. Asserts that `get_asset_as_of(t3)` — a timestamp after deletion — returns `None`.

All three assertions pass, confirming the temporal query predicate is correct.
