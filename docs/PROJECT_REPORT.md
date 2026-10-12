# Country Atlas: implementation and verification report

Verified on **12 October 2026**. The brief's suggested time budget was treated as guidance; the implementation covers all six technical requirements and adds a working analytical dashboard.

## Requirement completion

| Brief step | Result | Evidence |
| --- | --- | --- |
| 1. Virtual environment | Complete | `.venv/`; installed runtime and development dependencies; `pip check` passed |
| 2. Web scraping | Complete | Live HTTPS scrape; exactly the first 20 `.country` entries; all four required fields converted to validated types |
| 3. SQLite + OOP CRUD | Complete | `countries.db`; `CountryDatabaseManager`; `country_name TEXT NOT NULL PRIMARY KEY`; insert/read/update/delete methods |
| 4. FastAPI microservice | Complete | All five required routes with string-based country identifiers; API playground at `/docs` |
| 5. Standalone client + CSV | Complete | `client.py` requests `GET /countries`, prints the Pandas DataFrame, writes `exported_countries.csv` |
| 6. Scatter visualization | Complete | `population_vs_area.png`; population on X, area on Y; title, labeled axes, gridlines; 2000 × 1200 PNG |

The one-command pipeline was executed using an actual temporary FastAPI server and a real HTTP request from the client. No direct database shortcut substitutes for the required client step.

## Prepared data and outputs

The initial SQLite database contains **20 entries**, starting with **Andorra** and ending with **Belgium**, in source order. **Åland** retains its accent. **Antarctica** retains zero population and the source's literal `None` capital.

| Sample statistic | Value |
| --- | --- |
| Combined population | 304,224,742 people |
| Combined area | 26,888,881 km² |
| Median population density | 98.72 people/km² |
| Densest entry | Bangladesh |
| Largest entry by area | Antarctica |
| Population–area Pearson correlation | −0.0300 |

These statistics describe the selected educational source sample. They do not represent the entire world or current demographic estimates. Correlation is descriptive and does not imply causation.

Generated outputs are `exported_countries.csv`, the required `population_vs_area.png`, bonus `population_vs_area_log.png`, `analytics_summary.json`, and `pipeline_manifest.json`. The source HTML is preserved locally in `data/source.html` and checksum-named archives under `data/snapshots/`, with its SHA-256 checksum and scrape time recorded in SQLite.

## Additional project value

The dashboard gives the pipeline a distinct visual identity and supports interactive chart points, country field notes, CRUD dialogs, search, sorting, side-by-side comparisons, density rankings, and downloads. The pipeline screen explains source provenance and each data-processing stage. All dashboard resources are local; no remote fonts or third-party JavaScript are needed.

The optional Log1p chart explicitly uses `ln(1 + x)` for its axes. This retains zero-population entries. The required exported scatter remains on linear axes.

Repeat imports use upserts and commit validated source rows and provenance together. Original rows are refreshed without deleting user-added entries. A captured first-20 HTML fixture supports offline tests; the production scraper always uses the live source.

## Verification

| Check | Result |
| --- | --- |
| `python -m pytest -q` | **37 passed; no warnings** |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed; all Python files formatted |
| `python -m pip check` | No broken requirements |
| JavaScript syntax check | Passed |
| Real HTTP export pipeline | Passed; 20 DataFrame rows and required files generated |
| Chromium dashboard checks | Passed; no JavaScript errors |
| Desktop layout | Visually reviewed at 1440 × 1080 |
| Mobile layout | Visually reviewed at 390 × 844; no page-level horizontal overflow |
| Matplotlib outputs | Both PNGs opened and visually reviewed |

Automated tests cover the first-20 limit, source order, missing fields, numeric conversion, Unicode, zero population, natural-key persistence, duplicate conflicts, atomic rollback, all CRUD routes, input validation, NaN/Infinity handling, CSV structure, PNG validity, empty datasets, optional read-only mode, request size limits, cross-origin mutation checks, safe literal SQL values, and real HTTP integration.

Browser checks exercise chart scale switching, point details, zero-population comparison, CSV download, provenance, search, sorting, create/update/delete, duplicate errors, literal text rendering, mobile navigation, and mobile dialogs. Browser edits use a temporary database rather than the prepared project database.

The test toolkit uses Starlette's supported `httpx2` TestClient integration. All tests pass without warnings. The application's runtime client uses `requests` as required.

## Publication readiness

The review findings were addressed before preparing the repository: area values smaller than `0.000001` km² and URL dot-segment names are rejected; the launcher honors the configured database path; source archives survive failed refreshes; and the latest-source pointer updates only after a successful import. Regression tests cover these cases, including rejection of a corrupted archive.

The exact dependency lockfile requires Python 3.12 or later and matches the installed verification environment.

## CodeGuard review

The three always-apply rules were checked: no credentials are embedded; SHA-256 is used only for source integrity identification; no certificates or private keys are embedded, and outbound HTTPS uses normal certificate verification. No custom cryptography is introduced.

Python, JavaScript, HTML, SQL, and shell guidance was reviewed alongside applicable API, storage, injection, client-side web, input validation, serialization, dependency, and configuration guidance. The implementation uses parameterized SQL, bounded strict input schemas, unknown-field rejection, DOM `textContent`, spreadsheet-safe free-form CSV strings, host validation, cross-origin mutation rejection, security response headers, localhost binding, and an optional public read-only mode.

The remaining deployment boundary is explicit: local single-user editing is unauthenticated. A public demonstration should use read-only mode and HTTPS. Public write access would require a separately designed authentication/authorization layer and hosting configuration. No public service has been deployed.

## Ready for presentation

Use `bash start.sh` to start the dashboard and open http://127.0.0.1:8000. The [demo guide](DEMO.md) includes a three-minute walkthrough and viva questions. Screenshots are in `docs/images/`.

The repository includes code, test fixtures, screenshots, and sample analytical outputs. Local virtual environments, browser/tool caches, generated databases, source archives, and machine-specific manifests are excluded from Git. Recreate local state using the README's setup and pipeline commands. No public application hosting is included.
