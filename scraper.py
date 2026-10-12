"""Standalone live scrape -> validated models -> SQLite import."""

import argparse
import json
import sys
from pathlib import Path

from country_atlas.database import CountryDatabaseManager
from country_atlas.scraper import ScrapeError, activate_source_snapshot, scrape_countries
from country_atlas.settings import DATABASE_PATH, PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the first 20 source countries into SQLite.")
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    args = parser.parse_args()
    try:
        snapshot_path = PROJECT_ROOT / "data" / "source.html"
        records, provenance = scrape_countries(snapshot_path)
        CountryDatabaseManager(args.database).import_countries(records, provenance)
        activate_source_snapshot(snapshot_path, provenance)
    except (ScrapeError, OSError) as exc:
        print(f"Scrape failed: {exc}", file=sys.stderr)
        return 1
    print(f"Imported {len(records)} countries into {args.database}")
    print(json.dumps(provenance.model_dump(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
