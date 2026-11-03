"""Shared read helper with a short TTL cache, used by both the REST and GraphQL layers."""
import time

from api.db import connect

_CACHE: dict[tuple, tuple[float, list[dict]]] = {}
_TTL_SECONDS = 300  # the dataset is static, so recomputing 11M-row aggregates per request is wasteful


def query(sql: str, params: tuple = ()) -> list[dict]:
    key = (sql, params)
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _TTL_SECONDS:
        return hit[1]
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    _CACHE[key] = (time.monotonic(), rows)
    return rows
