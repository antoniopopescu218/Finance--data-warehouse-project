from __future__ import annotations

import numpy as np


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
