"""Describe each column of a table so the recommender can reason about it."""
import pandas as pd


def column_kind(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "timestamp"
    if pd.api.types.is_integer_dtype(s):
        return "integer"
    if pd.api.types.is_float_dtype(s):
        return "float"
    return "string"


def profile_table(name: str, df: pd.DataFrame) -> dict:
    cols = []
    for c in df.columns:
        s = df[c]
        kind = column_kind(s)
        info = {"name": c, "kind": kind, "n_distinct": int(s.nunique(dropna=True)), "null_frac": round(float(s.isna().mean()), 4)}
        if kind in ("integer", "float"):
            info.update(min=float(s.min()), max=float(s.max()), median=float(s.median()))
        cols.append(info)
    return {"name": name, "rows": int(len(df)), "columns": cols}
