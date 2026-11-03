"""Rule-based chart and calculated-field suggestions from column types and distributions.

No model involved: each rule is a short, explainable check, and every suggestion carries the reason it fired.
"""

LOW_CARDINALITY = 12   # a category axis stays readable up to about this many values
HIGH_CARDINALITY = 50  # beyond this a column is an identifier or a filter, not an axis
SKEW_RATIO = 10        # max / median above this is heavily right-skewed


def _numeric(cols):
    return [c for c in cols if c["kind"] in ("integer", "float")]


def recommend_charts(tables: list[dict]) -> list[dict]:
    out = []
    for t in tables:
        cols = t["columns"]
        measures = [c for c in _numeric(cols) if c["n_distinct"] > 2]
        times = [c for c in cols if c["kind"] == "timestamp"]
        cats = [c for c in cols if c["kind"] == "string" and 2 <= c["n_distinct"] <= LOW_CARDINALITY]
        flags = [c for c in cols if c["n_distinct"] == 2 and c["kind"] in ("string", "boolean")]

        for tm in times:
            for m in measures:
                out.append({"table": t["name"], "chart": "line", "x": tm["name"], "y": m["name"],
                            "reason": f"{tm['name']} is a timestamp and {m['name']} is numeric, so show it as a trend"})
        for ca in cats:
            for m in measures[:2]:
                out.append({"table": t["name"], "chart": "bar", "x": ca["name"], "y": m["name"], "sort": "descending",
                            "reason": f"{ca['name']} has {ca['n_distinct']} values, few enough to compare as bars"})
        for fl in flags:
            out.append({"table": t["name"], "chart": "kpi", "field": fl["name"],
                        "reason": f"{fl['name']} has exactly two values, so its share is a natural headline number"})
        for i, a in enumerate(measures):
            for b in measures[i + 1:]:
                if a["name"] != b["name"] and not times:
                    out.append({"table": t["name"], "chart": "scatter", "x": a["name"], "y": b["name"],
                                "reason": f"two numeric columns in a table with no time axis: check how {a['name']} relates to {b['name']}"})
        for m in measures:
            if m["median"] > 0 and m["max"] / m["median"] > SKEW_RATIO:
                out.append({"table": t["name"], "chart": "scale", "field": m["name"], "scale": "log",
                            "reason": f"{m['name']} is heavily skewed (max is {m['max'] / m['median']:.0f}x the median), so use a log axis"})
        for c in cols:
            if c["kind"] == "string" and c["n_distinct"] > HIGH_CARDINALITY:
                out.append({"table": t["name"], "chart": "filter", "field": c["name"],
                            "reason": f"{c['name']} has {c['n_distinct']} values: too many for an axis, use it as a filter or drill-down"})
    return out


def recommend_fields(tables: list[dict]) -> list[dict]:
    """Calculated fields, as Tableau expressions and DAX measures."""
    out = []
    for t in tables:
        names = {c["name"] for c in t["columns"]}
        n = t["name"]
        if {"events", "anomalous_events"} <= names:
            out.append({"table": n, "name": "Anomaly rate",
                        "tableau": "SUM([anomalous_events]) / SUM([events])",
                        "dax": f"Anomaly rate = DIVIDE(SUM('{n}'[anomalous_events]), SUM('{n}'[events]))",
                        "reason": "both a count and its anomalous subset exist, so the rate is the useful measure"})
        if "label" in names:
            out.append({"table": n, "name": "Anomalous blocks",
                        "tableau": "SUM(IF [label] = 'Anomaly' THEN 1 ELSE 0 END)",
                        "dax": f"Anomalous blocks = CALCULATE(COUNTROWS('{n}'), '{n}'[label] = \"Anomaly\")",
                        "reason": "label has an 'Anomaly' value that should be counted directly"})
        if {"verified", "runbook_correct"} <= names:
            out.append({"table": n, "name": "Agent accuracy",
                        "tableau": "SUM(INT([runbook_correct])) / COUNT([block_id])",
                        "dax": f"Agent accuracy = DIVIDE(COUNTROWS(FILTER('{n}', '{n}'[runbook_correct] = TRUE())), COUNTROWS('{n}'))",
                        "reason": "per-incident correctness flags roll up to an accuracy"})
    return out
