"""One validated contract shared by the scraper, database, API, and client."""

import unicodedata
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_POPULATION = 9_007_199_254_740_991  # Also exactly representable in browser JavaScript.
MIN_AREA = 0.000001  # One square meter in square kilometers; matches the dashboard form.
Name = Annotated[str, Field(min_length=1, max_length=120)]


def normalize_name(value: str) -> str:
    """Trim and NFC-normalize without losing accents or punctuation."""
    value = unicodedata.normalize("NFC", value.strip())
    if not value or len(value) > 120:
        raise ValueError("Name must contain between 1 and 120 characters")
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("Control characters are not allowed")
    if "/" in value:
        raise ValueError("Country names cannot contain slashes")
    if value in {".", ".."}:
        raise ValueError("Country names cannot be URL dot segments")
    return value


class CountryDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    capital: Annotated[str, Field(min_length=1, max_length=160)]
    population: Annotated[int, Field(strict=True, ge=0, le=MAX_POPULATION)]
    area: Annotated[float, Field(strict=True, ge=MIN_AREA, le=1e12, allow_inf_nan=False)]

    @field_validator("capital")
    @classmethod
    def validate_capital(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value)
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("Control characters are not allowed")
        return value


class Country(CountryDetails):
    country_name: Name

    @field_validator("country_name")
    @classmethod
    def validate_country_name(cls, value: str) -> str:
        return normalize_name(value)


class ScrapeProvenance(BaseModel):
    source_url: str
    scraped_at: str
    source_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    record_count: int
