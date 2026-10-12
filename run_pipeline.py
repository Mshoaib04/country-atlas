"""One command for the complete live scrape -> SQLite -> FastAPI -> requests -> exports flow."""

import argparse
import json
import socket
import threading
import time
from pathlib import Path

import uvicorn

from client import export_from_api
from country_atlas.api import create_app
from country_atlas.database import CountryDatabaseManager
from country_atlas.scraper import activate_source_snapshot, scrape_countries
from country_atlas.settings import DATABASE_PATH, PROJECT_ROOT


def run(database_path: Path, output_dir: Path, *, skip_scrape: bool = False) -> dict:
    manager = CountryDatabaseManager(database_path)
    if not skip_scrape:
        print("[1/4] Fetching the live source and validating the first 20 entries...")
        snapshot_path = PROJECT_ROOT / "data" / "source.html"
        countries, provenance = scrape_countries(snapshot_path)
        manager.import_countries(countries, provenance)
        activate_source_snapshot(snapshot_path, provenance)
        print(f"[2/4] Committed {len(countries)} rows to SQLite (natural key: country_name).")
    elif not manager.read_all():
        raise RuntimeError("No stored countries. Run without --skip-scrape first.")
    else:
        print("[1/4] Reusing the existing SQLite database (--skip-scrape).")
    # Hold the ephemeral socket throughout startup to avoid a find-free-port race.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(create_app(database_path), host="127.0.0.1", port=port, log_level="error")
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("Temporary API did not start")
                time.sleep(0.05)
            print(f"[3/4] FastAPI running temporarily at http://127.0.0.1:{port}; client uses real HTTP.")
            report = export_from_api(f"http://127.0.0.1:{port}", output_dir)
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    manifest = {
        "project": "Country Atlas",
        "database": str(database_path),
        "analytics": report,
        "provenance": manager.latest_provenance(),
        "artifacts": [
            "exported_countries.csv",
            "population_vs_area.png",
            "population_vs_area_log.png",
            "analytics_summary.json",
        ],
    }
    (output_dir / "pipeline_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        "[4/4] Pipeline complete. Start the dashboard: python -m uvicorn main:app --host 127.0.0.1 --port 8000"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--skip-scrape", action="store_true", help="Re-export stored data without fetching the source"
    )
    args = parser.parse_args()
    try:
        run(args.database, args.output_dir, skip_scrape=args.skip_scrape)
    except Exception as exc:
        print(f"Pipeline failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
