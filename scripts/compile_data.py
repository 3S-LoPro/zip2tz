"""
Compile packaged lookup data for zip2info.

Timezone mappings are preserved from the existing generated module.
Coordinates are merged from multiple sources (in priority order):
  1. GeoNames US postal codes (CC BY 4.0)
  2. U.S. Census ZCTA gazetteer centroids (public domain)
  3. Manual overrides in data/coordinate_overrides.json
  4. 3-digit ZIP prefix centroid fallback from higher-confidence matches

Usage:
    python scripts/compile_data.py
"""

from __future__ import annotations

import ast
import io
import json
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src" / "zip2info"
LEGACY_DATA = ROOT / "src" / "zip2tz" / "_data.py"
OUTPUT = SRC_DIR / "_data.py"
OVERRIDES_PATH = ROOT / "data" / "coordinate_overrides.json"

GEONAMES_US_ZIP_URL = "https://download.geonames.org/export/zip/US.zip"
CENSUS_ZCTA_GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/Gaz_zcta_national.zip"
)


def _load_legacy_timezone_data() -> tuple[tuple[str, ...], dict[int, int]]:
    source = LEGACY_DATA if LEGACY_DATA.exists() else OUTPUT
    if not source.exists():
        raise FileNotFoundError(
            f"No timezone source found at {LEGACY_DATA} or {OUTPUT}"
        )

    module = ast.parse(source.read_text(encoding="utf-8"))
    timezones: tuple[str, ...] | None = None
    zip_tz: dict[int, int] | None = None
    zip_info: dict[int, tuple[int, float, float]] | None = None

    def _set_from_target(name: str, value_node: ast.expr) -> None:
        nonlocal timezones, zip_tz, zip_info
        if name == "TIMEZONES":
            timezones = ast.literal_eval(value_node)
        elif name == "ZIP_TZ":
            zip_tz = ast.literal_eval(value_node)
        elif name == "ZIP_INFO":
            zip_info = ast.literal_eval(value_node)

    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _set_from_target(target.id, node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                _set_from_target(node.target.id, node.value)

    if zip_tz is None and zip_info is not None:
        zip_tz = {zip_code: value[0] for zip_code, value in zip_info.items()}

    if timezones is None or zip_tz is None:
        raise ValueError(f"Could not parse TIMEZONES and ZIP_TZ/ZIP_INFO from {source}")

    return timezones, zip_tz


def _load_existing_coordinate_data() -> dict[str, tuple[float, float]]:
    if not OUTPUT.exists():
        return {}

    module = ast.parse(OUTPUT.read_text(encoding="utf-8"))
    zip_info: dict[int, tuple[int, float, float]] | None = None
    coordinates: tuple[tuple[float, float], ...] | None = None
    zip_coord: dict[int, int] | None = None

    def _set_from_target(name: str, value_node: ast.expr) -> None:
        nonlocal zip_info, coordinates, zip_coord
        if name == "ZIP_INFO":
            zip_info = ast.literal_eval(value_node)
        elif name == "COORDINATES":
            coordinates = ast.literal_eval(value_node)
        elif name == "ZIP_COORD":
            zip_coord = ast.literal_eval(value_node)

    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _set_from_target(target.id, node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                _set_from_target(node.target.id, node.value)

    if zip_info is not None:
        return {
            _zip_to_geoid(zip_code): (latitude, longitude)
            for zip_code, (_, latitude, longitude) in zip_info.items()
        }

    if coordinates is not None and zip_coord is not None:
        return {
            _zip_to_geoid(zip_code): coordinates[coord_idx]
            for zip_code, coord_idx in zip_coord.items()
        }

    return {}


def _download_postal_coordinates() -> dict[str, tuple[float, float]]:
    print(f"Downloading GeoNames US postal data from {GEONAMES_US_ZIP_URL}...")
    with urllib.request.urlopen(GEONAMES_US_ZIP_URL, timeout=120) as response:
        payload = response.read()

    coordinates: dict[str, tuple[float, float]] = {}
    accuracy_rank: dict[str, int] = {}

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        data_names = [
            name
            for name in archive.namelist()
            if name.endswith(".txt") and not name.lower().startswith("readme")
        ]
        if not data_names:
            raise ValueError("GeoNames archive did not contain a data .txt file")
        raw = archive.read(data_names[0]).decode("utf-8")

    for line in raw.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 11:
            continue
        postal_code = parts[1].strip()
        if len(postal_code) != 5 or not postal_code.isdigit():
            continue
        lat = float(parts[9])
        lon = float(parts[10])
        accuracy = int(parts[11]) if parts[11].isdigit() else 1
        existing_rank = accuracy_rank.get(postal_code)
        if existing_rank is None or accuracy >= existing_rank:
            coordinates[postal_code] = (lat, lon)
            accuracy_rank[postal_code] = accuracy

    print(f"Loaded {len(coordinates)} GeoNames postal coordinate records")
    return coordinates


def _download_census_zcta_coordinates() -> dict[str, tuple[float, float]]:
    print(f"Downloading Census ZCTA gazetteer from {CENSUS_ZCTA_GAZETTEER_URL}...")
    with urllib.request.urlopen(CENSUS_ZCTA_GAZETTEER_URL, timeout=120) as response:
        payload = response.read()

    coordinates: dict[str, tuple[float, float]] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        data_names = [name for name in archive.namelist() if name.endswith(".txt")]
        if not data_names:
            raise ValueError("Census archive did not contain a .txt file")
        raw = archive.read(data_names[0]).decode("utf-8")

    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if parts[0] == "GEOID":
            continue
        geoid = parts[0].strip()
        if len(geoid) != 5 or not geoid.isdigit():
            continue
        # Gazetteer layout: GEOID, POP10, HU10, ALAND, AWATER, ALAND_SQMI, AWATER_SQMI,
        # INTPTLAT, INTPTLONG
        coordinates[geoid] = (float(parts[7]), float(parts[8]))

    print(f"Loaded {len(coordinates)} Census ZCTA coordinate records")
    return coordinates


def _load_manual_overrides() -> dict[str, tuple[float, float]]:
    if not OVERRIDES_PATH.exists():
        return {}
    raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    overrides: dict[str, tuple[float, float]] = {}
    for geoid, value in raw.items():
        lat, lon = value
        overrides[str(geoid).zfill(5)] = (float(lat), float(lon))
    print(f"Loaded {len(overrides)} manual coordinate overrides")
    return overrides


def _zip_to_geoid(zip_int: int) -> str:
    return str(zip_int).zfill(5)


def _merge_postal_coordinates(
    *sources: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """Later sources override earlier ones (GeoNames should win over Census)."""
    merged: dict[str, tuple[float, float]] = {}
    for source in sources:
        merged.update(source)
    return merged


def _apply_prefix_fallback(
    zip_tz: dict[int, int],
    postal_coords: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    prefix_coords: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for zip_int in zip_tz:
        geoid = _zip_to_geoid(zip_int)
        coord = postal_coords.get(geoid)
        if coord is not None:
            prefix_coords[geoid[:3]].append(coord)

    filled = 0
    for zip_int in zip_tz:
        geoid = _zip_to_geoid(zip_int)
        if geoid in postal_coords:
            continue
        candidates = prefix_coords.get(geoid[:3])
        if not candidates:
            continue
        postal_coords[geoid] = (mean(lat for lat, _ in candidates), mean(lon for _, lon in candidates))
        filled += 1

    if filled:
        print(f"Filled {filled} ZIP codes via 3-digit prefix centroid fallback")
    return postal_coords


def _build_zip_info(
    zip_tz: dict[int, int],
    postal_coords: dict[str, tuple[float, float]],
) -> dict[int, tuple[int, float, float]]:
    zip_info: dict[int, tuple[int, float, float]] = {}
    for zip_int in sorted(zip_tz):
        geoid = _zip_to_geoid(zip_int)
        coord = postal_coords.get(geoid)
        if coord is None:
            continue
        latitude, longitude = coord
        zip_info[zip_int] = (zip_tz[zip_int], latitude, longitude)

    return zip_info


def _format_tuple_lines(values: tuple[str, ...], indent: str = "    ") -> str:
    lines = [f"{indent}{value!r}," for value in values]
    return "\n".join(lines)


def _format_dict_entries(mapping: dict[int, int], indent: str = "    ") -> str:
    lines = [f"{indent}{key}: {value}," for key, value in sorted(mapping.items())]
    return "\n".join(lines)


def _format_zip_info_entries(
    zip_info: dict[int, tuple[int, float, float]],
    indent: str = "    ",
) -> str:
    lines = [
        f"{indent}{zip_code}: ({tz_idx}, {latitude}, {longitude}),"
        for zip_code, (tz_idx, latitude, longitude) in sorted(zip_info.items())
    ]
    return "\n".join(lines)


def _write_data_module(
    timezones: tuple[str, ...],
    zip_info: dict[int, tuple[int, float, float]],
    total_zip_count: int,
) -> None:
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    matched = len(zip_info)
    total = total_zip_count
    content = f'''"""
Auto-generated lookup data for zip2info.
Do not edit manually - regenerate with: python scripts/compile_data.py

Timezone data is preserved from the prior zip2tz dataset.
Coordinates merge GeoNames (CC BY 4.0), Census ZCTA centroids (public domain),
manual overrides, and 3-digit ZIP prefix fallback where needed.
Coordinate coverage: {matched}/{total} ZIP codes with timezone mappings.
"""

# Timezone strings indexed by ID
TIMEZONES: tuple[str, ...] = (
{_format_tuple_lines(timezones)}
)

# Zip code (as int) -> (timezone index, latitude, longitude)
ZIP_INFO: dict[int, tuple[int, float, float]] = {{
{_format_zip_info_entries(zip_info)}
}}
'''
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


def main() -> int:
    timezones, zip_tz = _load_legacy_timezone_data()
    try:
        postal_coords = _merge_postal_coordinates(
            _download_census_zcta_coordinates(),
            _download_postal_coordinates(),
            _load_manual_overrides(),
        )
    except Exception as exc:
        postal_coords = _load_existing_coordinate_data()
        if not postal_coords:
            raise
        print(f"Warning: failed to download fresh coordinate sources, using existing generated coordinates: {exc}")

    postal_coords = _apply_prefix_fallback(zip_tz, postal_coords)
    zip_info = _build_zip_info(zip_tz, postal_coords)
    missing = len(zip_tz) - len(zip_info)
    if missing:
        print(f"Warning: {missing} ZIP codes still lack coordinates")
    _write_data_module(timezones, zip_info, len(zip_tz))
    return 0


if __name__ == "__main__":
    sys.exit(main())
