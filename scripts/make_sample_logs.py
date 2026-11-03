"""Writes small, SYNTHETIC log files in formats newer than HDFS_v1, for trying the upload flow.

They are generated, not real: the point is to exercise the parser on ISO-8601 and syslog layouts, with one traffic
spike and a few rare errors planted so the summary has something to find. Fixed seed, so output is reproducible.
"""
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def app_log(path: Path, seed: int = 7) -> None:
    rnd = random.Random(seed)
    t = datetime(2026, 3, 2, 9, 0, 0, tzinfo=timezone.utc)
    lines = []
    for minute in range(120):
        n = 6 if minute != 70 else 90  # a spike at minute 70
        for _ in range(n):
            ts = (t + timedelta(minutes=minute, seconds=rnd.randint(0, 59))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            uid, ms = rnd.randint(1000, 9999), rnd.randint(5, 400)
            kind = rnd.random()
            if kind < 0.55:
                lines.append(f"{ts} INFO  [api] GET /v1/users/{uid} 200 {ms}ms")
            elif kind < 0.8:
                lines.append(f"{ts} INFO  [api] POST /v1/orders 201 {ms}ms order=ord_{rnd.randint(10**5, 10**6)}")
            elif kind < 0.93:
                lines.append(f"{ts} DEBUG [cache] hit ratio {rnd.randint(70, 99)}% for shard {rnd.randint(1, 8)}")
            else:
                lines.append(f"{ts} WARN  [db] slow query took {rnd.randint(800, 3000)}ms on replica 10.0.{rnd.randint(0, 3)}.{rnd.randint(2, 50)}")
        if minute == 70:
            ts = (t + timedelta(minutes=70, seconds=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            lines.append(  # one entry, so the stack frames stay attached to their error when sorted
                f"{ts} ERROR [payments] upstream timeout calling gateway.example.net after 30000ms\n"
                "java.net.SocketTimeoutException: Read timed out\n"
                "    at java.base/sun.nio.ch.NioSocketImpl.timedRead(NioSocketImpl.java:288)"
            )
    lines.sort(key=lambda l: l[:24])
    path.write_text("\n".join(lines) + "\n")


def syslog(path: Path, seed: int = 11) -> None:
    rnd = random.Random(seed)
    t = datetime(2026, 3, 2, 0, 0, 0)
    lines = []
    for i in range(400):
        ts = (t + timedelta(seconds=i * 20)).strftime("%b %e %H:%M:%S")
        if rnd.random() < 0.9:
            lines.append(f"{ts} web-01 sshd[{rnd.randint(1000, 9999)}]: Accepted publickey for deploy from 10.1.{rnd.randint(0, 9)}.{rnd.randint(1, 99)} port {rnd.randint(30000, 60000)}")
        else:
            lines.append(f"{ts} web-01 sshd[{rnd.randint(1000, 9999)}]: Failed password for invalid user admin from 203.0.113.{rnd.randint(1, 99)} port {rnd.randint(30000, 60000)}")
    lines.append(f"{(t + timedelta(hours=2)).strftime('%b %e %H:%M:%S')} web-01 kernel: Out of memory: Killed process 4242 (java)")
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    app_log(OUT / "modern_app.log")
    syslog(OUT / "syslog_sample.log")
    print("wrote", OUT / "modern_app.log", OUT / "syslog_sample.log")
