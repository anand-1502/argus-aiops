"""Phase 5 (BI export): the Power BI package is complete and self-consistent."""
import zipfile

import pandas as pd
import pytest

from bi.powerbi import write_package
from bi.profile import profile_table
from bi.recommend import recommend_charts, recommend_fields

TABLES = {
    "hourly_volume": pd.DataFrame({"hour": pd.date_range("2008-11-10", periods=24, freq="h"), "events": range(1000, 1024), "anomalous_events": range(10, 34)}),
    "block_summary": pd.DataFrame({"block_id": [f"blk_{i}" for i in range(60)], "label": ["Normal", "Anomaly"] * 30, "n_events": range(60)}),
    "agent_incidents": pd.DataFrame({"block_id": [f"blk_{i}" for i in range(6)], "verified": [True] * 6, "runbook_correct": [True] * 6}),
}


@pytest.fixture
def pkg(tmp_path):
    profiles = [profile_table(n, d) for n, d in TABLES.items()]
    zp = write_package(tmp_path / "argus_powerbi", TABLES, profiles, recommend_charts(profiles), recommend_fields(profiles))
    return tmp_path / "argus_powerbi", zp


def test_package_has_data_model_measures_loader_and_visuals(pkg):
    folder, _ = pkg
    for f in ["README.md", "model.md", "measures.dax", "load.pq", "visuals.md"]:
        assert (folder / f).read_text().strip(), f
    for n in TABLES:
        assert (folder / "data" / f"{n}.csv").exists() and (folder / "data" / f"{n}.parquet").exists()


def test_csv_round_trips_the_data(pkg):
    folder, _ = pkg
    back = pd.read_csv(folder / "data" / "hourly_volume.csv")
    assert len(back) == 24 and list(back.columns) == ["hour", "events", "anomalous_events"]


def test_model_lists_the_relationship_only_when_both_tables_exist(pkg, tmp_path):
    assert "`agent_incidents[block_id]` -> `block_summary[block_id]`" in (pkg[0] / "model.md").read_text()
    only = {"hourly_volume": TABLES["hourly_volume"]}
    prof = [profile_table(n, d) for n, d in only.items()]
    write_package(tmp_path / "solo", only, prof, [], [])
    assert "- none" in (tmp_path / "solo" / "model.md").read_text()


def test_dax_measures_reference_real_tables_and_columns(pkg):
    dax = (pkg[0] / "measures.dax").read_text()
    assert "Anomaly rate = DIVIDE(SUM('hourly_volume'[anomalous_events]), SUM('hourly_volume'[events]))" in dax
    assert "Agent accuracy" in dax and "Anomalous blocks" in dax


def test_power_query_loader_types_every_column(pkg):
    m = (pkg[0] / "load.pq").read_text()
    assert '{"hour", type datetime}' in m and '{"events", Int64.Type}' in m and '{"verified", type logical}' in m


def test_zip_contains_everything(pkg):
    _, zp = pkg
    names = set(zipfile.ZipFile(zp).namelist())
    assert "argus_powerbi/model.md" in names and "argus_powerbi/data/block_summary.csv" in names
