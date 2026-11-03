"""Write a Tableau .hyper extract with the free Hyper API (no Tableau licence needed)."""
from pathlib import Path

import pandas as pd

KIND_TO_HYPER = {"integer": "BIG_INT", "float": "DOUBLE", "string": "TEXT", "boolean": "BOOL", "timestamp": "TIMESTAMP"}


def write_hyper(path: Path, tables: dict[str, pd.DataFrame], profiles: list[dict]) -> Path:
    from tableauhyperapi import Connection, CreateMode, HyperProcess, Inserter, SqlType, TableDefinition, TableName, Telemetry

    sql_type = {"integer": SqlType.big_int, "float": SqlType.double, "string": SqlType.text, "boolean": SqlType.bool, "timestamp": SqlType.timestamp}
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, str(path), CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema("Extract")
            for prof in profiles:
                name = prof["name"]
                df = tables[name]
                cols = [TableDefinition.Column(c["name"], sql_type[c["kind"]]()) for c in prof["columns"]]
                tdef = TableDefinition(TableName("Extract", name), cols)
                conn.catalog.create_table(tdef)
                with Inserter(conn, tdef) as ins:
                    ins.add_rows(_rows(df, prof))
                    ins.execute()
    return path


def _rows(df: pd.DataFrame, prof: dict):
    from tableauhyperapi import Timestamp

    kinds = [c["kind"] for c in prof["columns"]]
    for row in df.itertuples(index=False, name=None):
        out = []
        for v, k in zip(row, kinds):
            if pd.isna(v):
                out.append(None)
            elif k == "timestamp":
                t = pd.Timestamp(v)
                out.append(Timestamp(t.year, t.month, t.day, t.hour, t.minute, t.second, t.microsecond))
            elif k == "integer":
                out.append(int(v))
            elif k == "float":
                out.append(float(v))
            elif k == "boolean":
                out.append(bool(v))
            else:
                out.append(str(v))
        yield out
