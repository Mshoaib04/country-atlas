"""DataFrame analytics, spreadsheet-safe exports, and presentation-ready scatter plots."""

import io
import os

from country_atlas.models import Country
from country_atlas.settings import PROJECT_ROOT

# Headless generation works on servers and doesn't need a GUI event loop.
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache" / "matplotlib"))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

COLUMNS = ["country_name", "capital", "population", "area"]


def to_dataframe(countries: list[Country]) -> pd.DataFrame:
    return pd.DataFrame([country.model_dump() for country in countries], columns=COLUMNS).astype(
        {"population": "int64", "area": "float64"}
    )


def csv_text(frame: pd.DataFrame) -> str:
    safe = frame[COLUMNS].copy()
    # Free-form CRUD values must not become formulas when opened in spreadsheet software.
    for column in ["country_name", "capital"]:
        safe[column] = safe[column].map(
            lambda value: (
                "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value
            )
        )
    return safe.to_csv(index=False, lineterminator="\n")


def summarize(countries: list[Country]) -> dict:
    if not countries:
        return {
            "count": 0,
            "total_population": 0,
            "total_area": 0,
            "median_density": 0,
            "densest_country": None,
            "largest_country": None,
            "most_populous_country": None,
            "population_area_correlation": None,
            "zero_population_count": 0,
        }
    frame = to_dataframe(countries)
    density = frame.population / frame.area
    correlation = (
        frame.population.corr(frame.area)
        if len(frame) > 1 and frame.population.nunique() > 1 and frame.area.nunique() > 1
        else None
    )
    return {
        "count": len(frame),
        "total_population": int(frame.population.sum()),
        "total_area": float(frame.area.sum()),
        "median_density": round(float(density.median()), 2),
        "densest_country": str(frame.loc[density.idxmax(), "country_name"]),
        "largest_country": str(frame.loc[frame.area.idxmax(), "country_name"]),
        "most_populous_country": str(frame.loc[frame.population.idxmax(), "country_name"]),
        "population_area_correlation": round(float(correlation), 4)
        if correlation is not None and np.isfinite(correlation)
        else None,
        "zero_population_count": int((frame.population == 0).sum()),
    }


def _short_number(value: float, _position=None) -> str:
    if abs(value) >= 1e6:
        return f"{value / 1e6:g}M"
    if abs(value) >= 1e3:
        return f"{value / 1e3:g}k"
    return f"{value:g}"


def scatter_png(frame: pd.DataFrame, *, log_scale: bool = False) -> bytes:
    """Keep the required plot linear; the optional log view uses log1p to include zero."""
    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.edgecolor": "#d5dcde",
            "axes.labelcolor": "#53636b",
            "xtick.color": "#53636b",
            "ytick.color": "#53636b",
        }
    ):
        fig, ax = plt.subplots(figsize=(12.5, 7.5), dpi=160)
        fig.patch.set_facecolor("#f7f9f8")
        ax.set_facecolor("#ffffff")
        fig.subplots_adjust(left=0.10, right=0.90, top=0.77, bottom=0.18)
        fig.text(0.10, 0.93, "COUNTRY ATLAS  /  DATA EXPLORER", fontsize=10, color="#087f73", weight="bold")
        fig.text(0.10, 0.86, "Population vs. area", fontsize=28, color="#142b36", weight="bold")
        subtitle = f"{len(frame)} source entries · Color shows population density · " + (
            "Log1p view includes zero population" if log_scale else "Linear axes · Source values preserved"
        )
        fig.text(0.10, 0.815, subtitle, fontsize=10, color="#66757c")
        if not frame.empty:
            density = frame.population / frame.area
            points = ax.scatter(
                frame.population,
                frame.area,
                c=np.log1p(density),
                cmap="viridis",
                s=105,
                alpha=0.90,
                edgecolors="white",
                linewidths=1.1,
                zorder=3,
                clip_on=False,
            )
            colorbar = fig.colorbar(points, ax=ax, pad=0.035, fraction=0.025)
            colorbar.set_label("Density color: ln(1 + people/km²)", fontsize=9)
            # Sparse outlier labels keep the linear plot legible.
            labels = set(frame.nlargest(2, "population").index) | set(frame.nlargest(2, "area").index)
            for index in labels:
                row = frame.loc[index]
                right_aligned = row.population > frame.population.max() * 0.80
                ax.annotate(
                    row.country_name,
                    (row.population, row.area),
                    xytext=(-8 if right_aligned else 8, 8),
                    textcoords="offset points",
                    ha="right" if right_aligned else "left",
                    fontsize=9,
                    color="#253e48",
                )
        else:
            ax.text(0.5, 0.5, "No countries to plot", transform=ax.transAxes, ha="center", color="#66757c")
        if log_scale:
            ax.set_xscale("function", functions=(np.log1p, np.expm1))
            ax.set_yscale("function", functions=(np.log1p, np.expm1))
            ax.set_xlim(left=0)
            ax.set_ylim(bottom=0)
            if not frame.empty:
                ax.set_xticks(
                    [
                        tick
                        for tick in [0, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9]
                        if tick <= frame.population.max() * 1.15
                    ]
                )
                ax.set_yticks(
                    [tick for tick in [0, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7] if tick <= frame.area.max() * 1.15]
                )
        else:
            ax.set_xlim(left=0)
            ax.set_ylim(bottom=0)
        ax.xaxis.set_major_formatter(FuncFormatter(_short_number))
        ax.yaxis.set_major_formatter(FuncFormatter(_short_number))
        ax.set_xlabel("Population (people)", labelpad=12)
        ax.set_ylabel("Area (sq. km)", labelpad=12)
        ax.grid(True, alpha=0.40, color="#d7e0e1", linestyle="--", zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
        fig.text(
            0.10,
            0.065,
            "SOURCE  scrapethissite.com/pages/simple/ · Educational source data; not current demographic estimates.",
            fontsize=8,
            color="#6b7c82",
        )
        stream = io.BytesIO()
        fig.savefig(stream, format="png", facecolor=fig.get_facecolor())
        plt.close(fig)
    return stream.getvalue()
