# preprocess_aep.py
import json, re, numpy as np, pandas as pd
from pathlib import Path

IN_DIR = Path("scraped_json")
OUT_CSV = "aep_preprocessed_wide_2000_2022.csv"
SOURCE_LINK = "https://africa-energy-portal.org/database"
year_cols = [str(y) for y in range(2000, 2023)]
early_year_cols = [str(y) for y in range(2000, 2012)]

def load_from_json(dir_path: Path) -> pd.DataFrame:
    records = []
    for fp in sorted(dir_path.glob("*.json")):
        blob = json.loads(fp.read_text(encoding="utf-8"))
        if isinstance(blob, list):
            for block in blob:
                metric_full = block.get("_id")
                for item in block.get("data", []) or []:
                    records.append({
                        "country_code": item.get("id"),
                        "country_name": item.get("name"),
                        "year": item.get("year"),
                        "value": item.get("score"),
                        "unit": item.get("unit"),
                        "region_name": item.get("region_name"),
                        "indicator_topic": item.get("indicator_topic"),
                        "indicator_group": item.get("indicator_group"),
                        "indicator_name": item.get("indicator_name"),
                        "indicator_source": item.get("indicator_source"),
                        "metric": metric_full,
                        "__file": fp.name,
                    })
    return pd.DataFrame.from_records(records)

def preprocess():
    df = load_from_json(IN_DIR)
    df.rename(columns={
        "country_name": "country",
        "indicator_group": "sector",
        "indicator_topic": "sub_sector",
        "indicator_source": "source"
    }, inplace=True)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    def strip_unit_parenthetical(s):
        if not isinstance(s, str): return s
        return re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()

    df["sub_sub_sector"] = df["indicator_name"].apply(strip_unit_parenthetical)
    if "unit" not in df.columns or df["unit"].isna().all():
        df["unit"] = df["metric"].str.extract(r"\(([^()]*)\)\s*$", expand=False)
    df["source_link"] = SOURCE_LINK

    country_order = (df["country"].dropna().drop_duplicates().sort_values().reset_index(drop=True))
    serial_map = {name: i+1 for i, name in enumerate(country_order)}
    df["country_serial"] = df["country"].map(serial_map).astype("Int64")

    tidy = df[[
        "country", "country_serial", "metric", "unit", "sector", "sub_sector", "sub_sub_sector",
        "source_link", "source", "year", "value"
    ]].copy()

    wide = tidy.pivot_table(
        index=["country", "country_serial", "metric", "unit", "sector", "sub_sector", "sub_sub_sector", "source_link", "source"],
        columns="year", values="value", aggfunc="first"
    ).reset_index()

    for y in year_cols:
        y_int = int(y)
        if y_int in wide.columns:
            wide.rename(columns={y_int: y}, inplace=True)
        if y not in wide.columns:
            wide[y] = np.nan

    early_all_null_mask = wide[early_year_cols].isna().all(axis=1)
    wide.loc[early_all_null_mask, early_year_cols] = 0.0
    years_df = wide[year_cols].astype(float)
    years_interp = years_df.T.interpolate(limit_direction="both").T
    years_filled = years_interp.T.ffill().bfill().T
    wide[year_cols] = years_filled

    final_cols = ["country", "country_serial", "metric", "unit", "sector", "sub_sector",
                  "sub_sub_sector", "source_link", "source"] + year_cols
    wide = wide[final_cols].sort_values(["country_serial", "metric"]).reset_index(drop=True)
    wide.to_csv(OUT_CSV, index=False)
    print(f"✅ Saved -> {OUT_CSV}  (rows: {len(wide)}, cols: {len(wide.columns)})")

if __name__ == "__main__":
    preprocess()
