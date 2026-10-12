#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Create the environment first: python3 -m venv .venv"
  echo "Then install packages: .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi
atlas_database_path="$(.venv/bin/python -c 'from country_atlas.settings import DATABASE_PATH; print(DATABASE_PATH)')"
if [ ! -f "$atlas_database_path" ]; then
  echo "Run the pipeline first: .venv/bin/python run_pipeline.py"
  exit 1
fi
# Recognize this application before trying to launch another copy on its port.
if .venv/bin/python - <<'PY'
import json
import sys
from urllib.error import URLError
from urllib.request import urlopen

try:
    with urlopen("http://127.0.0.1:8000/openapi.json", timeout=2) as response:
        specification = json.load(response)
except (URLError, OSError, ValueError):
    sys.exit(1)

sys.exit(0 if specification.get("info", {}).get("title") == "Country Atlas API" else 1)
PY
then
  echo "Country Atlas is already running. Open the links below; no second server is needed."
  echo "Dashboard: http://127.0.0.1:8000"
  echo "API playground: http://127.0.0.1:8000/docs"
  echo "Restart the existing server before changing database or read-only configuration."
  exit 0
fi
echo "Country Atlas dashboard: http://127.0.0.1:8000"
echo "API playground: http://127.0.0.1:8000/docs"
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
