"""Bring your own logs: parse any plain-text log file with Drain3 and load it into an isolated Postgres schema.

Each upload gets its own schema (`upload_<id>`), so one customer's data can never show up in another's queries, and
dropping the schema removes everything. Unlike the HDFS pipeline there are no labels and no Spark: the parser guesses the
timestamp format, pulls out a severity level and mines templates online.
"""
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

MAX_BYTES = 50 * 1024 * 1024
MAX_LINES = 500_000
BATCH = 5_000
SAMPLE_LINES = 200

# (name, regex, parser). Each regex must capture the whole timestamp in group 1.
_ISO = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)")
_SYSLOG = re.compile(r"([A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2})")
_COMPACT = re.compile(r"(\d{6} \d{6})")
_EPOCH = re.compile(r"(\d{10}(?:\.\d+)?)\s")
_MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
_LEVEL = re.compile(r"\b(TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|FATAL|CRITICAL|SEVERE)\b", re.I)
_LEVEL_NAMES = {"WARNING": "WARN", "ERR": "ERROR", "SEVERE": "ERROR", "CRITICAL": "FATAL"}


def _iso(s: str) -> datetime:
    s = s.replace(",", ".").replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _syslog(s: str, year: int) -> datetime:
    mon, day, hms = s.split(None, 2)
    h, m, sec = map(int, hms.split(":"))
    return datetime(year, _MONTHS[mon], int(day), h, m, sec, tzinfo=timezone.utc)


def _compact(s: str) -> datetime:
    return datetime.strptime(s, "%y%m%d %H%M%S").replace(tzinfo=timezone.utc)


def _epoch(s: str) -> datetime:
    return datetime.fromtimestamp(float(s), tz=timezone.utc)


FORMATS = {
    "iso8601": (_ISO, _iso),
    "syslog": (_SYSLOG, None),  # needs the year, bound per call
    "compact": (_COMPACT, _compact),
    "epoch": (_EPOCH, _epoch),
}


def detect_format(lines: list[str]) -> str | None:
    """Pick the timestamp format that parses the most of the sample, or None if under half do."""
    best, best_n = None, 0
    for name, (rx, fn) in FORMATS.items():
        n = 0
        for line in lines:
            m = rx.search(line[:80])
            if not m:
                continue
            try:
                fn(m.group(1)) if fn else _syslog(m.group(1), 2000)
                n += 1
            except ValueError:
                pass
        if n > best_n:
            best, best_n = name, n
    return best if best_n * 2 >= max(len(lines), 1) else None


def make_parser(fmt: str | None, year: int | None = None) -> Callable[[str], tuple[datetime | None, str]]:
    """Returns line -> (timestamp or None, line with the timestamp stripped)."""
    if fmt is None:
        return lambda line: (None, line)
    rx, fn = FORMATS[fmt]
    if fmt == "syslog":
        y = year or datetime.now(timezone.utc).year
        fn = lambda s: _syslog(s, y)  # noqa: E731

    def parse(line: str) -> tuple[datetime | None, str]:
        m = rx.search(line[:80])
        if not m:
            return None, line
        try:
            return fn(m.group(1)), (line[: m.start()] + line[m.end():]).strip(" []:-")
        except ValueError:
            return None, line

    return parse


def make_miner() -> TemplateMiner:
    cfg = TemplateMinerConfig()
    cfg.drain_sim_th = 0.5
    cfg.drain_depth = 4
    cfg.drain_max_clusters = 2000
    cfg.parametrize_numeric_tokens = True
    cfg.masking_instructions = [
        MaskingInstruction(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "UUID"),
        MaskingInstruction(r"\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b", "IP"),
        MaskingInstruction(r"\b0x[0-9a-fA-F]+\b", "HEX"),
        MaskingInstruction(r"(?<![\w])/[\w./-]+", "PATH"),
        MaskingInstruction(r"\b\d+\b", "NUM"),
    ]
    return TemplateMiner(config=cfg)


