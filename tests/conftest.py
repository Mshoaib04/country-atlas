from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from country_atlas.api import create_app
from country_atlas.database import CountryDatabaseManager
from country_atlas.models import Country


@pytest.fixture
def sample_countries():
    return [
        Country(country_name="Åland", capital="Mariehamn", population=26711, area=1580.0),
        Country(country_name="Antarctica", capital="None", population=0, area=14_000_000.0),
        Country(country_name="Bangladesh", capital="Dhaka", population=156118464, area=144000.0),
    ]


@pytest.fixture
def manager(tmp_path, sample_countries):
    database = CountryDatabaseManager(tmp_path / "countries.db")
    for country in sample_countries:
        database.create(country)
    return database


@pytest.fixture
def client(manager):
    with TestClient(create_app(manager.database_path)) as session:
        yield session


@pytest.fixture
def source_html():
    return (Path(__file__).parent / "fixtures" / "first_20_countries.html").read_text(encoding="utf-8")
