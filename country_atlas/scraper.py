"""Fetch the specified public sandbox and extract only its first 20 entries."""

import hashlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from country_atlas.models import Country, ScrapeProvenance
from country_atlas.settings import COUNTRY_LIMIT, SOURCE_URL


class ScrapeError(RuntimeError):
    """The source is unreachable or no longer matches its expected structure."""


def _write_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".atlas-", delete=False) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def activate_source_snapshot(snapshot_path: Path, provenance: ScrapeProvenance) -> None:
    """Update the latest-source pointer only after the caller commits the database import."""
    archive_path = snapshot_path.parent / "snapshots" / f"{provenance.source_sha256}.html"
    content = archive_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != provenance.source_sha256:
        raise ScrapeError("Archived source checksum does not match the import")
    _write_atomically(snapshot_path, content)


def parse_countries(html: str) -> list[Country]:
    """Keep source order, support scientific area notation, and fail on incomplete data."""
    nodes = BeautifulSoup(html, "html.parser").select(".country")[:COUNTRY_LIMIT]
    if len(nodes) != COUNTRY_LIMIT:
        raise ScrapeError(f"Expected {COUNTRY_LIMIT} country entries; found {len(nodes)}")
    countries: list[Country] = []
    for index, node in enumerate(nodes, start=1):

        def field(selector: str, node=node, index=index) -> str:
            element = node.select_one(selector)
            if element is None:
                raise ScrapeError(f"Entry {index} is missing {selector}")
            return element.get_text(strip=True)

        try:
            countries.append(
                Country(
                    country_name=field(".country-name"),
                    capital=field(".country-capital"),
                    population=int(field(".country-population").replace(",", "")),
                    area=float(field(".country-area").replace(",", "")),
                )
            )
        except ValueError as exc:
            raise ScrapeError(f"Invalid data in entry {index}: {exc}") from exc
    if len({country.country_name for country in countries}) != COUNTRY_LIMIT:
        raise ScrapeError("Source contains duplicate country names")
    return countries


def scrape_countries(snapshot_path: Path | None = None) -> tuple[list[Country], ScrapeProvenance]:
    retry = Retry(
        total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"]
    )
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retry))
        try:
            response = session.get(
                SOURCE_URL,
                timeout=(10, 30),
                allow_redirects=False,
                headers={"User-Agent": "CountryAtlas/1.0 (educational capstone; first 20 records)"},
            )
            response.raise_for_status()
            if response.status_code != 200:
                raise ScrapeError(f"Unexpected source response: HTTP {response.status_code}")
        except requests.RequestException as exc:
            raise ScrapeError(f"Unable to fetch the country source: {exc}") from exc
    # The page declares UTF-8. Decode explicitly to preserve Åland even if HTTP omits charset.
    html = response.content.decode("utf-8")
    countries = parse_countries(html)
    provenance = ScrapeProvenance(
        source_url=SOURCE_URL,
        scraped_at=datetime.now(UTC).isoformat(),
        source_sha256=hashlib.sha256(response.content).hexdigest(),
        record_count=len(countries),
    )
    if snapshot_path is not None:
        # Immutable-by-checksum archives keep earlier successful imports traceable
        # even if a later database transaction fails.
        archive_path = snapshot_path.parent / "snapshots" / f"{provenance.source_sha256}.html"
        if not archive_path.exists() or archive_path.read_bytes() != response.content:
            _write_atomically(archive_path, response.content)
    return countries, provenance