def read_lines(path: Path):
    """Yields non-empty lines. Raises ValueError for binary files and for files over the line cap."""
    n = 0
    with open(path, "rb") as f:
        if b"\x00" in f.read(4096):
            raise ValueError("this looks like a binary file, not a text log")
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            n += 1
            if n > MAX_LINES:
                raise ValueError(f"file has more than {MAX_LINES:,} lines; split it and upload a part")
            yield line


# ---- storage ------------------------------------------------------------------

REGISTRY = """
CREATE TABLE IF NOT EXISTS uploads (
    id           text PRIMARY KEY,
    filename     text NOT NULL,
    status       text NOT NULL,
    stage        text,
    bytes        bigint,
    lines_total  integer,
    lines_done   integer DEFAULT 0,
    templates    integer,
    ts_format    text,
    error        text,
    created_at   timestamptz DEFAULT now(),
    finished_at  timestamptz
)"""


def schema_of(upload_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{12}", upload_id):
        raise ValueError("bad upload id")
    return f"upload_{upload_id}"


def create(conn, filename: str, size: int) -> str:
    upload_id = uuid.uuid4().hex[:12]
    conn.execute(REGISTRY)
    conn.execute(
        "INSERT INTO uploads (id, filename, status, stage, bytes) VALUES (%s, %s, 'queued', 'queued', %s)",
        (upload_id, filename[:200], size),
    )
    conn.commit()
    return upload_id


def _set(conn, upload_id: str, **fields) -> None:
    cols = ", ".join(f"{k} = %s" for k in fields)
    conn.execute(f"UPDATE uploads SET {cols} WHERE id = %s", (*fields.values(), upload_id))
    conn.commit()


def ingest(conn, upload_id: str, path: Path) -> dict:
    """Parse and load one file. Updates the registry row as it goes; never raises (failures land in `error`)."""
    schema = schema_of(upload_id)
    try:
        _set(conn, upload_id, status="running", stage="reading")
        size = path.stat().st_size
        if size > MAX_BYTES:
            raise ValueError(f"file is {size / 1e6:.0f} MB; the limit is {MAX_BYTES // 2**20} MB")
        lines = list(read_lines(path))
        if not lines:
            raise ValueError("the file has no non-empty lines")
        fmt = detect_format(lines[:SAMPLE_LINES])
        parse = make_parser(fmt)
        _set(conn, upload_id, lines_total=len(lines), ts_format=fmt or "none", stage="parsing")

        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
        conn.execute(
            f'CREATE TABLE "{schema}".events (line_no integer, ts timestamptz, level text, content text, template_id integer)'
        )
        conn.execute(f'CREATE TABLE "{schema}".templates (template_id integer PRIMARY KEY, template text, n integer)')
        conn.commit()

        miner, counts = make_miner(), Counter()
        batch: list[tuple] = []
        last_ts = None
        for i, line in enumerate(lines, 1):
            ts, rest = parse(line)
            if ts is None:
                ts = last_ts  # continuation lines (stack traces) inherit the previous timestamp
            else:
                last_ts = ts
            lm = _LEVEL.search(rest)
            level = (lm.group(1).upper() if lm else "UNKNOWN")
            level = _LEVEL_NAMES.get(level, level)
            cid = miner.add_log_message(rest)["cluster_id"]
            counts[cid] += 1
            batch.append((i, ts, level, rest[:2000], cid))
            if len(batch) >= BATCH or i == len(lines):
                _copy(conn, schema, batch)
                batch = []
                _set(conn, upload_id, lines_done=i)

        _set(conn, upload_id, stage="templates")
        with conn.cursor() as cur:
            cur.executemany(
                f'INSERT INTO "{schema}".templates VALUES (%s, %s, %s)',
                [(c.cluster_id, c.get_template(), counts[c.cluster_id]) for c in miner.drain.clusters],
            )
        conn.execute(f'CREATE INDEX ON "{schema}".events (ts)')
        conn.execute(f'CREATE INDEX ON "{schema}".events (template_id)')
        conn.commit()
        _set(
            conn, upload_id, status="succeeded", stage="done", templates=len(miner.drain.clusters),
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as e:  # noqa: BLE001 - surfaced to the user, not swallowed
        conn.rollback()
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.commit()
        _set(conn, upload_id, status="failed", stage="failed", error=f"{type(e).__name__}: {e}"[:500],
             finished_at=datetime.now(timezone.utc))
    return get(conn, upload_id)


def _copy(conn, schema: str, rows: list[tuple]) -> None:
    with conn.cursor() as cur, cur.copy(
        f'COPY "{schema}".events (line_no, ts, level, content, template_id) FROM STDIN'
    ) as cp:
        for r in rows:
            cp.write_row(r)
    conn.commit()


def get(conn, upload_id: str) -> dict | None:
    conn.execute(REGISTRY)
    return conn.execute("SELECT * FROM uploads WHERE id = %s", (upload_id,)).fetchone()


def listing(conn) -> list[dict]:
    conn.execute(REGISTRY)
    return conn.execute("SELECT * FROM uploads ORDER BY created_at DESC LIMIT 50").fetchall()


def delete(conn, upload_id: str) -> bool:
    schema = schema_of(upload_id)
    conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    n = conn.execute("DELETE FROM uploads WHERE id = %s", (upload_id,)).rowcount
    conn.commit()
    return bool(n)


# ---- analysis -----------------------------------------------------------------

def summary(conn, upload_id: str) -> dict:
    """What a first look at an unknown log file should show: size, levels, volume, templates, rare ones, spikes."""
    s = schema_of(upload_id)
    ev, tp = f'"{s}".events', f'"{s}".templates'
    total = conn.execute(f"SELECT count(*) AS n, min(ts) AS first, max(ts) AS last FROM {ev}").fetchone()
    levels = conn.execute(f"SELECT level AS name, count(*) AS n FROM {ev} GROUP BY 1 ORDER BY 2 DESC").fetchall()
    span = (total["last"] - total["first"]) if total["first"] else timedelta(0)
    unit = "minute" if span <= timedelta(hours=6) else "hour" if span <= timedelta(days=4) else "day"
    volume = conn.execute(
        f"SELECT date_trunc('{unit}', ts) AS bucket, count(*) AS events FROM {ev} WHERE ts IS NOT NULL GROUP BY 1 ORDER BY 1"
    ).fetchall()
    top = conn.execute(f"SELECT template_id, template, n FROM {tp} ORDER BY n DESC LIMIT 10").fetchall()
    # a template seen in under 1% of lines (and at most 5 times) is worth a human look
    rare = conn.execute(
        f"""SELECT t.template_id, t.template, t.n,
                   (SELECT content FROM {ev} e WHERE e.template_id = t.template_id ORDER BY line_no LIMIT 1) AS example
            FROM {tp} t WHERE t.n <= 5 AND t.n::float / %s < 0.01 ORDER BY t.n, t.template_id LIMIT 10""",
        (total["n"],),
    ).fetchall()
    return {
        "events": total["n"],
        "first_ts": total["first"],
        "last_ts": total["last"],
        "bucket": unit,
        "levels": levels,
        "volume": volume,
        "spikes": spikes(volume),
        "top_templates": top,
        "rare_templates": rare,
        "error_share_pct": round(100 * sum(l["n"] for l in levels if l["name"] in ("ERROR", "FATAL")) / max(total["n"], 1), 2),
    }


def spikes(volume: list[dict], z: float = 3.0) -> list[dict]:
    """Buckets whose volume is more than z standard deviations above the mean. Needs at least 8 buckets."""
    ns = [v["events"] for v in volume]
    if len(ns) < 8:
        return []
    mean = sum(ns) / len(ns)
    sd = (sum((n - mean) ** 2 for n in ns) / len(ns)) ** 0.5
    if sd == 0:
        return []
    return [{"bucket": v["bucket"], "events": v["events"], "z": round((v["events"] - mean) / sd, 1)}
            for v in volume if (v["events"] - mean) / sd > z]


def search(conn, upload_id: str, q: str, limit: int = 50) -> list[dict]:
    s = schema_of(upload_id)
    limit = max(1, min(limit, 200))
    return conn.execute(
        f'SELECT line_no, ts, level, content FROM "{s}".events WHERE content ILIKE %s ORDER BY line_no LIMIT %s',
        (f"%{q}%", limit),
    ).fetchall()
