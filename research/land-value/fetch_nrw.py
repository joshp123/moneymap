"""Fetch and prepare NRW standard land values (Bodenrichtwerte) and admin boundaries.

Written by AI on 2026.10.16 by model claude fable 5.1 subagent.

Run from the repo root:
    devenv shell -- python -I research/land-value/fetch_nrw.py

Outputs (under data/experiments/land-value/raw/nrw/):
    brw/BRW_EPSG25832_Shape.zip      statewide Bodenrichtwerte, Shapefile, EPSG:25832
    brw/extracted/                   unzipped shapefile
    brw_zones.parquet                one row per zone polygon, WKB geometry in EPSG:4326
    dvg/dvg1_EPSG25832_Shape.zip     Digitale Verwaltungsgrenzen (dvg1), Shapefile
    dvg/extracted/                   unzipped shapefiles
    dvg/dvg1_gemeinden_4326.geojson  municipalities, EPSG:4326
    dvg/dvg1_kreise_4326.geojson     districts, EPSG:4326

Downloaded files are untrusted data; this script only reads them with fiona.
"""

from __future__ import annotations

import collections
import json
import statistics
import subprocess
import sys
import zipfile
from pathlib import Path

import fiona
import fiona.transform
import numpy
import pyarrow
import pyarrow.parquet
import rasterio.enums
import rasterio.features
import rasterio.transform
import shapely
import shapely.geometry

REPO_ROOT = Path(__file__).resolve().parents[2]
NRW_RAW_DIR = REPO_ROOT / "data" / "experiments" / "land-value" / "raw" / "nrw"
BRW_DIR = NRW_RAW_DIR / "brw"
DVG_DIR = NRW_RAW_DIR / "dvg"
BRW_ZONES_PARQUET = NRW_RAW_DIR / "brw_zones.parquet"

OPENGEODATA_BRW_BASE = "https://www.opengeodata.nrw.de/produkte/infrastruktur_bauen_wohnen/boris/BRW/"
OPENGEODATA_DVG1_BASE = "https://www.opengeodata.nrw.de/produkte/geobasis/vkg/dvg/dvg1/"

DOWNLOADS = [
    (OPENGEODATA_BRW_BASE + "BRW_EPSG25832_Shape.zip", BRW_DIR / "BRW_EPSG25832_Shape.zip"),
    (OPENGEODATA_BRW_BASE + "BRW_Datenmodell.pdf", BRW_DIR / "BRW_Datenmodell.pdf"),
    (OPENGEODATA_DVG1_BASE + "dvg1_EPSG25832_Shape.zip", DVG_DIR / "dvg1_EPSG25832_Shape.zip"),
    (OPENGEODATA_DVG1_BASE + "Nutzerinformationen.pdf", DVG_DIR / "Nutzerinformationen.pdf"),
]

SOURCE_CRS = "EPSG:25832"
TARGET_CRS = "EPSG:4326"
REPROJECTION_BATCH_SIZE = 5000

# Coverage check grid: 100 m cells over the NRW bounding box in EPSG:25832.
COVERAGE_CELL_SIZE_M = 100
COVERAGE_ORIGIN_WEST_M = 280_000
COVERAGE_ORIGIN_NORTH_M = 5_821_000
COVERAGE_WIDTH_CELLS = 2_520
COVERAGE_HEIGHT_CELLS = 2_440

FIONA_TYPE_TO_ARROW_TYPE = {"str": pyarrow.string(), "int": pyarrow.int64(), "float": pyarrow.float64()}


def download_missing_files() -> None:
    for url, destination in DOWNLOADS:
        if destination.exists() and destination.stat().st_size > 0:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url}")
        subprocess.run(["curl", "-sSL", "--fail", "-o", str(destination), url], check=True)


