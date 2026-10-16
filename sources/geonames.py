"""Written by AI on 2026.10.17 by model gpt-6.1-sol.

Build the nearest-place gazetteer from GeoNames cities15000 (CC BY 4.0).
"""

import csv
import io
import json
from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/geonames"
OUTPUT = ROOT / "data/places/cities.json"
DUMP_URL = "https://download.geonames.org/export/dump/"


def build():
    RAW.mkdir(parents=True, exist_ok=True)
    for filename in ("cities15000.zip", "countryInfo.txt"):
        destination = RAW / filename
        if not destination.exists():
            print(f"Downloading {filename}", flush=True)
            download = destination.with_suffix(destination.suffix + ".download")
            urlretrieve(DUMP_URL + filename, download)
            download.replace(destination)

    with (RAW / "countryInfo.txt").open(encoding="utf-8") as source:
        countries = {row[0]: row[4] for row in csv.reader(
            (line for line in source if not line.startswith("#")), delimiter="\t") if row}

    with ZipFile(RAW / "cities15000.zip") as archive:
        with archive.open("cities15000.txt") as contents:
            cities = [[row[1], countries[row[8]], float(row[4]), float(row[5]), int(row[14])]
                      for row in csv.reader(io.TextIOWrapper(contents, encoding="utf-8"), delimiter="\t")]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(cities, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Built {len(cities):,} places in {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
