-- Written by AI on 2026.10.16 by model claude opus 5.5.
-- Counts bus, tram and metro/train stops per GHS-POP 30 arc-second cell from
-- Overture Maps (base/infrastructure/transit, OpenStreetMap-derived, ODbL).
-- Class mapping reproduces Tom Forth's counts. Run from the repository root:
--   nix shell nixpkgs#duckdb -c duckdb < sources/overture_stops.sql
INSTALL httpfs; LOAD httpfs;
SET s3_region='us-west-2'; SET http_timeout=120; SET http_retries=8;
COPY (
  WITH stops AS (
    SELECT (bbox.xmin + bbox.xmax) / 2 AS lon, (bbox.ymin + bbox.ymax) / 2 AS lat,
      CASE WHEN class = 'bus_stop' THEN 'bus'
           WHEN class = 'stop_position' AND source_tags['railway'] = 'tram_stop' THEN 'tram'
           WHEN class IN ('railway_station', 'railway_halt', 'subway_station') THEN 'rail' END AS mode
    FROM read_parquet('s3://overturemaps-us-west-2/release/2026-09-23.1/theme=base/type=infrastructure/*.parquet')
    WHERE subtype = 'transit'
      AND class IN ('bus_stop', 'stop_position', 'railway_station', 'railway_halt', 'subway_station'))
  SELECT floor((lon + 180.0079159313) * 120)::INTEGER AS grid_col,
         floor((89.0995831776 - lat) * 120)::INTEGER AS grid_row,
         count(*) FILTER (WHERE mode = 'bus') AS bus_stops,
         count(*) FILTER (WHERE mode = 'tram') AS tram_stops,
         count(*) FILTER (WHERE mode = 'rail') AS rail_stops
  FROM stops WHERE mode IS NOT NULL GROUP BY ALL
) TO 'data/raw/overture/stops_per_cell.parquet';
