-- Written by AI on 2026.10.16 by model claude opus 5.5.
-- Counts Overture Maps places (points of interest) per GHS-POP 30 arc-second cell,
-- release 2026-09-23.1. Licence: CDLA Permissive 2.0 (Meta, Microsoft, PinMeTo
-- sources) and Apache 2.0; cite "Overture Maps Foundation, overturemaps.org".
-- Permanently closed places are dropped. workplace_* counts places whose primary
-- category sits in an office, business-service, industrial, government-office or
-- research branch of the Overture taxonomy; agricultural services are excluded.
-- Run from the repository root:
--   nix shell nixpkgs#duckdb -c duckdb < scripts/extract_places.sql
INSTALL httpfs; LOAD httpfs;
SET s3_region='us-west-2'; SET http_timeout=120; SET http_retries=8;
CREATE TEMP TABLE workplace_category AS
  SELECT "primary" AS category
  FROM read_csv('https://docs.overturemaps.org/taxonomy/2026-09-23.0/taxonomy.csv', header=true, all_varchar=true)
  WHERE array_to_string(string_split(taxonomy, ' > ')[1:2], ' > ') IN (
      'services_and_business > b2b_service',
      'services_and_business > corporate_or_business_office',
      'services_and_business > design_service',
      'services_and_business > financial_service',
      'services_and_business > industrial_facility_or_service',
      'services_and_business > legal_service',
      'services_and_business > media_service',
      'services_and_business > professional_service',
      'services_and_business > real_estate_service',
      'services_and_business > technical_service',
      'services_and_business > telecommunications_service',
      'community_and_government > government_office',
      'education > education_office',
      'education > research_institute')
    AND taxonomy NOT LIKE 'services_and_business > b2b_service > b2b_agriculture_service%';
COPY (
  WITH places AS (
    SELECT bbox.xmin AS lon, bbox.ymin AS lat, confidence,  -- points: xmin = xmax
           taxonomy."primary" IN (SELECT category FROM workplace_category) AS workplace
    FROM read_parquet('s3://overturemaps-us-west-2/release/2026-09-23.1/theme=places/type=place/*.parquet')
    WHERE operating_status IS DISTINCT FROM 'permanently_closed')
  SELECT floor((lon + 180.0079159313) * 120)::INTEGER AS grid_col,
         floor((89.0995831776 - lat) * 120)::INTEGER AS grid_row,
         count(*) AS places,
         count(*) FILTER (WHERE confidence >= 0.5) AS places_conf50,
         count(*) FILTER (WHERE workplace) AS workplace_places,
         count(*) FILTER (WHERE workplace AND confidence >= 0.5) AS workplace_places_conf50
  FROM places GROUP BY ALL
) TO 'data/raw/overture/places_per_cell.parquet';
