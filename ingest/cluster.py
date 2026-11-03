"""Cluster near-duplicate log templates with FAISS.

Parsers split one message into several templates when a variable looks different
(for example a trailing extra field). Merging near-duplicates keeps the template list small
for retrieval and dashboards. The threshold is deliberately strict: two different failure
signatures can be close in embedding space (cosine about 0.90), and must never merge.
"""
import io
import json
import subprocess
import sys

import numpy as np

from api.db import connect

THRESHOLD = 0.95


def cluster_templates(templates: list[str], embeddings: np.ndarray, threshold: float = THRESHOLD) -> list[int]:
    """Greedy clustering in input order: a template joins the nearest existing representative if the
    cosine similarity reaches the threshold, otherwise it starts a new cluster. Embeddings must be unit length.
    FAISS runs in a worker process because it cannot share a process with torch on macOS."""
    buf = io.BytesIO()
    np.save(buf, np.asarray(embeddings, dtype="float32"))
    out = subprocess.run(
        [sys.executable, "-m", "ingest.faiss_worker", str(threshold)],
        input=buf.getvalue(), capture_output=True, check=True,
    )
    return json.loads(out.stdout)


def build_clusters() -> int:
    """Embed every template (most frequent first), cluster them and store the result in Postgres."""
    from kb.index import embedder

    with connect() as conn:
        rows = conn.execute("SELECT template, blocks FROM template_stats ORDER BY blocks DESC, template").fetchall()
        templates = [r["template"] for r in rows]
        emb = embedder().encode(templates, normalize_embeddings=True)
        labels = cluster_templates(templates, emb)
        rep = {}
        for t, lab in zip(templates, labels):
            rep.setdefault(lab, t)  # first (most frequent) member represents the cluster
        conn.execute("DROP TABLE IF EXISTS template_clusters")
        conn.execute("CREATE TABLE template_clusters (template text PRIMARY KEY, cluster_id int NOT NULL, representative text NOT NULL, blocks int NOT NULL)")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO template_clusters VALUES (%s, %s, %s, %s)",
                [(t, lab, rep[lab], r["blocks"]) for t, lab, r in zip(templates, labels, rows)],
            )
        conn.commit()
    return len(set(labels))


if __name__ == "__main__":
    print(f"{build_clusters()} clusters")
