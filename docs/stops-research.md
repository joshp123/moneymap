Written by AI on 2026.10.16 by model claude opus 5.5 (research subagent).

# Transit stops like Tom Forth's

Source: Overture Maps release 2026-09-23.1, theme `base`, type `infrastructure`, subtype `transit` (OpenStreetMap-derived, ODbL; attribution "© OpenStreetMap contributors, Overture Maps Foundation"). Overture has no tram class, so trams come from the raw OSM tag.

Mapping that reproduces Tom's counts:
- bus: `class = 'bus_stop'`
- tram: `class = 'stop_position' AND source_tags['railway'] = 'tram_stop'`
- metro and train: `class IN ('railway_station', 'railway_halt', 'subway_station')`, all geometries (polygons needed to match Amsterdam)

Exact point-in-circle counts against Tom's API (ours/Tom):

| Circle | Bus | Tram | Rail |
|---|---|---|---|
| Amsterdam 1 km | 39/40 | 33/33 | 6/6 |
| Amsterdam 5 km | 702/696 | 349/345 | 34/33 |
| Berlin 3 km | 411/405 | 135/135 | 60/59 |
| Manchester 3 km | 727/734 | 37/37 | 7/7 |
| London 3 km | 861/877 | 0/0 | 63/63 |
| Paris 3 km | 969/982 | 0/0 | 137/138 |
| New York 3 km | 640/632 | 0/0 | 68/66 |
| Tokyo 3 km | 565/567 | 0/0 | 112/111 |
| Utrecht 3 km | 314/317 | 0/20 | 14/5 |

Utrecht differs because its tram stops were retagged in OSM on 18 May 2026 (`railway=tram_stop` → `railway=stop` + `light_rail=yes`), after Tom's data. Rules using `light_rail` break Berlin's S-Bahn, which Tom counts as rail, so the simple rule stays.

Per-cell counts summed inside Amsterdam 5 km: 684/352/33 against Tom's 696/345/33; 1 km shows cell rounding (38/37/3 against 40/33/6), as population does.

Extraction: `sources/overture_stops.sql` reads about 3.2 GB of the 13.8 GB infrastructure files (157.6 million features); about 20 minutes at 3 MB/s.

Licence note [inferred, not legal advice]: publicly served stop tiles are probably an ODbL derived database and should be offered under ODbL; the population and GDP layers are separate data.
