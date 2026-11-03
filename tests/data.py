"""Shared skip condition: tests that assert on the full HDFS load only run where it exists (not in CI)."""
import socket

import pytest


def full_data_present() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        if s.connect_ex(("localhost", 5433)) != 0:
            return False
    try:
        from api.db import connect

        with connect() as c:
            return c.execute("SELECT count(*) AS n FROM events").fetchone()["n"] > 1_000_000
    except Exception:
        return False


needs_full_data = pytest.mark.skipif(not full_data_present(), reason="needs the full 11M-event HDFS load")
