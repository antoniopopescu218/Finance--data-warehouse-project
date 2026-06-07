# Financial Markets Data Warehouse

A temporal, NoSQL data warehouse for financial market data with vendor ingestion, provenance tracking, a REST API, analytics, and an MCP-exposed assistant.

---

## Prerequisites

- Docker & Docker Compose (v2)
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

---

## Quick Start

### 1. Start the stack

```bash
docker compose up -d
```

This starts MongoDB 7 on port `27017` and the FastAPI server on port `8000`.

### 2. Seed the database

```bash
uv run python scripts/seed.py
```

Seeds ~2510 timeseries rows for 5 symbols (AAPL, MSFT, TSLA, ^GSPC, GLD) from two vendors.

### 3. Verify

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok","db":"dwh"}`

---

## API Reference

Interactive docs at `http://localhost:8000/docs`.

### Q1 — List assets

```bash
curl http://localhost:8000/assets
```

Returns a list of `{asset_id, symbol, asset_class, region}` for all current non-deleted assets.

### Q2 — Get asset (with optional temporal lookup)

```bash
# Current version
curl http://localhost:8000/assets/AAPL

# Point-in-time version
curl "http://localhost:8000/assets/AAPL?as_of=2024-06-01T00:00:00Z"
```

Returns full asset details. `as_of` returns the version active at that timestamp.

### Q3 — List sources

```bash
curl http://localhost:8000/sources
```

Returns all data sources with `source_id` and `name`.

### Q4 — Get source

```bash
curl http://localhost:8000/sources/yfinance
```

Returns full source record; `404` if not found.

### Q5 — Get timeseries

```bash
curl "http://localhost:8000/assets/AAPL/timeseries?source_id=yfinance&from=2024-01-01&to=2024-03-31"
```

Returns OHLCV rows for the asset, filtered by source and date range.

---

## Analytics Endpoints

### Summary statistics

```bash
curl "http://localhost:8000/assets/AAPL/analytics/summary?source_id=yfinance&from=2024-01-01&to=2024-12-31"
```

Returns `count`, `min`, `max`, `avg` of close prices over the window.

### Price trend with moving average

```bash
curl "http://localhost:8000/assets/AAPL/analytics/trend?source_id=yfinance&from=2024-01-01&to=2024-12-31&window=20"
```

Returns period `% change` and a per-day list of `{date, close, moving_avg}`.

### Next-day forecast

```bash
curl "http://localhost:8000/assets/AAPL/analytics/forecast?source_id=yfinance"
```

Returns two labeled predictions: naive (last-close repeat) and linear-regression extrapolation.

### Risk metrics

```bash
curl "http://localhost:8000/assets/AAPL/analytics/risk?source_id=yfinance&from=2024-01-01&to=2024-12-31"
```

Returns rolling 20-day volatility and maximum drawdown (negative fraction).

### Export for ML / Spark

```bash
# JSON
curl "http://localhost:8000/assets/AAPL/timeseries/export?source_id=yfinance&format=json"

# CSV download
curl -O "http://localhost:8000/assets/AAPL/timeseries/export?source_id=yfinance&format=csv"
```

---

## MCP Server

The entire API is exposed as MCP tools via [FastMCP](https://github.com/jlowin/fastmcp), making it compatible with any MCP-capable client or agent framework.

### Test with MCP Inspector

```bash
uv run fastmcp dev mcp_server.py
```

Open the Inspector URL printed to the console and confirm all tools appear.

### Connect an MCP client

Add the server to your MCP client configuration. The command to run the server is:

```bash
uv run --project /path/to/this/repo python /path/to/this/repo/mcp_server.py
```

Replace `/path/to/this/repo` with the absolute path to the project directory. Once connected, you can invoke tools such as `list_assets`, `get_timeseries`, or `get_risk` directly from the client.

---

## Running Locally (without Docker)

Start MongoDB separately, then:

```bash
MONGO_URL=mongodb://localhost:27017 uv run uvicorn api.main:app --reload
```

---

## Tests

```bash
# Smoke tests (requires running API on localhost:8000)
uv run python scripts/smoke.py

# Temporal correctness test (requires running MongoDB)
uv run pytest tests/test_temporal.py -v
```

---

## LangFlow Integration

A pre-built LangFlow flow is included at [`flows/acme_financial.json`](flows/acme_financial.json). It lets you query the warehouse API visually, without writing code.

### Canvas layout

The flow has three independent sub-flows on a single canvas:

| Sub-flow | Endpoint called | What it returns |
|---|---|---|
| **1. List All Assets** | `GET /assets` | All current non-deleted assets |
| **2. Get Timeseries** | `GET /assets/{id}/timeseries` | OHLCV rows for a date range |
| **3. Get Analytics Summary** | `GET /assets/{id}/analytics/summary` | count, min, max, avg of close |

### Prerequisites

Start the warehouse API first (it must be reachable on `http://localhost:8000`):

```bash
docker compose up -d
uv run uvicorn api.main:app --reload
```

### Install LangFlow (once)

```bash
pip install langflow
```

Or with Docker:

```bash
docker run -p 7860:7860 langflowai/langflow:latest
```

### Import the flow

1. Open LangFlow at `http://localhost:7860`.
2. Click **My Flows → Import** (or drag-and-drop).
3. Select `flows/acme_financial.json`.
4. The canvas loads with all three sub-flows pre-wired.

### Run a sub-flow

**Sub-flow 1 — List all assets** (no inputs required):
- Click **Run** on the `1. List All Assets` node.
- The response appears in the `Assets Output` chat panel.

**Sub-flow 2 — Get timeseries** (edit the four Text Input nodes):
| Field | Default | Notes |
|---|---|---|
| Asset ID | `AAPL` | Any of: AAPL, MSFT, TSLA, ^GSPC, GLD |
| Source ID | `yfinance` | `yfinance` or `csv-vendor` |
| From Date | `2024-01-01` | ISO 8601 date |
| To Date | `2024-12-31` | ISO 8601 date |

Click **Run** → timeseries JSON appears in `Timeseries Output`.

**Sub-flow 3 — Analytics summary**: same four inputs, same pattern → returns `{count, min, max, avg}` of close prices over the window.

### Customising the URL

Each Prompt node contains the full URL template. To call a different endpoint (e.g. `/analytics/trend` or `/analytics/risk`), open the Prompt node, edit the template string in place, and re-run.

---

## Security Notice

This project is a development/demo build and is **not hardened for production use**. Notable gaps include: no API authentication, no MongoDB access control, no rate limiting, and no TLS between services. See [`security_readme.md`](security_readme.md) for a full audit with a production hardening checklist.
