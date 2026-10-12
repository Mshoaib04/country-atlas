"""Paths anchored to the project, independent of the shell's current directory."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.environ.get("ATLAS_DATABASE_PATH", PROJECT_ROOT / "countries.db"))
STATIC_PATH = PROJECT_ROOT / "static"
SOURCE_URL = "https://www.scrapethissite.com/pages/simple/"
COUNTRY_LIMIT = 20
