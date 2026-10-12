import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import quote

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from country_atlas.analytics import csv_text, scatter_png, summarize, to_dataframe
from country_atlas.api import create_app
from country_atlas.database import CountryAlreadyExistsError, CountryDatabaseManager, CountryNotFoundError
from country_atlas.models import Country, CountryDetails, ScrapeProvenance
from country_atlas.scraper import ScrapeError, activate_source_snapshot, parse_countries, scrape_countries
from run_pipeline import run


def provenance(count):
    return ScrapeProvenance(
        source_url="https://www.scrapethissite.com/pages/simple/",
        scraped_at="2026-10-12T00:00:00+00:00",
        source_sha256="a" * 64,
        record_count=count,
    )


def test_source_order_types_unicode_zero_and_scope(source_html):
    # The 21st entry is deliberately malformed: it must never be extracted or validated.
    records = parse_countries(source_html + '<div class="country">OUTSIDE SCOPE</div>')
    assert len(records) == 20
    assert records[0].country_name == "Andorra"
    assert records[-1].country_name == "Belgium"
    assert records[14].country_name == "Åland"
    assert records[8].population == 0
    assert records[8].area == 14_000_000.0
    assert all(type(record.population) is int and type(record.area) is float for record in records)


@pytest.mark.parametrize(
    "change",
    [
        lambda html: html.replace('class="country-area"', 'class="missing-area"', 1),
        lambda html: html.replace("84000", "invalid-number", 1),
        lambda html: '<div class="country"></div>',
    ],
)
def test_scraper_rejects_bad_source_without_partial_results(source_html, change):
    with pytest.raises(ScrapeError):
        parse_countries(change(source_html))


def test_database_crud_natural_key_and_persistence(manager):
    new_country = Country(country_name="O'Brien's Island", capital="Test Town", population=123, area=4.5)
    manager.create(new_country)
    assert manager.read(new_country.country_name) == new_country
    with pytest.raises(CountryAlreadyExistsError):
        manager.create(new_country)
    details = CountryDetails(capital="Updated Town", population=456, area=8.5)
    updated = manager.update(new_country.country_name, details)
    assert CountryDatabaseManager(manager.database_path).read(new_country.country_name) == updated
    with sqlite3.connect(manager.database_path) as connection:
        schema = connection.execute("PRAGMA table_info(countries)").fetchall()
        assert [(row[1], row[5]) for row in schema if row[5]] == [("country_name", 1)]
    manager.delete(new_country.country_name)
    with pytest.raises(CountryNotFoundError):
        manager.read(new_country.country_name)


def test_import_is_idempotent_and_preserves_user_rows(manager, sample_countries):
    manual = Country(country_name="Manual Entry", capital="Local", population=1, area=2.0)
    manager.create(manual)
    manager.import_countries(sample_countries, provenance(3))
    manager.import_countries(sample_countries, provenance(3))
    assert len(manager.read_all()) == 4
    assert manager.read(manual.country_name) == manual
    assert manager.latest_provenance()["record_count"] == 3


def test_import_rolls_back_all_rows_and_metadata(manager, sample_countries):
    original = manager.read_all()
    with sqlite3.connect(manager.database_path) as connection:
        connection.execute("""CREATE TRIGGER reject_bad BEFORE INSERT ON countries
                            WHEN NEW.capital = 'Reject' BEGIN SELECT RAISE(ABORT, 'test rejection'); END""")
    changed = Country(country_name="Åland", capital="Different", population=22, area=10.0)
    rejected = Country(country_name="Rejected", capital="Reject", population=1, area=1.0)
    with pytest.raises(sqlite3.IntegrityError):
        manager.import_countries([changed, rejected], provenance(2))
    assert manager.read_all() == original
    assert manager.latest_provenance() is None


def test_api_complete_crud_round_trip(client):
    payload = {"country_name": "Test Republic", "capital": "Test Capital", "population": 1234, "area": 567.8}
    assert client.post("/countries", json=payload).status_code == 201
    assert client.post("/countries", json=payload).status_code == 409
    url = "/countries/Test%20Republic"
    assert client.get(url).json() == payload
    details = {"capital": "New Capital", "population": 2000, "area": 600.0}
    updated = client.put(url, json=details)
    assert updated.status_code == 200
    assert updated.json() == {"country_name": "Test Republic", **details}
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.put(url, json=details).status_code == 404
    assert client.delete(url).status_code == 404


