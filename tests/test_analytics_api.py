"""The analytics layer (dbt marts) as served to the dashboard."""
import pytest
from fastapi.testclient import TestClient

from api.main import SQL_VIEWABLE, app
from tests.data import needs_full_data

pytestmark = needs_full_data
client = TestClient(app)


def test_kpis_match_the_published_benchmark():
    k = client.get("/analytics/kpis").json()
    assert (k["total_events"], k["total_blocks"], k["anomalous_blocks"], k["anomaly_rate_pct"]) == (11_175_629, 575_061, 16_838, 2.93)
    assert 0 < k["incident_windows"] < k["anomalous_blocks"] and 0 < k["alert_reduction_pct"] < 100


def test_headline_is_reproducible_from_the_published_sensitivity_curve():
    k = client.get("/analytics/kpis").json()
    curve = {r["gap_seconds"]: r for r in client.get("/analytics/windows").json()["sensitivity"]}
    assert curve[30]["windows"] == k["incident_windows"]
    windows = [curve[g]["windows"] for g in sorted(curve)]
    assert windows == sorted(windows, reverse=True)  # wider gap, never more windows


def test_trend_flags_spikes_with_window_function_columns():
    rows = client.get("/analytics/trend").json()
    assert len(rows) >= 24 and rows == sorted(rows, key=lambda r: r["hour_ts"])
    assert sum(r["events"] for r in rows) == 11_175_629
    assert any(r["is_spike"] for r in rows) and all(r["moving_avg_3h"] is not None for r in rows)
    assert rows[0]["change_vs_prev_hour"] is None  # nothing precedes the first hour


def test_component_pareto_is_sorted_and_ends_at_100():
    rows = client.get("/analytics/components").json()
    cum = [r["cumulative_pct"] for r in rows]
    assert cum == sorted(cum) and 99.9 <= cum[-1] <= 100.1
    assert {r["plane"] for r in rows} >= {"Metadata plane", "Storage plane"}


@pytest.mark.parametrize("model", sorted(SQL_VIEWABLE))
def test_every_viewable_model_returns_real_sql(model):
    r = client.get(f"/analytics/sql/{model}").json()
    assert "select" in r["sql"].lower() and r["model"] == model


def test_unknown_or_path_like_model_names_are_refused():
    assert client.get("/analytics/sql/not_a_model").status_code == 404
    assert client.get("/analytics/sql/..%2F..%2Fpyproject").status_code == 404


def test_business_inputs_are_measured_numbers_not_savings():
    b = client.get("/business/inputs").json()
    assert b["incident_windows"] == client.get("/analytics/kpis").json()["incident_windows"]
    assert b["capture_hours"] >= 24 and b["agent_seconds"] > 0
    assert 0 < b["runbook_accuracy"] <= 1 and 0 < b["verified_rate"] <= 1
    assert not any("saving" in key or "cost" in key for key in b)  # the model lives in the browser, with its assumptions
