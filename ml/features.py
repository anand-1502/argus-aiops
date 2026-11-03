"""Build one feature row per HDFS block from the parsed events in Postgres."""
import pandas as pd

from api.db import connect

COUNTS_SQL = "SELECT block_id, template, count(*)::int AS n FROM events WHERE block_id <> '' GROUP BY 1, 2"
STATS_SQL = """
SELECT block_id,
       count(*)::int AS n_events,
       extract(epoch FROM max(ts) - min(ts))::float8 AS duration_s,
       (count(*) FILTER (WHERE level = 'WARN'))::int AS n_warn
FROM events WHERE block_id <> '' GROUP BY 1
"""
LABELS_SQL = "SELECT block_id, label FROM block_labels"
TEMPLATES_SQL = "SELECT template FROM events GROUP BY 1 ORDER BY count(*) DESC, template"


def build_matrix(counts: pd.DataFrame, stats: pd.DataFrame, labels: pd.DataFrame, templates: list[str]):
    """Return (X, y). X is indexed by block_id; y is 1 for Anomaly. Unlabeled blocks are dropped."""
    wide = counts.pivot_table(index="block_id", columns="template", values="n", aggfunc="sum", fill_value=0)
    wide = wide.reindex(columns=templates, fill_value=0)
    wide.columns = [f"tpl_{i}" for i in range(len(templates))]
    X = wide.join(stats.set_index("block_id"), how="inner")
    lab = labels.set_index("block_id")["label"]
    X = X.loc[X.index.intersection(lab.index)].sort_index()
    y = (lab.loc[X.index] == "Anomaly").astype(int)
    return X, y


def load_dataset():
    """Query Postgres and return (X, y, templates)."""
    with connect() as conn:
        templates = [r["template"] for r in conn.execute(TEMPLATES_SQL).fetchall()]
        counts = pd.DataFrame(conn.execute(COUNTS_SQL).fetchall())
        stats = pd.DataFrame(conn.execute(STATS_SQL).fetchall())
        labels = pd.DataFrame(conn.execute(LABELS_SQL).fetchall())
    X, y = build_matrix(counts, stats, labels, templates)
    return X, y, templates
