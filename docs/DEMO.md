# Country Atlas: demonstration guide

Start the application with `bash start.sh` and open http://127.0.0.1:8000.

## A three-minute walkthrough

1. **Explain the assignment.** “I built a complete data path from a live HTML source to SQLite, a FastAPI microservice, an independent requests client, and exported analytics. The dashboard makes the result easier to explore.”
2. **Show the overview.** Point to the stored count, population, area, and median density. Explain that these totals describe only the selected sample.
3. **Explore the scatter plot.** Switch between Linear and Log1p. Click Antarctica to show that zero population is preserved instead of silently dropped. Explain that Log1p is `ln(1 + x)`, allowing zero.
4. **Compare countries.** Compare Bangladesh with Australia. Discuss population density as population divided by area and how it adds meaning beyond absolute size.
5. **Demonstrate CRUD.** Add “Demo Republic,” edit its capital, inspect its detail card, then delete it. Deleting the demonstration entry returns the dataset to 20 entries.
6. **Prove provenance.** Open Data pipeline. Show the original source link, scrape timestamp, original scope, stored count, and SHA-256 checksum.
7. **Show the contract and files.** Open API playground. Point out the required five routes, then show `client.py`, the printed DataFrame, `exported_countries.csv`, and the required linear `population_vs_area.png`.

The screenshots in `docs/images/` were captured from an isolated database; browser-test mutations do not change your prepared data.

## Likely viva questions

**Why is country name the primary key?** The brief requires a natural identifier. A unique, non-null country name is enforced by SQLite, with duplicate creation mapped to HTTP 409. Names are immutable in the update contract.

**Why use a class for database operations?** `CountryDatabaseManager` encapsulates schema creation, CRUD, transaction boundaries, and provenance. The API and scraper use the same class instead of duplicating SQL.

**What happens if scraping fails?** The scraper fails clearly if the source is unreachable, fields are missing, numeric conversion fails, or fewer than 20 records are available. All rows are validated before an atomic database import. It does not substitute fake data.

**What happens when you run it twice?** The scraper imports only the first 20 source entries using an upsert. Existing keys are updated, duplicates are avoided, and manual additions remain intact. Each successful import records its provenance.

**Does the client connect to the database?** No. `client.py` uses requests to fetch `GET /countries`, validates the JSON, creates and prints a Pandas DataFrame, and exports its CSV and Matplotlib charts.

**Why are some entries territories?** The assignment defines the scope by the source page's first 20 entries. Keeping the page's order and values is more faithful than substituting a different list.

**Why not call these current statistics?** A fresh scrape tells us when the HTML was retrieved, not when its demographic values were measured. The dashboard explicitly identifies them as educational source data.

**What does the checksum prove?** It identifies the exact fetched HTML bytes. Together with the timestamp and preserved source snapshot, it makes the import traceable. It does not independently establish that the source values are correct.

**How did you verify it?** Deterministic tests cover parsing, natural-key CRUD, persistence, transactions, validation, Unicode, exports, and real HTTP integration. Chromium checks cover dashboard navigation, chart interaction, comparison, downloads, CRUD, duplicate errors, safe rendering, and mobile behavior.

**Can GitHub Pages host everything?** GitHub Pages can host static files, but this project needs a running Python API and persistent SQLite storage. Publishing the repository and deploying the application are different steps.
