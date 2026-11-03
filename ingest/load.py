"""Parse an HDFS log file with Spark and load events + block labels into Postgres."""
import argparse
import os
from pathlib import Path

import psycopg
from pyspark.sql import SparkSession

from ingest.parser import parse_logs

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "infra" / "sql"
PG = dict(host=os.environ.get("PGHOST", "localhost"), port=int(os.environ.get("PGPORT", "5433")),
          dbname=os.environ.get("PGDATABASE", "argus"), user="argus",
          password=os.environ.get("POSTGRES_PASSWORD", "argus"))
JDBC_URL = f"jdbc:postgresql://{PG['host']}:{PG['port']}/{PG['dbname']}"
JDBC_PKG = "org.postgresql:postgresql:42.7.4"


def make_spark(memory: str = "2g") -> SparkSession:
    return (
        SparkSession.builder.master("local[2]")
        .appName("argus-ingest")
        .config("spark.driver.memory", memory)
        .config("spark.jars.packages", JDBC_PKG)
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )


def load_events(spark: SparkSession, log_path: Path, limit: int | None) -> int:
    raw = spark.read.text(str(log_path))
    if limit:
        raw = raw.limit(limit)
    events = parse_logs(raw)
    (
        events.coalesce(2).write.format("jdbc")
        .option("url", JDBC_URL).option("dbtable", "events")
        .option("user", PG["user"]).option("password", PG["password"])
        .option("driver", "org.postgresql.Driver")
        .option("batchsize", 20000)
        .mode("append").save()
    )
    with psycopg.connect(**PG) as conn:
        return conn.execute("SELECT count(*) FROM events").fetchone()[0]


def load_labels(label_csv: Path) -> None:
    with psycopg.connect(**PG) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE block_labels")
        with cur.copy("COPY block_labels (block_id, label) FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
            with label_csv.open("rb") as f:
                while chunk := f.read(1 << 20):
                    cp.write(chunk)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=ROOT / "data/hdfs/HDFS.log")
    ap.add_argument("--labels", type=Path, default=ROOT / "data/hdfs/preprocessed/anomaly_label.csv")
    ap.add_argument("--limit", type=int, default=None, help="only load the first N lines")
    args = ap.parse_args()

    with psycopg.connect(**PG, autocommit=True) as conn:
        conn.execute((SQL / "schema.sql").read_text())
    spark = make_spark()
    n = load_events(spark, args.log, args.limit)
    spark.stop()
    load_labels(args.labels)
    with psycopg.connect(**PG, autocommit=True) as conn:
        conn.execute((SQL / "indexes.sql").read_text())
    print(f"loaded {n} events")


if __name__ == "__main__":
    main()
