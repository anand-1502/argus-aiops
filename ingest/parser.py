"""Parse raw HDFS log lines into structured events with Spark SQL functions."""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

LINE = r"^(\d{6}) (\d{6}) (\d+) (\w+) ([^:]+): (.*)$"
BLOCK = r"blk_-?\d+"

# applied in order: block ids, IPs (with optional leading slash and port), paths, bare numbers
_MASKS = [
    BLOCK,
    r"/?\d+\.\d+\.\d+\.\d+(:\d+)?",
    r"/\S+",
    r"\b\d+\b",
]


def parse_logs(raw: DataFrame) -> DataFrame:
    """raw has one string column `value`; returns one row per well-formed line."""
    line = F.col("value")
    df = raw.select(
        F.regexp_extract(line, LINE, 1).alias("d"),
        F.regexp_extract(line, LINE, 2).alias("t"),
        F.regexp_extract(line, LINE, 3).alias("pid"),
        F.regexp_extract(line, LINE, 4).alias("level"),
        F.regexp_extract(line, LINE, 5).alias("component"),
        F.regexp_extract(line, LINE, 6).alias("content"),
    ).where(F.col("pid") != "")

    template = F.col("content")
    for mask in _MASKS:
        template = F.regexp_replace(template, mask, "<*>")

    return df.select(
        F.to_timestamp(F.concat("d", "t"), "yyMMddHHmmss").alias("ts"),
        F.col("pid").cast("int").alias("pid"),
        "level",
        "component",
        F.regexp_extract("content", f"({BLOCK})", 1).alias("block_id"),
        "content",
        template.alias("template"),
    )
