"""Standalone requests client: fetch, print a Pandas DataFrame, export CSV and PNGs."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import requests
from pydantic import TypeAdapter, ValidationError

from country_atlas.analytics import csv_text, scatter_png, summarize, to_dataframe
from country_atlas.models import Country
from country_atlas.settings import PROJECT_ROOT


def fetch_countries(base_url: str) -> list[Country]:
    response = requests.get(f"{base_url.rstrip('/')}/countries", timeout=(5, 30))
    response.raise_for_status()
    return TypeAdapter(list[Country]).validate_python(response.json())


def export_from_api(base_url: str, output_dir: Path) -> dict:
    records = fetch_countries(base_url)
    frame = to_dataframe(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    with pd.option_context("display.max_rows", None, "display.max_columns", None, "display.width", 160):
        print(frame.to_string(index=False))
    (output_dir / "exported_countries.csv").write_text(csv_text(frame), encoding="utf-8")
    (output_dir / "population_vs_area.png").write_bytes(scatter_png(frame))
    (output_dir / "population_vs_area_log.png").write_bytes(scatter_png(frame, log_scale=True))
    report = summarize(records)
    (output_dir / "analytics_summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nExported {len(frame)} rows, two scatter plots, and an analytical summary to {output_dir}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    try:
        export_from_api(args.base_url, args.output_dir)
    except (requests.RequestException, ValidationError, ValueError, OSError) as exc:
        print(f"Client failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
