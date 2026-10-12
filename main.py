"""Run: python -m uvicorn main:app --host 127.0.0.1 --port 8000."""

from country_atlas.api import create_app

app = create_app()
