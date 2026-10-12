"""Build a portable handoff ZIP containing code, docs, and prepared capstone outputs."""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_DIRECTORIES = {
    ".venv",
    ".cache",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "tmp",
    "output",
}
EXCLUDED_NAMES = {".DS_Store", ".env"}


def package() -> Path:
    output = ROOT / "output" / "country-atlas.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or set(relative.parts) & EXCLUDED_DIRECTORIES:
                continue
            if path.name in EXCLUDED_NAMES or path.suffix in {".pyc", ".log"}:
                continue
            archive.write(path, Path("country-atlas") / relative)
    print(f"Created {output} ({output.stat().st_size:,} bytes)")
    return output


if __name__ == "__main__":
    package()