def extract_zip_safely(zip_path: Path, extract_dir: Path) -> list[Path]:
    """Extract without letting any member path escape extract_dir."""
    if extract_dir.exists() and any(extract_dir.rglob("*.shp")):
        return sorted(extract_dir.rglob("*.shp"))
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (extract_dir / member.filename).resolve()
            if not target.is_relative_to(extract_dir.resolve()):
                raise ValueError(f"zip member escapes extract dir: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as sink:
                sink.write(source.read())
    return sorted(extract_dir.rglob("*.shp"))


def describe_layer(shapefile_path: Path) -> None:
    with fiona.open(shapefile_path) as layer:
        print(f"\n== layer {shapefile_path.name}")
        print(f"   driver={layer.driver} crs={layer.crs} features={len(layer)}")
        print(f"   geometry={layer.schema['geometry']} bounds={layer.bounds}")
        first_feature = next(iter(layer))
        print("   fields (name: type = example from first feature):")
        for field_name, field_type in layer.schema["properties"].items():
            print(f"     {field_name}: {field_type} = {first_feature.properties.get(field_name)!r}")


def parse_german_decimal(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def reproject_geometries_to_wkb(source_geometries: list) -> list[bytes]:
    reprojected = fiona.transform.transform_geom(SOURCE_CRS, TARGET_CRS, source_geometries)
    return [shapely.to_wkb(shapely.geometry.shape(geometry)) for geometry in reprojected]


def build_brw_zones_parquet(brw_shapefile: Path, parquet_path: Path) -> None:
    columns: dict[str, list] = collections.defaultdict(list)
    geometry_wkb: list[bytes | None] = []
    pending_geometries: list = []
    pending_row_indices: list[int] = []

    def flush_pending_geometries() -> None:
        for row_index, wkb in zip(pending_row_indices, reproject_geometries_to_wkb(pending_geometries)):
            geometry_wkb[row_index] = wkb
        pending_geometries.clear()
        pending_row_indices.clear()

    with fiona.open(brw_shapefile) as layer:
        property_types = {
            name: FIONA_TYPE_TO_ARROW_TYPE[field_type.split(":")[0]]
            for name, field_type in layer.schema["properties"].items()
        }
        for row_index, feature in enumerate(layer):
            properties = feature.properties
            for name in property_types:
                columns[name].append(properties.get(name))

            geometry_wkb.append(None)
            if feature.geometry is None:
                columns["area_m2"].append(None)
                columns["geometry_is_valid"].append(None)
            else:
                source_shape = shapely.geometry.shape(feature.geometry)
                columns["area_m2"].append(source_shape.area)
                columns["geometry_is_valid"].append(bool(source_shape.is_valid))
                pending_geometries.append(feature.geometry)
                pending_row_indices.append(row_index)
                if len(pending_geometries) >= REPROJECTION_BATCH_SIZE:
                    flush_pending_geometries()

            brw_eur_per_m2 = parse_german_decimal(properties.get("BRW"))
            columns["brw_eur_per_m2"].append(brw_eur_per_m2)
            columns["brw_missing_or_nonpositive"].append(brw_eur_per_m2 is None or brw_eur_per_m2 <= 0)

    if pending_geometries:
        flush_pending_geometries()
    columns["geometry"] = geometry_wkb

    arrow_types = {
        **property_types,
        "area_m2": pyarrow.float64(),
        "geometry_is_valid": pyarrow.bool_(),
        "brw_eur_per_m2": pyarrow.float64(),
        "brw_missing_or_nonpositive": pyarrow.bool_(),
        "geometry": pyarrow.binary(),
    }
    table = pyarrow.table({name: pyarrow.array(values, type=arrow_types[name]) for name, values in columns.items()})
    # No "crs" key: GeoParquet then means OGC:CRS84, which is EPSG:4326 with lon/lat axis order.
    geoparquet_metadata = {
        "version": "1.0.0",
        "primary_column": "geometry",
        "columns": {"geometry": {"encoding": "WKB", "geometry_types": ["Polygon", "MultiPolygon"]}},
    }
    table = table.replace_schema_metadata({b"geo": json.dumps(geoparquet_metadata).encode()})

    partial_path = parquet_path.with_suffix(".parquet.partial")
    pyarrow.parquet.write_table(table, partial_path, compression="zstd")
    partial_path.rename(parquet_path)


def print_breakdown(title: str, keys: list, area_m2: list, brw_eur_per_m2: list) -> None:
    rows = collections.defaultdict(lambda: {"zones": 0, "area_m2": 0.0, "value_eur": 0.0, "brw": []})
    for key, area, brw in zip(keys, area_m2, brw_eur_per_m2):
        row = rows[key or "(none)"]
        row["zones"] += 1
        row["area_m2"] += area or 0.0
        if brw is not None and brw > 0:
            row["value_eur"] += brw * (area or 0.0)
            row["brw"].append(brw)
    print(f"\n== {title}")
    print(f"   {'code':<10}{'zones':>8}{'area_km2':>12}{'area x BRW, EUR bn':>20}{'median BRW':>12}")
    for key, row in sorted(rows.items(), key=lambda item: -item[1]["area_m2"]):
        median_brw = statistics.median(row["brw"]) if row["brw"] else float("nan")
        print(
            f"   {key:<10}{row['zones']:>8}{row['area_m2'] / 1e6:>12.1f}"
            f"{row['value_eur'] / 1e9:>20.2f}{median_brw:>12.2f}"
        )
    total_area = sum(row["area_m2"] for row in rows.values())
    total_value = sum(row["value_eur"] for row in rows.values())
    print(f"   {'TOTAL':<10}{len(keys):>8}{total_area / 1e6:>12.1f}{total_value / 1e9:>20.2f}")


def report_from_parquet(parquet_path: Path) -> None:
    table = pyarrow.parquet.read_table(
        parquet_path,
        columns=[
            "STAG", "NUTA", "ENTW", "FARBE", "ERGNUTA", "BRKE",
            "area_m2", "brw_eur_per_m2", "brw_missing_or_nonpositive", "geometry_is_valid",
        ],
    )
    data = table.to_pydict()
    print(f"\n== {parquet_path.name}: rows={table.num_rows} size={parquet_path.stat().st_size / 1e6:.1f} MB")
    print("   schema:")
    for field in pyarrow.parquet.read_schema(parquet_path):
        print(f"     {field.name}: {field.type}")
    print(f"   STAG values: {dict(collections.Counter(data['STAG']))}")
    print(f"   BRKE values (1 zonal, 2 typical-location): {dict(collections.Counter(data['BRKE']))}")
    print(f"   rows with BRW missing or <= 0: {sum(data['brw_missing_or_nonpositive'])}")
    print(f"   rows with invalid geometry (EPSG:25832): {data['geometry_is_valid'].count(False)}")
    positive_brw = [value for value in data["brw_eur_per_m2"] if value is not None and value > 0]
    print(f"   BRW range: min={min(positive_brw)} median={statistics.median(positive_brw)} max={max(positive_brw)} EUR/m2")

    area_m2, brw = data["area_m2"], data["brw_eur_per_m2"]
    print_breakdown("by NUTA (type of use)", data["NUTA"], area_m2, brw)
    print_breakdown("by ENTW (development state)", data["ENTW"], area_m2, brw)
    print_breakdown("by FARBE (map colour class)", data["FARBE"], area_m2, brw)
    overlay_groups = [overlay_group_for_zone(f, e) for f, e in zip(data["FARBE"], data["ERGNUTA"])]
    print_breakdown("by overlay group (see coverage check)", overlay_groups, area_m2, brw)


def overlay_group_for_zone(farbe: str | None, ergnuta: str | None) -> str:
    """Descriptive grouping of zones by map colour class, used only for the coverage check."""
    if farbe == "4":
        return "forest"
    if farbe == "5":
        return "agri"
    if farbe == "6" or "ASB" in (ergnuta or "").split("/"):
        return "outer_bldg"
    return "inner"


def report_coverage_depth(brw_shapefile: Path, nrw_state_shapefile: Path) -> None:
    """Rasterise zones at 100 m and count how many zones cover each cell, per overlay group."""
    grid_transform = rasterio.transform.from_origin(
        COVERAGE_ORIGIN_WEST_M, COVERAGE_ORIGIN_NORTH_M, COVERAGE_CELL_SIZE_M, COVERAGE_CELL_SIZE_M
    )
    grid_shape = (COVERAGE_HEIGHT_CELLS, COVERAGE_WIDTH_CELLS)
    cell_area_km2 = (COVERAGE_CELL_SIZE_M / 1000) ** 2

    shapes_by_group = collections.defaultdict(list)
    with fiona.open(brw_shapefile) as layer:
        for feature in layer:
            group = overlay_group_for_zone(feature.properties.get("FARBE"), feature.properties.get("ERGNUTA"))
            shapes_by_group[group].append((shapely.geometry.shape(feature.geometry), 1))

    with fiona.open(nrw_state_shapefile) as layer:
        nrw_state_shape = shapely.geometry.shape(next(iter(layer)).geometry)
    nrw_mask = rasterio.features.rasterize([(nrw_state_shape, 1)], out_shape=grid_shape, transform=grid_transform)
    nrw_cells = int(nrw_mask.sum())
    print(f"\n== coverage check on a {COVERAGE_CELL_SIZE_M} m grid (cell-centre rasterisation)")
    print(f"   NRW state area (DVG1 polygon): {nrw_state_shape.area / 1e6:.1f} km2; grid cells inside: {nrw_cells * cell_area_km2:.1f} km2")
    print(f"   {'group':<12}{'covered_km2':>12}{'% of NRW':>10}{'mean_depth':>12}{'% cells depth>=2':>18}")

    depth_all_groups = numpy.zeros(grid_shape, dtype=numpy.uint16)
    for group in ("inner", "outer_bldg", "agri", "forest"):
        depth = rasterio.features.rasterize(
            shapes_by_group[group],
            out_shape=grid_shape,
            transform=grid_transform,
            merge_alg=rasterio.enums.MergeAlg.add,
            dtype="uint16",
        )
        depth_all_groups += depth
        covered = depth > 0
        covered_cells = int(covered.sum())
        print(
            f"   {group:<12}{covered_cells * cell_area_km2:>12.1f}"
            f"{100 * int((covered & (nrw_mask == 1)).sum()) / nrw_cells:>10.1f}"
            f"{depth[covered].mean():>12.2f}"
            f"{100 * int((depth >= 2).sum()) / max(covered_cells, 1):>18.1f}"
        )
    covered_any = depth_all_groups > 0
    print(f"   all zones: covered {int(covered_any.sum()) * cell_area_km2:.1f} km2, mean depth {depth_all_groups[covered_any].mean():.2f}")
    histogram = collections.Counter(numpy.minimum(depth_all_groups[covered_any], 8).tolist())
    print("   depth histogram, all zones (depth: km2; 8 means 8+): " + ", ".join(
        f"{depth}: {count * cell_area_km2:.0f}" for depth, count in sorted(histogram.items())
    ))


def convert_shapefile_to_geojson_4326(shapefile_path: Path, geojson_path: Path) -> None:
    partial_path = geojson_path.with_suffix(".geojson.partial")
    with fiona.open(shapefile_path) as source:
        schema = {"geometry": ("Polygon", "MultiPolygon"), "properties": source.schema["properties"]}
        with fiona.open(
            partial_path, "w", driver="GeoJSON", crs=TARGET_CRS, schema=schema, COORDINATE_PRECISION=7
        ) as sink:
            for feature in source:
                reprojected = fiona.transform.transform_geom(SOURCE_CRS, TARGET_CRS, feature.geometry)
                sink.write(fiona.Feature(geometry=reprojected, properties=feature.properties))
    partial_path.rename(geojson_path)
    with fiona.open(geojson_path) as written:
        print(f"   wrote {geojson_path.name}: {len(written)} features, {geojson_path.stat().st_size / 1e6:.1f} MB, bounds={written.bounds}")


def main() -> None:
    download_missing_files()

    print("\n#### Bodenrichtwerte (BRW)")
    brw_shapefiles = extract_zip_safely(BRW_DIR / "BRW_EPSG25832_Shape.zip", BRW_DIR / "extracted")
    if len(brw_shapefiles) != 1:
        sys.exit(f"expected exactly one BRW shapefile, found: {brw_shapefiles}")
    brw_shapefile = brw_shapefiles[0]
    describe_layer(brw_shapefile)
    if not BRW_ZONES_PARQUET.exists():
        build_brw_zones_parquet(brw_shapefile, BRW_ZONES_PARQUET)
    report_from_parquet(BRW_ZONES_PARQUET)

    print("\n#### Digitale Verwaltungsgrenzen (DVG1)")
    dvg_shapefiles = extract_zip_safely(DVG_DIR / "dvg1_EPSG25832_Shape.zip", DVG_DIR / "extracted")
    for shapefile in dvg_shapefiles:
        describe_layer(shapefile)
    shapefile_by_stem = {path.stem: path for path in dvg_shapefiles}
    convert_shapefile_to_geojson_4326(shapefile_by_stem["dvg1gem_nw"], DVG_DIR / "dvg1_gemeinden_4326.geojson")
    convert_shapefile_to_geojson_4326(shapefile_by_stem["dvg1krs_nw"], DVG_DIR / "dvg1_kreise_4326.geojson")

    report_coverage_depth(brw_shapefile, shapefile_by_stem["dvg1bld_nw"])


if __name__ == "__main__":
    main()
