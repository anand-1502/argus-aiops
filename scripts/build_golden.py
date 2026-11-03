"""Build the golden eval set and the small fixtures CI uses instead of the 11M-row database.

Golden set: the 6 seeded incidents (which the agent was tuned on) plus 24 held-out ones, 4 per failure
signature, chosen by a hash of the block id so the pick does not depend on how the agent behaves.
Fixtures: every golden block's events, the template stats, and a stratified sample of the classifier's
feature matrix.
"""
import csv
import json
from pathlib import Path

from api.db import connect
from scripts.seed_incidents import ALL, SIGNATURES

ROOT = Path(__file__).resolve().parent.parent
PER_SIGNATURE = 4


def main() -> None:
    seeded = json.loads((ROOT / "agent" / "incidents.json").read_text())
    golden = [{**i, "split": "seeded"} for i in seeded]
    taken = {i["block_id"] for i in seeded}
    with connect() as conn:
        for rb, pat in SIGNATURES:
            others = [p for p in ALL if p != pat]
            clause = " AND ".join("NOT bool_or(e.template LIKE %s)" for _ in others)
            rows = conn.execute(
                f"""SELECT e.block_id, min(e.ts) AS first_ts, max(e.ts) AS last_ts, count(*) AS n_events
                    FROM events e JOIN block_labels l USING (block_id)
                    WHERE l.label = 'Anomaly'
                    GROUP BY e.block_id
                    HAVING bool_or(e.template LIKE %s) AND {clause} AND count(*) BETWEEN 3 AND 40
                    ORDER BY md5(e.block_id) LIMIT %s""",
                [pat, *others, PER_SIGNATURE + len(seeded)],
            ).fetchall()
            added = 0
            for r in rows:
                if r["block_id"] in taken or added == PER_SIGNATURE:
                    continue
                line = conn.execute(
                    "SELECT content FROM events WHERE block_id = %s AND template LIKE %s ORDER BY ts LIMIT 1",
                    [r["block_id"], pat],
                ).fetchone()["content"]
                golden.append({"block_id": r["block_id"], "expected_runbook": rb, "first_ts": r["first_ts"].isoformat(),
                               "last_ts": r["last_ts"].isoformat(), "n_events": r["n_events"], "signature_line": line, "split": "heldout"})
                taken.add(r["block_id"])
                added += 1
        (ROOT / "eval" / "golden.json").write_text(json.dumps(golden, indent=2))

        # events + template stats + labels for exactly these blocks (CI loads them into an empty Postgres)
        ids = [g["block_id"] for g in golden]
        ev = conn.execute(
            "SELECT block_id, ts, pid, level, component, content, template FROM events WHERE block_id = ANY(%s) ORDER BY block_id, ts, pid, content", [ids]
        ).fetchall()
        with (ROOT / "eval/fixtures/golden_events.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["block_id", "ts", "pid", "level", "component", "content", "template"])
            w.writerows([[r["block_id"], r["ts"].isoformat(), r["pid"], r["level"], r["component"], r["content"], r["template"]] for r in ev])
        ts = conn.execute("SELECT template, blocks, frac_blocks FROM template_stats ORDER BY template").fetchall()
        with (ROOT / "eval/fixtures/template_stats.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["template", "blocks", "frac_blocks"])
            w.writerows([[r["template"], r["blocks"], r["frac_blocks"]] for r in ts])

    # stratified sample of the classifier's feature matrix (all 16,838 anomalies would be too big; keep the 2.93% rate)
    from ml.features import load_dataset

    X, y, _ = load_dataset()
    pos = y[y == 1].sample(600, random_state=0).index
    neg = y[y == 0].sample(20_000, random_state=0).index
    sample = X.loc[list(pos) + list(neg)].assign(label=y.loc[list(pos) + list(neg)])
    sample.to_parquet(ROOT / "ml/fixtures/features_sample.parquet")
    print(f"golden: {len(golden)} incidents ({sum(g['split']=='heldout' for g in golden)} held out); "
          f"{len(ev)} fixture events; feature sample {len(sample)} blocks, {int(sample['label'].sum())} anomalous")


if __name__ == "__main__":
    main()
