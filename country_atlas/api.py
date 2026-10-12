"""The five required CRUD endpoints plus an analytical dashboard."""

import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from country_atlas.analytics import csv_text, scatter_png, summarize, to_dataframe
from country_atlas.database import CountryAlreadyExistsError, CountryDatabaseManager, CountryNotFoundError
from country_atlas.models import Country, CountryDetails, normalize_name
from country_atlas.settings import COUNTRY_LIMIT, DATABASE_PATH, SOURCE_URL, STATIC_PATH

# Matplotlib uses process-global state, so serialize dynamic chart rendering.
CHART_LOCK = threading.Lock()


def create_app(database_path: str | Path = DATABASE_PATH, *, read_only: bool | None = None) -> FastAPI:
    if read_only is None:
        read_only = os.environ.get("ATLAS_READ_ONLY", "0") == "1"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = CountryDatabaseManager(database_path)
        yield

    app = FastAPI(
        title="Country Atlas API",
        version="1.0.0",
        lifespan=lifespan,
        description="Country-name keyed CRUD and analytics for the first 20 entries from Scrape This Site.",
    )
    hosts = [
        host.strip()
        for host in os.environ.get("ATLAS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    ]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.middleware("http")
    async def guard_and_headers(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if read_only:
                return JSONResponse({"detail": "This demo is read-only"}, status_code=403)
            origin = request.headers.get("origin")
            expected_origin = f"{request.url.scheme}://{request.url.netloc}"
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin and origin != expected_origin
            ):
                return JSONResponse({"detail": "Cross-origin changes are not allowed"}, status_code=403)
            if request.method in {"POST", "PUT", "PATCH"}:
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    return JSONResponse({"detail": "Use application/json"}, status_code=415)
                # Measure streamed bytes instead of trusting a caller-supplied Content-Length.
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 8192:
                        return JSONResponse({"detail": "Request body exceeds 8 KB"}, status_code=413)
                request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        # Swagger uses its official CDN assets; the dashboard uses only local resources.
        if request.url.path not in {"/docs", "/redoc"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            )
        return response

    def database(request: Request) -> CountryDatabaseManager:
        return request.app.state.database

    def key(value: str) -> str:
        try:
            return normalize_name(value)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc

    @app.exception_handler(CountryNotFoundError)
    async def not_found(_request: Request, _exc: CountryNotFoundError):
        return JSONResponse({"detail": "Country not found"}, status_code=404)

    @app.exception_handler(CountryAlreadyExistsError)
    async def duplicate(_request: Request, _exc: CountryAlreadyExistsError):
        return JSONResponse({"detail": "A country with this name already exists"}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError):
        # Do not echo raw inputs: nonstandard NaN/Infinity JSON would otherwise
        # make FastAPI's error response itself fail JSON serialization.
        details = [
            {"type": error["type"], "loc": error["loc"], "msg": error["msg"]} for error in exc.errors()
        ]
        return JSONResponse({"detail": details}, status_code=422)

    @app.get("/health", tags=["System"])
    def health(request: Request):
        count = len(database(request).read_all())
        return {"status": "ok", "country_count": count, "read_only": read_only}

    @app.get("/countries", response_model=list[Country], tags=["Countries"])
    def list_countries(request: Request, q: Annotated[str | None, Query(max_length=120)] = None):
        records = database(request).read_all()
        if q:
            term = q.strip().casefold()
            records = [
                record
                for record in records
                if term in record.country_name.casefold() or term in record.capital.casefold()
            ]
        return records

    @app.get("/countries/{country_name}", response_model=Country, tags=["Countries"])
    def get_country(country_name: str, request: Request):
        return database(request).read(key(country_name))

    @app.post("/countries", response_model=Country, status_code=201, tags=["Countries"])
    def create_country(country: Country, request: Request):
        return database(request).create(country)

    @app.put("/countries/{country_name}", response_model=Country, tags=["Countries"])
    def update_country(country_name: str, details: CountryDetails, request: Request):
        return database(request).update(key(country_name), details)

    @app.delete("/countries/{country_name}", status_code=204, tags=["Countries"])
    def delete_country(country_name: str, request: Request):
        database(request).delete(key(country_name))
        return Response(status_code=204)

    @app.get("/analytics/summary", tags=["Analytics"])
    def summary(request: Request):
        return summarize(database(request).read_all())

    @app.get("/pipeline/status", tags=["System"])
    def pipeline_status(request: Request):
        manager = database(request)
        return {
            "source_url": SOURCE_URL,
            "scope": COUNTRY_LIMIT,
            "stored_count": len(manager.read_all()),
            "last_scrape": manager.latest_provenance(),
            "read_only": read_only,
            "data_note": "Educational source values, including territories; not current demographic estimates.",
        }

    @app.get("/exports/countries.csv", tags=["Exports"])
    def export_csv(request: Request):
        return Response(
            csv_text(to_dataframe(database(request).read_all())),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="exported_countries.csv"'},
        )

    @app.get("/exports/population_vs_area.png", tags=["Exports"])
    def export_chart(request: Request, log_scale: bool = False):
        with CHART_LOCK:
            content = scatter_png(to_dataframe(database(request).read_all()), log_scale=log_scale)
        return Response(
            content,
            media_type="image/png",
            headers={"Content-Disposition": 'attachment; filename="population_vs_area.png"'},
        )

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(STATIC_PATH / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")
    return app
