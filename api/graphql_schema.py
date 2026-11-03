"""GraphQL layer over the same read-only queries as the REST API."""
from typing import Optional

import strawberry
from strawberry.fastapi import GraphQLRouter

from api.queries import query

MAX_ROWS = 200


@strawberry.type
class Summary:
    events: int
    blocks: int
    anomalous_blocks: int
    anomaly_rate_pct: float


@strawberry.type
class VolumePoint:
    bucket: str
    events: int


@strawberry.type
class Count:
    name: str
    events: int


@strawberry.type
class Event:
    ts: str
    level: str
    component: str
    content: str


@strawberry.type
class Block:
    block_id: str
    label: Optional[str]

    @strawberry.field
    def events(self, limit: int = 50) -> list[Event]:
        rows = query(
            "SELECT ts, level, component, content FROM events WHERE block_id = %s ORDER BY ts, pid, content LIMIT %s",
            (self.block_id, max(1, min(limit, MAX_ROWS))),
        )
        return [Event(ts=r["ts"].isoformat(), level=r["level"], component=r["component"], content=r["content"]) for r in rows]


@strawberry.type
class Query:
    @strawberry.field
    def summary(self) -> Summary:
        events = query("SELECT count(*) AS n FROM events")[0]["n"]
        row = query("SELECT count(*) AS blocks, count(*) FILTER (WHERE label = 'Anomaly') AS bad FROM block_labels")[0]
        rate = round(100 * row["bad"] / row["blocks"], 2) if row["blocks"] else 0.0
        return Summary(events=events, blocks=row["blocks"], anomalous_blocks=row["bad"], anomaly_rate_pct=rate)

    @strawberry.field
    def volume(self, bucket: str = "hour") -> list[VolumePoint]:
        if bucket not in ("hour", "day"):
            raise ValueError("bucket must be 'hour' or 'day'")
        rows = query(
            f"SELECT to_char(date_trunc('{bucket}', ts), 'YYYY-MM-DD\"T\"HH24:MI:SS') AS bucket, count(*) AS events "
            "FROM events GROUP BY 1 ORDER BY 1"
        )
        return [VolumePoint(**r) for r in rows]

    @strawberry.field
    def components(self) -> list[Count]:
        return [Count(**r) for r in query("SELECT component AS name, count(*) AS events FROM events GROUP BY 1 ORDER BY 2 DESC")]

    @strawberry.field
    def levels(self) -> list[Count]:
        return [Count(**r) for r in query("SELECT level AS name, count(*) AS events FROM events GROUP BY 1 ORDER BY 2 DESC")]

    @strawberry.field
    def block(self, block_id: str) -> Optional[Block]:
        if not block_id.startswith("blk_"):
            raise ValueError("block_id must look like blk_-123...")
        rows = query("SELECT label FROM block_labels WHERE block_id = %s", (block_id,))
        return Block(block_id=block_id, label=rows[0]["label"] if rows else None)

    @strawberry.field
    def anomalous_blocks(self, limit: int = 20) -> list[Block]:
        rows = query(
            "SELECT block_id FROM block_labels WHERE label = 'Anomaly' ORDER BY block_id LIMIT %s",
            (max(1, min(limit, MAX_ROWS)),),
        )
        return [Block(block_id=r["block_id"], label="Anomaly") for r in rows]


schema = strawberry.Schema(Query)
router = GraphQLRouter(schema)
