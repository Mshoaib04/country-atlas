"""SQLite persistence with natural keys, parameterized CRUD, and atomic imports."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from country_atlas.models import Country, CountryDetails, ScrapeProvenance, normalize_name


class CountryAlreadyExistsError(ValueError):
    """The natural primary key is already in use."""


class CountryNotFoundError(LookupError):
    """No country matches the supplied natural key."""


class CountryDatabaseManager:
    """Use short-lived connections so FastAPI worker threads can safely share this class."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS countries (
                    country_name TEXT NOT NULL PRIMARY KEY CHECK(length(country_name) BETWEEN 1 AND 120),
                    capital TEXT NOT NULL CHECK(length(capital) BETWEEN 1 AND 160),
                    population INTEGER NOT NULL CHECK(typeof(population) = 'integer' AND population >= 0),
                    area REAL NOT NULL CHECK(area > 0)
                );
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id INTEGER PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    scraped_at TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    record_count INTEGER NOT NULL
                );
            """)

    @staticmethod
    def _row_to_country(row: sqlite3.Row) -> Country:
        return Country.model_validate(dict(row))

    def create(self, country: Country) -> Country:
        country = Country.model_validate(country)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO countries (country_name, capital, population, area) VALUES (?, ?, ?, ?)",
                    (country.country_name, country.capital, country.population, country.area),
                )
        except sqlite3.IntegrityError as exc:
            raise CountryAlreadyExistsError("A country with this name already exists") from exc
        return country

    def read_all(self) -> list[Country]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT country_name, capital, population, area FROM countries ORDER BY rowid"
            ).fetchall()
        return [self._row_to_country(row) for row in rows]

    def read(self, country_name: str) -> Country:
        country_name = normalize_name(country_name)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT country_name, capital, population, area FROM countries WHERE country_name = ?",
                (country_name,),
            ).fetchone()
        if row is None:
            raise CountryNotFoundError("Country not found")
        return self._row_to_country(row)

    def update(self, country_name: str, details: CountryDetails) -> Country:
        country_name = normalize_name(country_name)
        details = CountryDetails.model_validate(details)
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE countries SET capital = ?, population = ?, area = ? WHERE country_name = ?",
                (details.capital, details.population, details.area, country_name),
            )
            if cursor.rowcount == 0:
                raise CountryNotFoundError("Country not found")
        return Country(country_name=country_name, **details.model_dump())

    def delete(self, country_name: str) -> None:
        country_name = normalize_name(country_name)
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM countries WHERE country_name = ?", (country_name,))
            if cursor.rowcount == 0:
                raise CountryNotFoundError("Country not found")

    def import_countries(self, countries: list[Country], provenance: ScrapeProvenance) -> None:
        """All rows and provenance commit together; user-created rows remain intact."""
        countries = [Country.model_validate(country) for country in countries]
        if len({country.country_name for country in countries}) != len(countries):
            raise ValueError("Scrape contains duplicate natural keys")
        if provenance.record_count != len(countries):
            raise ValueError("Provenance count does not match the imported rows")
        with self._connect() as connection:
            connection.executemany(
                """INSERT INTO countries (country_name, capital, population, area) VALUES (?, ?, ?, ?)
                   ON CONFLICT(country_name) DO UPDATE SET
                   capital = excluded.capital, population = excluded.population, area = excluded.area""",
                [(c.country_name, c.capital, c.population, c.area) for c in countries],
            )
            connection.execute(
                "INSERT INTO pipeline_runs (source_url, scraped_at, source_sha256, record_count) VALUES (?, ?, ?, ?)",
                (
                    provenance.source_url,
                    provenance.scraped_at,
                    provenance.source_sha256,
                    provenance.record_count,
                ),
            )

    def latest_provenance(self) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT source_url, scraped_at, source_sha256, record_count FROM pipeline_runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