def test_unicode_names_and_search(client):
    assert client.get("/countries/" + quote("Åland")).json()["capital"] == "Mariehamn"
    # Canonically equivalent composed/decomposed Unicode refers to the same natural key.
    assert client.get("/countries/" + quote("A\u030aland")).status_code == 200
    assert [country["country_name"] for country in client.get("/countries?q=DHAKA").json()] == ["Bangladesh"]


@pytest.mark.parametrize(
    "patch",
    [
        {"population": -1},
        {"population": 1.5},
        {"population": "100"},
        {"population": True},
        {"population": 9_007_199_254_740_992},
        {"area": 0},
        {"area": -2},
        {"area": "100"},
        {"area": 1e-310},
        {"country_name": " "},
        {"country_name": "A/B"},
        {"country_name": "."},
        {"country_name": ".."},
        {"capital": " "},
        {"capital": "A\x00B"},
        {"unexpected_field": "no"},
    ],
)
def test_api_rejects_invalid_or_unknown_input(client, patch):
    payload = {"country_name": "Valid Name", "capital": "Valid Capital", "population": 100, "area": 200.0}
    assert client.post("/countries", json={**payload, **patch}).status_code == 422
    assert len(client.get("/countries").json()) == 3


def test_injection_is_literal_and_exports_are_spreadsheet_safe(client):
    name = "x'; DROP TABLE countries; --"
    payload = {"country_name": name, "capital": "=1+1", "population": 1, "area": 2.0}
    assert client.post("/countries", json=payload).status_code == 201
    assert client.get("/countries/" + quote(name, safe="")).json() == payload
    exported = pd.read_csv(StringIO(client.get("/exports/countries.csv").text))
    assert exported.iloc[-1].capital == "'=1+1"
    assert len(client.get("/countries").json()) == 4


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_json_numbers_return_validation_error(client, literal):
    body = '{"country_name":"Invalid Area","capital":"Test","population":1,"area":' + literal + "}"
    response = client.post("/countries", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "finite_number"


def test_api_body_limits_cross_origin_and_headers(client):
    assert (
        client.post(
            "/countries", content="x" * 8193, headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )
    assert client.post("/countries", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert (
        client.delete("/countries/Antarctica", headers={"Origin": "https://other.example"}).status_code == 403
    )
    assert client.delete("/countries/Antarctica", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/health", headers={"Host": "untrusted.example"}).status_code == 400


def test_read_only_demo_keeps_reads_and_blocks_all_mutations(manager):
    with TestClient(create_app(manager.database_path, read_only=True)) as client:
        assert client.get("/countries").status_code == 200
        assert client.get("/health").json()["read_only"] is True
        for method, path in [
            ("POST", "/countries"),
            ("PUT", "/countries/Åland"),
            ("DELETE", "/countries/Åland"),
        ]:
            assert client.request(method, path, json={}).status_code == 403


def test_analytics_and_exports_keep_all_rows(client, sample_countries):
    response = client.get("/analytics/summary").json()
    assert response["count"] == 3
    assert response["zero_population_count"] == 1
    assert response["largest_country"] == "Antarctica"
    assert response["densest_country"] == "Bangladesh"
    frame = pd.read_csv(StringIO(client.get("/exports/countries.csv").text))
    assert list(frame.columns) == ["country_name", "capital", "population", "area"]
    assert len(frame) == 3
    assert frame.iloc[0].country_name == "Åland"
    for log_scale in [False, True]:
        response = client.get("/exports/population_vs_area.png", params={"log_scale": log_scale})
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        with Image.open(BytesIO(response.content)) as image:
            assert image.width >= 1500 and image.height >= 1000
            image.verify()


def test_empty_and_single_row_analytics_are_valid():
    assert summarize([])["count"] == 0
    only = Country(country_name="Empty Population", capital="None", population=0, area=1.0)
    assert summarize([only])["population_area_correlation"] is None
    empty = to_dataframe([])
    assert csv_text(empty) == "country_name,capital,population,area\n"
    assert scatter_png(empty).startswith(b"\x89PNG")


def test_real_http_pipeline_exports_database_records(manager, tmp_path):
    output = tmp_path / "exports"
    manifest = run(manager.database_path, output, skip_scrape=True)
    frame = pd.read_csv(output / "exported_countries.csv")
    assert len(frame) == 3
    assert manifest["analytics"]["count"] == 3
    assert (
        json.loads((output / "pipeline_manifest.json").read_text())["artifacts"][0]
        == "exported_countries.csv"
    )
    assert (output / "population_vs_area.png").read_bytes().startswith(b"\x89PNG")
    assert (output / "population_vs_area_log.png").read_bytes().startswith(b"\x89PNG")


def test_failed_refresh_preserves_the_previous_source_snapshot(tmp_path, source_html):
    snapshot = tmp_path / "source.html"
    old_content = source_html.encode("utf-8")
    new_content = old_content.replace(b"84000", b"84001", 1)
    old_digest = hashlib.sha256(old_content).hexdigest()
    old_provenance = provenance(20).model_copy(update={"source_sha256": old_digest})
    snapshot.write_bytes(old_content)
    archive = tmp_path / "snapshots"
    archive.mkdir()
    (archive / f"{old_digest}.html").write_bytes(old_content)
    manager = CountryDatabaseManager(tmp_path / "refresh.db")
    manager.import_countries(parse_countries(source_html), old_provenance)
    with sqlite3.connect(manager.database_path) as connection:
        connection.execute("""CREATE TRIGGER reject_refresh BEFORE UPDATE ON countries
                              BEGIN SELECT RAISE(ABORT, 'simulated failed import'); END""")
    response = MagicMock(status_code=200, content=new_content)
    with patch("country_atlas.scraper.requests.Session") as mocked_session:
        mocked_session.return_value.__enter__.return_value.get.return_value = response
        countries, refreshed_provenance = scrape_countries(snapshot)
    with pytest.raises(sqlite3.IntegrityError):
        manager.import_countries(countries, refreshed_provenance)
    assert snapshot.read_bytes() == old_content
    assert manager.latest_provenance()["source_sha256"] == old_digest
    assert (archive / f"{refreshed_provenance.source_sha256}.html").read_bytes() == new_content
    assert (archive / f"{old_digest}.html").read_bytes() == old_content
    with sqlite3.connect(manager.database_path) as connection:
        connection.execute("DROP TRIGGER reject_refresh")
    manager.import_countries(countries, refreshed_provenance)
    activate_source_snapshot(snapshot, refreshed_provenance)
    assert snapshot.read_bytes() == new_content
    assert manager.read("Andorra").population == 84001


def test_snapshot_activation_rejects_a_corrupted_archive(tmp_path):
    snapshot = tmp_path / "source.html"
    snapshot.write_bytes(b"previous successful source")
    archive = tmp_path / "snapshots"
    archive.mkdir()
    metadata = provenance(20)
    (archive / f"{metadata.source_sha256}.html").write_bytes(b"corrupted archive")
    with pytest.raises(ScrapeError, match="checksum"):
        activate_source_snapshot(snapshot, metadata)
    assert snapshot.read_bytes() == b"previous successful source"


def test_launcher_honors_a_custom_database_path(tmp_path):
    import shlex

    root = Path(__file__).resolve().parent.parent
    launcher = tmp_path / "launcher"
    launcher.mkdir()
    shutil.copy2(root / "start.sh", launcher / "start.sh")
    python_path = launcher / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    # Run the launcher's real checks, but avoid starting a second real server.
    python_path.write_text(
        '#!/usr/bin/env bash\nif [ "$1" = "-m" ] && [ "$2" = "uvicorn" ]; then exit 0; fi\n'
        + f'exec {shlex.quote(sys.executable)} "$@"\n'
    )
    python_path.chmod(0o755)
    custom_database = tmp_path / "state" / "custom.db"
    CountryDatabaseManager(custom_database)
    environment = {**os.environ, "ATLAS_DATABASE_PATH": str(custom_database), "PYTHONPATH": str(root)}
    result = subprocess.run(
        ["bash", str(launcher / "start.sh")], env=environment, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert "Run the pipeline first" not in result.stdout
    assert "http://127.0.0.1:8000" in result.stdout
