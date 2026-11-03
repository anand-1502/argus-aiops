"""Write a Power BI-ready package: clean data files, a documented model, DAX measures, a Power Query loader
and the recommended visuals. It imports into free Power BI Desktop with no account, API or manual modelling."""
import zipfile
from pathlib import Path

import pandas as pd

# one-to-one or one-to-many links between tables (from_table.from_col -> to_table.to_col)
RELATIONSHIPS = [("agent_incidents", "block_id", "block_summary", "block_id", "many-to-one")]

M_TYPES = {"timestamp": "type datetime", "integer": "Int64.Type", "float": "type number", "string": "type text", "boolean": "type logical"}


def _m_loader(profiles: list[dict]) -> str:
    lines = ["// Power Query: Home > Get data > Blank query > Advanced editor > paste this, then set DATA_DIR.",
             "let", '    DATA_DIR = "C:\\\\path\\\\to\\\\argus_powerbi\\\\data\\\\",']
    parts = []
    for t in profiles:
        n = t["name"]
        types = ", ".join(f'{{"{c["name"]}", {M_TYPES[c["kind"]]}}}' for c in t["columns"])
        lines += [f'    {n}_raw = Csv.Document(File.Contents(DATA_DIR & "{n}.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
                  f"    {n}_hdr = Table.PromoteHeaders({n}_raw, [PromoteAllScalars=true]),",
                  f"    {n} = Table.TransformColumnTypes({n}_hdr, {{{types}}}),"]
        parts.append(n)
    lines += [f"    Result = [{', '.join(f'{p} = {p}' for p in parts)}]", "in", "    Result"]
    return "\n".join(lines)


def _model_doc(profiles: list[dict]) -> str:
    out = ["# Data model", "", "Tables and columns (type, distinct values):", ""]
    for t in profiles:
        out.append(f"## {t['name']} ({t['rows']:,} rows)")
        out += [f"- `{c['name']}`: {c['kind']}, {c['n_distinct']:,} distinct" for c in t["columns"]]
        out.append("")
    names = {t["name"] for t in profiles}
    rel = [r for r in RELATIONSHIPS if r[0] in names and r[2] in names]
    out += ["## Relationships (Model view > Manage relationships)", ""]
    out += [f"- `{a}[{ac}]` -> `{b}[{bc}]` ({card}, single direction)" for a, ac, b, bc, card in rel] or ["- none"]
    out += ["", "`hourly_volume` and `component_level` are standalone aggregates and need no relationship."]
    return "\n".join(out)


def _visuals_doc(charts: list[dict]) -> str:
    out = ["# Recommended visuals", "", "Each suggestion comes from a rule on column types and distributions, with the reason it fired.", ""]
    for c in charts:
        if c["chart"] in ("line", "bar", "scatter"):
            out.append(f"- **{c['chart']}** on `{c['table']}`: x = `{c['x']}`, y = `{c['y']}`. {c['reason']}.")
        elif c["chart"] == "kpi":
            out.append(f"- **card** on `{c['table']}`: `{c['field']}`. {c['reason']}.")
        elif c["chart"] == "scale":
            out.append(f"- **log axis** for `{c['table']}[{c['field']}]`. {c['reason']}.")
        else:
            out.append(f"- **slicer** on `{c['table']}[{c['field']}]`. {c['reason']}.")
    return "\n".join(out)


def write_package(out: Path, tables: dict[str, pd.DataFrame], profiles: list[dict], charts: list[dict], fields: list[dict]) -> Path:
    """Write the folder and return the path of its zip."""
    data = out / "data"
    data.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(data / f"{name}.csv", index=False)
        df.to_parquet(data / f"{name}.parquet", index=False)
    (out / "load.pq").write_text(_m_loader(profiles))
    (out / "model.md").write_text(_model_doc(profiles))
    (out / "measures.dax").write_text("\n\n".join(f"// {f['reason']}\n{f['dax']}" for f in fields) + "\n")
    (out / "visuals.md").write_text(_visuals_doc(charts))
    (out / "README.md").write_text(
        "# Argus Power BI package\n\n1. Open Power BI Desktop (free).\n2. Home > Get data > Blank query > Advanced editor, paste `load.pq`, "
        "set `DATA_DIR`, then load each table from the result. (Or use Get data > Text/CSV on the files in `data/`; "
        "Parquet files are included too.)\n3. Create the relationships listed in `model.md`.\n"
        "4. Add the measures from `measures.dax` (New measure, paste one at a time).\n5. Build the visuals listed in `visuals.md`.\n")
    zip_path = out.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out.parent))
    return zip_path
