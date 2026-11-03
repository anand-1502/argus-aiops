"""Phase 1: raw HDFS lines become structured events."""
from pathlib import Path

from ingest.parser import parse_logs

FIXTURE = Path(__file__).parent / "fixtures" / "hdfs_sample.log"


def rows(spark):
    return parse_logs(spark.read.text(str(FIXTURE))).orderBy("ts", "pid", "content").collect()


def test_every_line_is_parsed(spark):
    assert len(rows(spark)) == 4


def test_timestamp_is_the_literal_log_time(spark):
    from pyspark.sql import functions as F

    df = parse_logs(spark.read.text(str(FIXTURE))).where("pid = 35")
    got = df.select(F.date_format("ts", "yyyy-MM-dd HH:mm:ss")).first()[0]
    assert got == "2008-11-09 20:35:18"


def test_fields_of_first_line(spark):
    r = [x for x in rows(spark) if x.pid == 143][0]
    assert r.level == "INFO"
    assert r.component == "dfs.DataNode$DataXceiver"
    assert r.block_id == "blk_-1608999687919862906"


def test_template_masks_variable_parts(spark):
    r = [x for x in rows(spark) if x.pid == 143][0]
    assert r.template == "Receiving block <*> src: <*> dest: <*>"


def test_path_and_block_masked_in_namesystem_line(spark):
    r = [x for x in rows(spark) if x.component == "dfs.FSNamesystem"][0]
    assert r.template == "BLOCK* NameSystem.allocateBlock: <*> <*>"


def test_warn_level_and_number_masking(spark):
    r = [x for x in rows(spark) if x.level == "WARN"][0]
    assert r.block_id == "blk_7503483334202473044"
    assert r.template == "PacketResponder <*> for block <*> Interrupted."
