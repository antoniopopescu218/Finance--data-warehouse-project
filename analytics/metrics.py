from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def daily_returns(closes: list[float]) -> list[float | None]:
    if len(closes) < 2:
        return [None] * len(closes)
    arr = np.array(closes, dtype=float)
    pct = np.diff(arr) / arr[:-1]
    return [None] + pct.tolist()


def rolling_mean(values: list[float], window: int) -> list[float | None]:
    n = len(values)
    if n == 0 or window < 1:
        return []
    arr = np.array(values, dtype=float)
    result: list[float | None] = [None] * min(window - 1, n)
    for i in range(window - 1, n):
        result.append(float(np.mean(arr[i - window + 1 : i + 1])))
    return result


def rolling_std(values: list[float], window: int) -> list[float | None]:
    n = len(values)
    if n == 0 or window < 2:
        return [None] * n
    arr = np.array(values, dtype=float)
    result: list[float | None] = [None] * min(window - 1, n)
    for i in range(window - 1, n):
        result.append(float(np.std(arr[i - window + 1 : i + 1], ddof=1)))
    return result


def correlation(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(a) != len(b):
        return None
    c = float(np.corrcoef(a, b)[0, 1])
    return None if np.isnan(c) else c


# ── Phase 3 analytics ─────────────────────────────────────────────────────────

def compute_summary(closes: list[float]) -> dict[str, Any]:
    """Return count, min, max, and mean of a close-price series."""
    if not closes:
        return {"count": 0, "min": None, "max": None, "avg": None}
    arr = np.array(closes, dtype=float)
    return {
        "count": int(len(arr)),
        "min": round(float(arr.min()), 4),
        "max": round(float(arr.max()), 4),
        "avg": round(float(arr.mean()), 4),
    }


def compute_trend(
    closes: list[float], dates: list[Any], window: int = 20
) -> dict[str, Any]:
    """Return period % change and a per-day list of close + moving average."""
    if not closes:
        return {"period_change_pct": None, "window": window, "data": []}
    first, last = float(closes[0]), float(closes[-1])
    period_change = round((last - first) / first * 100, 4) if first != 0 else None
    ma = pd.Series(closes, dtype=float).rolling(window=window, min_periods=1).mean()
    data = [
        {"date": d, "close": round(float(c), 4), "moving_avg": round(float(m), 4)}
        for d, c, m in zip(dates, closes, ma)
    ]
    return {"period_change_pct": period_change, "window": window, "data": data}


def compute_forecast(closes: list[float]) -> dict[str, Any]:
    """Return a naive last-close forecast and a linear-regression next-day prediction."""
    if not closes:
        return {"naive_forecast": None, "linear_regression_forecast": None}
    naive = round(float(closes[-1]), 4)
    x = np.arange(len(closes), dtype=float)
    y = np.array(closes, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    lr = round(float(slope * len(closes) + intercept), 4)
    return {
        "naive_forecast": naive,
        "linear_regression_forecast": lr,
        "labels": {
            "naive_forecast": "last observed close price",
            "linear_regression_forecast": "OLS fit over all closes, predicting next period",
        },
    }


def compute_risk(closes: list[float]) -> dict[str, Any]:
    """Return the most-recent 20-day rolling volatility and the maximum drawdown."""
    if len(closes) < 2:
        return {"rolling_20d_volatility": None, "max_drawdown": None}
    s = pd.Series(closes, dtype=float)
    rets = s.pct_change().dropna()
    vol_series = rets.rolling(window=20, min_periods=2).std()
    valid_vol = vol_series.dropna()
    last_vol = round(float(valid_vol.iloc[-1]), 6) if not valid_vol.empty else None
    peak = s.cummax()
    drawdown = (s - peak) / peak
    max_dd = round(float(drawdown.min()), 6)
    return {"rolling_20d_volatility": last_vol, "max_drawdown": max_dd}
