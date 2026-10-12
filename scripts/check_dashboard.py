"""Exercise actual browser interactions against an isolated database, with screenshots."""

import argparse
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache" / "playwright"))

import pandas as pd
import uvicorn
from playwright.sync_api import expect, sync_playwright

from country_atlas.api import create_app
from country_atlas.database import CountryDatabaseManager
from country_atlas.models import ScrapeProvenance
from country_atlas.scraper import parse_countries


def check(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory(prefix="atlas-browser-") as temporary:
        temporary_path = Path(temporary)
        manager = CountryDatabaseManager(temporary_path / "countries.db")
        records = parse_countries(
            (ROOT / "tests" / "fixtures" / "first_20_countries.html").read_text(encoding="utf-8")
        )
        metadata = CountryDatabaseManager(ROOT / "countries.db").latest_provenance()
        if metadata:
            manager.import_countries(records, ScrapeProvenance.model_validate(metadata))
        else:
            for record in records:
                manager.create(record)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            server = uvicorn.Server(
                uvicorn.Config(create_app(manager.database_path, read_only=False), log_level="error")
            )
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 15
                while not server.started:
                    if not thread.is_alive() or time.monotonic() > deadline:
                        raise RuntimeError("Browser-check API did not start")
                    time.sleep(0.05)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{port}")
                    expect(page.locator("#metric-count")).to_have_text("20")
                    expect(page.locator(".chart-point")).to_have_count(20)
                    expect(page.locator("#error-banner")).to_be_hidden()
                    page.screenshot(path=str(output_dir / "dashboard.png"))

                    page.get_by_role("button", name="Linear", exact=True).click()
                    expect(page.locator("#linear-button")).to_have_attribute("aria-pressed", "true")
                    page.get_by_role("button", name="Log1p", exact=True).click()
                    page.locator(".chart-point[aria-label^='Antarctica:']").click()
                    expect(page.locator("#detail-dialog")).to_be_visible()
                    expect(page.locator("#detail-capital")).to_contain_text("no capital")
                    page.locator("#detail-dialog").get_by_label("Close dialog").click()

                    page.get_by_role("button", name="Compare countries").click()
                    expect(page.locator("#comparison-note")).to_contain_text("densely populated")
                    page.locator("#compare-second").select_option("Antarctica")
                    expect(page.locator("#comparison-note")).to_contain_text("zero population")
                    page.locator("#compare-dialog").get_by_label("Close dialog").click()

                    with page.expect_download() as download_event:
                        page.get_by_role("link", name="Export CSV", exact=False).click()
                    download = download_event.value
                    csv_path = temporary_path / download.suggested_filename
                    download.save_as(csv_path)
                    assert len(pd.read_csv(csv_path)) == 20

                    page.locator("[data-nav='pipeline']").click()
                    expect(page.locator("#store-step")).to_have_text("20 records stored")
                    page.screenshot(path=str(output_dir / "pipeline.png"))
                    page.locator("[data-nav='records']").click()
                    page.locator("#search").fill("Mariehamn")
                    expect(page.locator("#country-rows tr")).to_have_count(1)
                    expect(page.locator("#country-rows")).to_contain_text("Åland")
                    page.locator("#search").fill("")
                    page.locator("#sort").select_option("population")
                    expect(page.locator("#country-rows tr").first).to_contain_text("Bangladesh")

                    page.get_by_role("button", name="Add country", exact=False).click()
                    page.locator("#field-name").fill("Atlas Demo")
                    # The UI must display raw text safely instead of turning a CRUD value into HTML.
                    page.locator("#field-capital").fill("<img src=x onerror=alert(1)>")
                    page.locator("#field-population").fill("42")
                    page.locator("#field-area").fill("12.5")
                    page.get_by_role("button", name="Save country", exact=True).click()
                    expect(page.locator("#record-dialog")).to_be_hidden()
                    expect(page.locator("#table-count")).to_have_text("21")
                    page.locator("#search").fill("Atlas Demo")
                    expect(page.locator("#country-rows")).to_contain_text("<img src=x onerror=alert(1)>")
                    expect(page.locator("#country-rows img")).to_have_count(0)
                    page.get_by_role("button", name="Edit Atlas Demo", exact=True).click()
                    expect(page.locator("#field-name")).to_be_disabled()
                    page.locator("#field-capital").fill("Atlas City")
                    page.locator("#field-population").fill("84")
                    page.get_by_role("button", name="Save country", exact=True).click()
                    expect(page.locator("#country-rows")).to_contain_text("Atlas City")
                    page.get_by_role("button", name="Explore Atlas Demo", exact=True).click()
                    page.get_by_role("button", name="Delete record", exact=True).click()
                    page.get_by_role("button", name="Delete country", exact=True).click()
                    expect(page.locator("#delete-dialog")).to_be_hidden()
                    expect(page.locator("#table-count")).to_have_text("20")

                    # A duplicate remains in the form with a human-readable error.
                    page.get_by_role("button", name="Add country", exact=False).click()
                    page.locator("#field-name").fill("Andorra")
                    page.locator("#field-capital").fill("Andorra la Vella")
                    page.locator("#field-population").fill("84000")
                    page.locator("#field-area").fill("468")
                    page.get_by_role("button", name="Save country", exact=True).click()
                    expect(page.locator("#form-error")).to_contain_text("already exists")
                    page.locator("#record-dialog").get_by_role("button", name="Cancel", exact=True).click()
                    page.locator("#search").fill("")
                    page.locator("#sort").select_option("source")

                    mobile = browser.new_page(
                        viewport={"width": 390, "height": 844},
                        device_scale_factor=1,
                        is_mobile=True,
                        has_touch=True,
                    )
                    mobile.on("pageerror", lambda error: errors.append(str(error)))
                    mobile.goto(f"http://127.0.0.1:{port}")
                    expect(mobile.locator("#metric-count")).to_have_text("20")
                    assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
                        "Mobile page overflows horizontally"
                    )
                    mobile.screenshot(path=str(output_dir / "mobile.png"))
                    mobile.locator("[data-nav='records']").click()
                    expect(mobile.locator("#records-section")).to_be_visible()
                    mobile.locator("#search").fill("Åland")
                    expect(mobile.locator("#country-rows tr")).to_have_count(1)
                    mobile.get_by_role("button", name="Explore Åland", exact=True).click()
                    expect(mobile.locator("#detail-dialog")).to_be_visible()
                    mobile.locator("#detail-dialog").get_by_label("Close dialog").click()
                    browser.close()
            finally:
                server.should_exit = True
                thread.join(timeout=10)
    assert not errors, f"Browser JavaScript errors: {errors}"
    return {
        "status": "passed",
        "javascript_errors": len(errors),
        "screenshots": str(output_dir),
        "checks": [
            "20 chart points",
            "zero population",
            "linear/log1p toggle",
            "comparison",
            "CSV download",
            "provenance",
            "search",
            "sorting",
            "create",
            "update",
            "delete",
            "duplicate error",
            "safe text rendering",
            "mobile layout",
            "mobile details",
        ],
    }


if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp" / "browser")
    arguments = parser.parse_args()
    result = check(arguments.output_dir)
    print(json.dumps(result, indent=2))
