"""Phase 5 (BI export): the recommender explains each suggestion, and only suggests what the data supports."""
import pandas as pd

from bi.profile import profile_table
from bi.recommend import recommend_charts, recommend_fields

VOLUME = pd.DataFrame({
    "hour": pd.date_range("2008-11-10", periods=48, freq="h"),
    "events": range(1000, 1048), "anomalous_events": range(30, 78),
})
COMPONENTS = pd.DataFrame({"component": list("ABCDE") * 4, "level": ["INFO", "WARN"] * 10, "events": range(20)})


def charts(df, name="t"):
    return recommend_charts([profile_table(name, df)])


def test_timestamp_plus_numeric_gives_a_line_chart_with_a_reason():
    line = [c for c in charts(VOLUME) if c["chart"] == "line"]
    assert {c["y"] for c in line} == {"events", "anomalous_events"}
    assert all(c["x"] == "hour" and "trend" in c["reason"] for c in line)


def test_low_cardinality_category_gives_bars_and_two_value_column_gives_a_kpi():
    got = charts(COMPONENTS)
    assert any(c["chart"] == "bar" and c["x"] == "component" for c in got)
    assert any(c["chart"] == "kpi" and c["field"] == "level" for c in got)


def test_high_cardinality_string_becomes_a_filter_not_an_axis():
    df = pd.DataFrame({"block_id": [f"blk_{i}" for i in range(200)], "n": range(200)})
    got = charts(df)
    assert any(c["chart"] == "filter" and c["field"] == "block_id" for c in got)
    assert not any(c["chart"] == "bar" and c["x"] == "block_id" for c in got)


def test_skewed_measure_gets_a_log_scale_suggestion():
    x = [1] * 40 + list(range(2, 12)) + [100000, 100001]  # many distinct values, one huge tail
    df = pd.DataFrame({"x": x, "y": range(len(x))})
    assert any(c["chart"] == "scale" and c["field"] == "x" for c in charts(df))


def test_no_scatter_when_there_is_a_time_axis():
    assert not any(c["chart"] == "scatter" for c in charts(VOLUME))


def test_anomaly_rate_field_is_suggested_with_both_tableau_and_dax():
    f = recommend_fields([profile_table("hourly_volume", VOLUME)])
    rate = next(x for x in f if x["name"] == "Anomaly rate")
    assert rate["tableau"] == "SUM([anomalous_events]) / SUM([events])"
    assert rate["dax"].startswith("Anomaly rate = DIVIDE(") and "'hourly_volume'" in rate["dax"]


def test_nothing_is_suggested_for_a_column_set_that_does_not_support_it():
    assert recommend_fields([profile_table("t", pd.DataFrame({"a": [1, 2, 3]}))]) == []
