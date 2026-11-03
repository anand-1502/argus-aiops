"""The SQL layer: `dbt build` runs every model and every data test (including reconciliation against the raw table)."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.data import needs_full_data

DBT = shutil.which("dbt") or str(Path.home() / ".local/bin/dbt")
PROJECT = Path(__file__).resolve().parent.parent / "dbt" / "argus"
pytestmark = [needs_full_data, pytest.mark.skipif(not Path(DBT).exists(), reason="dbt is not installed (uv tool install dbt-core --with dbt-postgres)")]


def test_dbt_build_passes_every_model_and_data_test():
    out = subprocess.run([DBT, "build", "--profiles-dir", str(PROJECT), "--project-dir", str(PROJECT)],
                         capture_output=True, text=True, env={**os.environ, "NO_COLOR": "1"})
    text = out.stdout + out.stderr
    assert out.returncode == 0, text[-2500:]
    m = re.search(r"PASS=(\d+) WARN=(\d+) ERROR=(\d+) SKIP=(\d+)", text)
    assert m, text[-800:]
    passed, warn, error, skip = map(int, m.groups())
    assert error == 0 and skip == 0 and passed >= 44, m.group(0)
