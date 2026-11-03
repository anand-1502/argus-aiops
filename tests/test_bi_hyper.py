"""Phase 5 (BI export): the .hyper extract opens with Tableau's own library and holds exactly the data we wrote."""
import pandas as pd
import pytest

from bi.hyper import write_hyper
from bi.profile import profile_table

pytest.importorskip("tableauhyperapi")
from tableauhyperapi import Connection, HyperProcess, Telemetry  # noqa: E402

TABLES = {
    "hourly_volume": pd.DataFrame({"hour": pd.date_range("2008-11-10 03:00", periods=5, freq="h"), "events": [10, 20, 30, 40, 50], "anomalous_events": [1, 2, 3, 4, 5]}),
    "agent_incidents": pd.DataFrame({"block_id": ["blk_1", "blk_2"], "verified": [True, False], "seconds": [12.5, None]}),
}


@pytest.fixture
def hyper_file(tmp_path):
    profiles = [profile_table(n, d) for n, d in TABLES.items()]
    return write_hyper(tmp_path / "t.hyper", TABLES, profiles)


def query(path, sql):
    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as h:
        with Connection(h.endpoint, str(path)) as c:
            return c.execute_list_query(sql)


def test_extract_opens_and_has_both_tables_with_all_rows(hyper_file):
    assert query(hyper_file, 'SELECT count(*) FROM "Extract"."hourly_volume"') == [[5]]
    assert query(hyper_file, 'SELECT count(*) FROM "Extract"."agent_incidents"') == [[2]]


def test_values_and_types_survive(hyper_file):
    assert query(hyper_file, 'SELECT sum("events"), sum("anomalous_events") FROM "Extract"."hourly_volume"') == [[150, 15]]
    row = query(hyper_file, 'SELECT "block_id", "verified", "seconds" FROM "Extract"."agent_incidents" ORDER BY 1')
    assert row == [["blk_1", True, 12.5], ["blk_2", False, None]]  # a missing number stays NULL


def test_timestamps_keep_their_value(hyper_file):
    first = query(hyper_file, 'SELECT min("hour") FROM "Extract"."hourly_volume"')[0][0]
    assert (first.year, first.month, first.day, first.hour) == (2008, 11, 10, 3)


def test_rewriting_replaces_the_file(tmp_path):
    prof = [profile_table("hourly_volume", TABLES["hourly_volume"])]
    p = tmp_path / "x.hyper"
    write_hyper(p, {"hourly_volume": TABLES["hourly_volume"]}, prof)
    write_hyper(p, {"hourly_volume": TABLES["hourly_volume"].head(2)}, [profile_table("hourly_volume", TABLES["hourly_volume"].head(2))])
    assert query(p, 'SELECT count(*) FROM "Extract"."hourly_volume"') == [[2]]
