import os

import psycopg
from psycopg.rows import dict_row


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5433")),
        dbname=os.environ.get("PGDATABASE", "argus"),
        user=os.environ.get("PGUSER", "argus"),
        password=os.environ.get("POSTGRES_PASSWORD", "argus"),
        row_factory=dict_row,
    )
