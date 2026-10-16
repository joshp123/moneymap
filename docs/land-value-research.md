Written by AI on 2026.10.16 by model claude opus 5.5 (research subagent). Not yet acted on: GDP first, land value later.

# Land value within a circle: what data exists

**[V]** = the agent saw the data or download page. **[I]** = inferred.

## Short answer

- No open dataset gives the value of land alone (without buildings) per grid cell, globally or across Europe.
- The global and European grids that exist measure buildings and infrastructure, not land. They spread a national total using population, night-time lights or land cover.
- Real land values exist only country by country, mostly as prices per m² for zones, not totals.
- The Netherlands has the best ready-made input: the official tax value of every home (WOZ, land plus building) on a 100 m grid.

## Four meanings of "land value"

For scale, Dutch national accounts for 2025 [V] (CBS table 85953ENG): all land €2.72 trn, of which farmland €0.20 trn; homes as buildings €1.55 trn; other buildings €0.58 trn.

1. **Land only:** German Bodenrichtwert, Danish grundværdi, US FHFA estimates.
2. **Property value (land plus building):** Dutch WOZ; French DVF ("valeur foncière" is the full sale price).
3. **Farmland price:** € per hectare.
4. **Buildings and infrastructure (produced capital):** rebuild cost. Excludes land by definition.

## Global and European sources

- **LitPop** (ETH) [V]: buildings and equipment value, 2014, USD, ~1 km, 224 countries. Night lights × population. 11 GB, CC BY 4.0. https://doi.org/10.3929/ethz-b-000331316
- **GEM Global Exposure Model 2026** [V]: rebuild cost of buildings, ~1 km, csv.gz. CC BY-NC-SA 4.0; 1 km files may need a licence request. https://github.com/gem/global_exposure_model
- **Paprotny 2025** (PIK) [V]: GDP and net fixed assets, ~1 km, 1850–2100. 12.3 GB, CC BY 4.0. https://doi.org/10.5281/zenodo.14892500
- **HANZE v2** (Europe, 42 countries) [V]: fixed assets at 100 m, to 2020. ~260 MB GeoTIFF per year, CC BY 4.0. Regional GDP × wealth-to-GDP ratio per sector; housing spread by population. https://doi.org/10.5281/zenodo.6783202
- **World Bank Changing Wealth of Nations 2024** [V]: national only. Urban land is assumed to be 24% of produced capital.
- **Eurostat national balance sheets** (nama_10_nfa_bs, N211N) [V]: total land value for 9 countries only (AT, CZ, DE, EE, FI, FR, NL, SE, SK). Germany €7.65 trn (2024), France €8.65 trn (2025), Netherlands €2.46 trn (2024).
- **Eurostat farmland prices** (apri_lprc) [V]: € per hectare by NUTS2, 2024, 22 countries; Germany, Belgium and Italy missing.
- **JRC Mapadomo** [V]: house prices and stock by NUTS3, 2000–2020, under maintenance. Too coarse for a 3 km circle. https://data.jrc.ec.europa.eu/collection/id-00467
- **Lepetit et al. 2023** [V]: scraped rents and prices on a 1 km grid for 192 cities.

## National sources

- **Netherlands, CBS 100 m and 500 m grids** [V]
  - Fields: `aantal_woningen` (homes) and `gemiddelde_woz_waarde_woning` (average WOZ, € thousands). Example: a central Amsterdam cell in 2023 has 3,015 homes at €492k.
  - 2023 complete; 2024 WOZ still empty in the API.
  - 76 MB zip (100 m, 2023), 19 MB (500 m). Also via PDOK OGC API. Free with credit to CBS.
  - Privacy suppression costs little: 99.9% of homes near Haarlem and 99.6% in rural Drenthe sit in cells with a WOZ value.
  - Homes only: no offices, shops or industry.
  - https://www.cbs.nl/nl-nl/dossier/nederland-regionaal/geografische-data/kaart-van-100-meter-bij-100-meter-met-statistieken
- **Netherlands, land share** [V]: not published; WOZ register not open; CBS leaves "land beneath dwellings" empty. Nationally land is roughly half of building property value [I]. The share varies a lot: CBS median WOZ per m² floor space 2025 [V] is €3,320 nationally, €7,100 Amsterdam, €1,600 Pekela. With rebuild cost ~€1,500–2,000/m², land is ~70% of value in Amsterdam and ~0% in Pekela [I].
- **Netherlands, farmland** (Kadaster with Wageningen, quarterly, by province) [V]: €108,500/ha average in Q2 2026; €72,700 Fryslân to €215,800 Flevoland. CC0.
- **Germany, BORIS Bodenrichtwerte** [V]: official land-only €/m² by zone. Bulk open data for Berlin, Hamburg, Hessen, NRW, Niedersachsen, Brandenburg, Mecklenburg-Vorpommern, Sachsen-Anhalt (mostly dl-de/by-2.0). Not open for Bayern, Baden-Württemberg, Rheinland-Pfalz, Schleswig-Holstein, Saarland (third-party summary; BORIS-D and Brandenburg checked). Prices, not totals.
- **Denmark, grundværdi** [V]: official land-only valuations; full data needs a Datafordeler access request.
- **England, MHCLG land value estimates 2023** (March 2026) [V]: £/ha for a typical residential site with planning permission, per local authority. OGL, 172 KB xlsx. Cannot be multiplied by area [I].
- **France, DVF** [V]: every property sale 2014–2025, geocoded, open. Land plus buildings; only plot sales give land prices.
- **US, FHFA** (Davis, Larson, Oliner, Shui) [V]: land value per acre and land share by tract, ZIP and county; single-family homes; updated June 2024. https://www.fhfa.gov/research/papers/wp1901

## Assessment

1. **No grid of total land value exists.** Global grids are building value spread by proxies; they mostly repeat population and night lights and miss price differences (Amsterdam and Heerlen homes count about the same) [I].
2. **Closest defensible options:**
   - (a) Property value, labelled "land and buildings". Best where data exists.
   - (b) Land = property value × land share. One national share is wrong in city and countryside alike. Better: property value minus rebuild cost of floor space (the appraisers' method), using BAG floor areas and an assumed rebuild cost [I].
   - (c) Average price per m² (German zones). Honest but does not answer "how much".
   - (d) HANZE buildings and infrastructure value across Europe. Consistent but not land, and largely repeats GDP.
3. **Netherlands:** value of homes in the circle works exactly like the population sum: per 100 m cell, homes × average WOZ. A few hundred thousand cells, a few MB of tiles [I]. Add farmland as farmland area × provincial €/ha for rural circles. Missing: non-residential property and the land/building split.

## Shortlist

1. **Netherlands: value of homes (land and buildings) from the CBS 100 m grid**, optionally with a land estimate by the rebuild-cost method. Caveat: homes only; WOZ lags the market by about a year.
2. **Europe: HANZE buildings and infrastructure value at 100 m** (or Paprotny ~1 km global), labelled as such. Caveat: modelled from GDP and population; excludes land.
3. **Germany add-on: average land price per m² from BORIS** where published. Caveat: patchy; prices, not totals.

## Worldwide method

Written by AI on 2026.10.16 by model claude opus 5.5. **[V]** = the agent saw the data or computed it from the data. **[I]** = inference.

### Short answer

- A worldwide land-value grid (buildings excluded) can be built the same way as the GDP grid: official national totals, then a within-country split fitted to official land valuations.
- Official land figures cover 57% of world GDP: 24% complete, 33% households only. Elsewhere the total is modelled, typically within a factor of 1.5.
- Tested on New South Wales, a split by population with a city-size term put 86% of land value in the right council area and got the four big regions within 1%.

### National totals

- **OECD Table 9B** ([data explorer](https://data-explorer.oecd.org/vis?df[ag]=OECD.SDD.NAD&df[id]=DSD_NASEC10@DF_TABLE9B), free SDMX API) [V]:
  - Total land, all sectors, 2023–2025: Australia, Austria, Canada, Czechia, Estonia, Finland, France, Germany, Japan, Korea, Netherlands, Slovakia, Sweden, UK. Mexico and Croatia also report, but their figures (0.24× and 0.39× GDP) look partial. These 16 produce 24% of world GDP.
  - Household land only: 13 more, including the US ($29.3 trn in 2024, 1.0× GDP), Italy, Spain and Poland: another 33% of world GDP.
  - Where both exist, households own 31–84% of all land (median 63%).
- **Taiwan** publishes land in its [national wealth statistics](https://ws.dgbas.gov.tw/Download.ashx?n=MjAyNOaWsOiBnueovyhFbmdsaXNoKS5wZGY%3D&u=LzAwMS9VcGxvYWQvNDY0L3JlbGZpbGUvMTA4NTQvMjM2MTk2LzIwMjTmlrDogZ7nqL8oZW5nbGlzaCkucGRm): about NT$134 trn in 2024, roughly 5.5× GDP [V].
- **Land ÷ GDP** [V]: Finland 0.76, Czechia 1.14, Sweden 1.70, Germany 1.77, Canada 1.96, Netherlands 2.19, Japan 2.38, UK 2.46, France 2.90, Australia 3.87, Korea 4.75. Land is 23–71% of land plus buildings (median 43%, Mexico excluded).
- **US check**: BEA researchers put private US land at $24.1 trn in 2015, 1.3× GDP ([Wentland et al. 2023](https://www.bea.gov/sites/default/files/papers/BEA-WP2023-4.pdf)); [Larson 2015](https://www.bea.gov/sites/default/files/papers/WP2015-3.pdf) has $23 trn for 2009 including federal land [V]. Household land ÷ 0.63 gives $46 trn for 2024, 1.6× GDP [I].
- **World Bank CWON 2024 is unusable for land** [V]. It fixes urban land at 24% of produced capital and values farmland as capitalised rent. For 2020 the two together come to 11–70% of official land in 13 of 16 countries (Korea 11%, UK 18%, France 26%). It puts US farmland at $0.18 trn, while USDA puts US cropland at $6,020 an acre ([2026 summary](https://release.nass.usda.gov/reports/land0726.pdf)).
- **Countries that publish nothing** (China, India, Brazil, Russia, Indonesia, Switzerland and others; 43% of world GDP) [V]: across 12 publishers, one land ÷ GDP ratio misses by a factor of 1.67 in leave-one-out tests. Adding GDP per head and the share of people in million-plus cities brings this to 1.52. GDP per head extrapolates badly to poorer countries: that model puts China at 0.54× GDP, which is not credible [I].
- **World total** [I]: about $170–230 trn, 1.5–2.0× world GDP. This agrees with [Savills](https://www.savills.com/insight-and-opinion/savills-news/381209/world-s-real-estate-worth-$393.3-trillion-and-is-the-world-s-largest-store-of-wealth) ($393 trn of real estate in 2025) times a land share near 45%.
- No published worldwide land-value grid or global urban land-price dataset was found [V].

### Within-country split: NSW test

- NSW Valuer General land-only values at 1 July 2024: A$2.98 trn across 128 council areas, CC BY 4.0 ([report](https://www.nsw.gov.au/sites/default/files/noindex/2025-01/Report%20on%20land%20values%20at%201%20July%202024.pdf), [bulk data](https://data.nsw.gov.au/data/dataset/http-www-valuergeneral-nsw-gov-au-land-value-summaries-lv-php)) [V].
- The project's GHSL population and Kummu GDP grids were summed into ABS council boundaries ([ABS map service](https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/LGA/MapServer)) and each weighting compared with the valuations [V]:

| Weighting | Value in the wrong council area | Wrong at four-region level |
| --- | --- | --- |
| Population | 16.5% | 8.6% |
| GDP | 17.1% | 6.0% |
| Population × (population density within ~40 km)^0.25, plus 5% spread by area | 14.3% | 0.9% |

- The exponent 0.25 matches urban economics: land prices at city centres rise with city population at an elasticity of about 0.3 ([Combes, Duranton and Gobillon 2019](https://faculty.wharton.upenn.edu/wp-content/uploads/2012/11/UrbanCost.pdf), summarised in [Duranton and Puga 2020](https://pubs.aeaweb.org/doi/pdfplus/10.1257/jep.34.3.3)) [V].
- GDP is a worse weight than population. Kummu GDP per head is up to 5× higher in Sydney than inland; land value per resident is not [V].
- The remaining misses are local [V]: Woollahra, a rich harbour suburb, 3.5× too low; Blacktown 1.5× too high; Sydney CBD 13% low; farm districts (Moree Plains) too low and the outback (Bourke) too high, because the 5% farmland placeholder ignores crops. Likely fixes: office land from GHSL non-residential built-up area, and farmland from crop area × price [I].
- The parameters were fitted on NSW, so NSW is calibration, not validation.

### Recommended method

1. **National land totals**, 2024, in US dollars at market exchange rates (asset values, unlike GDP, are not converted at PPP) [I]. Use official land where published, scaled from its year to 2024 by nominal GDP. Use household land ÷ 0.63 for the 13 household-only countries. Elsewhere use GDP × one ratio fitted on the official countries, adjusted for each country's urban concentration with the same population-access term as step 3, scored by leave-one-out. Cross-check China and India against [WID](https://wid.world/bulk_download) housing and farmland wealth, which draws on national sources for both.
2. **Farmland**: crop area from SPAM 2020 × farmland price (Eurostat by NUTS 2 region, USDA by state, Kadaster for the Netherlands; elsewhere WID farmland value ÷ crop area). Subtract from the national total.
3. **Urban land**: spread the remainder by population × (population density within 40 km)^0.25. Add office land from GHSL non-residential built-up area only if it beats the plain version on held-out data.
4. **Tiles**: store land value as a third float32 plane in the existing 120 × 120 tiles; the circle sum works as for GDP [I].

### Data to download

| Data | Use | Size | Licence |
| --- | --- | --- | --- |
| OECD Table 9B land; World Bank GDP | National totals | API, kilobytes | Free |
| [DGBAS 2024 national wealth](https://ws.dgbas.gov.tw/Download.ashx?n=MjAyNOaWsOiBnueovyhFbmdsaXNoKS5wZGY%3D&u=LzAwMS9VcGxvYWQvNDY0L3JlbGZpbGUvMTA4NTQvMjM2MTk2LzIwMjTmlrDogZ7nqL8oZW5nbGlzaCkucGRm) | Taiwan | PDF | Free |
| [SPAM 2020 physical area, all crops](https://digital-atlas.s3.amazonaws.com/cdh/data/mapspam2020-v2r2/cog/spam2020-physical_area-all.tif) ([record](https://doi.org/10.7910/DVN/SWPENT)) | Farmland area | 65 MB | CC BY 4.0 |
| [Eurostat apri_lprc](https://ec.europa.eu/eurostat/databrowser/view/apri_lprc/default/table); [USDA land values](https://release.nass.usda.gov/reports/land0726.pdf) | Farmland price | Small | Free; US public domain |
| [GHS-BUILT-S non-residential, 2025, 30″](https://human-settlement.emergency.copernicus.eu/ghs_buS2023.php) | Office land test | 37 MB | CC BY 4.0 |
| [WID country files](https://wid.world/bulk_download) (China, India) | Cross-check | 25–70 MB each | Free |
| Already in the project: Kummu GDP, GHSL population | Weights | — | CC BY 4.0 |
| NSW Valuer General | Calibration | 1 MB report | CC BY 4.0 |
| [BORIS NRW land values](https://www.opengeodata.nrw.de/produkte/infrastruktur_bauen_wohnen/boris/BRW) | Held-out test | 184 MB | dl-de/zero-2.0 |
| [FHFA land prices by tract](https://www.fhfa.gov/research/papers/wp1901); BEA division totals | Held-out test | Small | US public domain |
| [Japan official land prices (L01)](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-L01-v3_1.html) | Held-out test | ~2.5 MB a year | CC BY 4.0 |

### Validation plan

1. **National**: leave-one-country-out over the ~30 official totals. The median and worst errors are the accuracy for countries without official data.
2. **Within country, held out**: grid BORIS NRW (zone €/m² × zone area) and compare circle totals at 3, 10 and 30 km around Cologne, Düsseldorf, Essen and the rural Sauerland. Compare US county totals built from FHFA tract land prices, and BEA division totals by land use. Check the Tokyo and Osaka land-price gradient against the official price points.
3. **Pass mark** [I]: no more than 15% of value in the wrong council area or county, and circles of 30 km or more within 10%.

## Fable review

Written by AI on 2026.10.16 by model claude fable 5.1. Independent check of the sections above. Code: `research/land-value/{national_totals,landgrid,holdout_units,holdout_nsw,holdout_japan,holdout_us,holdout_misc,holdout_victoria,grid_nrw,holdout_nrw,summarise}.py`; test data fetched by `fetch_*.py` (subagents); outputs, logs and downloaded test data: `data/experiments/land-value/`. **[V]** = measured by this review. **[I]** = inferred.

### National totals

- Re-derived from the same OECD file [V]: 14 countries report land for the whole economy (AUS, AUT, CAN, CZE, DEU, EST, FIN, FRA, GBR, JPN, KOR, NLD, SVK, SWE). Mexico and Croatia report households only under the "total economy" label and New Zealand reports zero; all three must be dropped, not counted as reporters. The land ÷ GDP ratios above are correct.
- Households' share of all land, matched years, 14 countries: median 0.60, range 0.31 (Estonia) to 0.84 (Australia) [V]. US check: Fed household land in 2015 was $14.3 trn; BEA researchers put all private US land that year at $24.1 trn (Wentland et al. 2023), a household share of 0.59 [V]. So household ÷ 0.6 is right for the largest household-only country and within about ±30% elsewhere.
- **The model for non-reporters is wrong.** "GDP per head + big-city share" fits the 14 reporters best (leave-one-out error factor 1.46) but fails out of sample: scored on the 13 household-only countries (scaled by 0.6) it misses by a factor 2.1, and it implies land worth 0.21× GDP in India, 0.33× in Indonesia and 0.8× in China [V]. Independent figures say otherwise: India's 2019 All India Debt and Investment Survey puts land at 69% of rural and 49% of urban household assets, about 1.7× GDP [V, ratio I]; China's national balance sheet (CASS) has household wealth of ¥513 trn in 2019, mostly housing, plus ¥31.5 trn of state-owned construction land, which puts land at roughly 1.5–2.5× GDP [V, ratio I]. GDP per head extrapolates downwards into countries where land is a larger, not smaller, share of wealth.
- Use the big-city share alone (land ÷ GDP = exp(0.17 + 1.75 × share of people in cities over one million); leave-one-out factor 1.56, out-of-sample factor 1.95 with no bias) or a constant 1.9× GDP (factors 1.75 and 1.91) [V]. Big-city model: China 2.1, India 1.6, Brazil 2.6, Russia 1.8, Indonesia 1.5, Switzerland 1.6.
- World total: $226 trn (constant) to $238 trn (big-city), 2.0–2.1× world GDP [V]. The $170–230 trn above is too low at the bottom end because it under-values China and India.

### Within-country split: ten held-out tests

Official land-only values that no parameter was fitted on, against fixed cell weights summed over the same units. Score: share of the area's land value placed in the wrong unit (lower is better). All weights are fixed in advance: exponent 0.25, ~40 km density radius, mixes half and half. "GDP layer" is the site's own GDP grid (`data/gdp-v3/gdp.tif`).

| Test | population | pop × density^0.25 | GDP layer | Kummu GDP | ½ pop×density^0.25 + ½ GDP | ½ pop + ½ GDP | built volume |
|---|---|---|---|---|---|---|---|
| NSW councils (128), calibration | 16.5% | 15.4% | 20.3% | 17.0% | 16.7% | 17.4% | 26.6% |
| Japan prefectures (47), fixed-asset tax values 2025 | 19.6% | 14.2% | 14.8% | 14.9% | **12.8%** | 16.8% | 28.5% |
| Japan municipalities (1,719) | 24.1% | 19.2% | 22.0% | 20.1% | **19.1%** | 22.2% | 34.3% |
| NRW municipalities (396), Bodenrichtwerte 2026 gridded | 17.4% | 17.8% | 12.9% | **12.2%** | 14.6% | 14.3% | 19.7% |
| US states (49), Larson 2009 all land | 12.4% | 13.2% | 13.0% | **11.4%** | 12.9% | 12.4% | 15.7% |
| US counties (2,423), residential land (FHFA share × ACS value) | 35.1% | 30.8% | 29.7% | 30.9% | **28.9%** | 31.0% | 38.8% |
| Korea regions (17), national balance sheet 2025 | 18.8% | 15.6% | 17.2% | 17.2% | **15.4%** | 16.8% | 31.4% |
| Korea districts (228), assessed land prices 2025 | 24.2% | 23.0% | 22.5% | 27.2% | **21.8%** | 22.4% | 30.0% |
| British Columbia municipalities (160), 2026 roll | 17.4% | **10.7%** | 15.6% | 11.5% | 11.9% | 15.6% | 19.9% |
| Denmark municipalities (98), taxable land value 2025 | 16.1% | **13.5%** | 17.2% | 16.1% | 14.7% | 15.4% | 24.1% |
| Victoria councils (78), site value 2026 | 17.1% | 17.7% | 23.6% | **16.7%** | 19.2% | 18.8% | 19.7% |
| **Mean, ten held-out tests** | 20.2% | 17.6% | 18.9% | 17.8% | **17.1%** | 18.6% | 26.2% |

- The density term (pop × density^0.25) survives held-out testing: it beats plain population in eight of ten tests, by 3–7 points in Japan, Korea, BC and Denmark. It fails in NRW, where Düsseldorf and Cologne (2–2.5× under-predicted) and the Ruhr cities (2.5× over-predicted) have the same density but very different prices, so the GDP layer, which carries official regional GDP, does best there; and it is a point worse than population in Victoria, where it starves the wheat-belt councils [V].
- The half-and-half mix with the GDP layer is best in five tests and within 2.5 points of best in all ten; no single weight is that consistent [V]. Its weak spot is Australia, where the site's GDP layer has no official sub-state control and spreads state GDP by population and building volume (Victoria 23.6%). The exponent is not sharp: 0.35 does slightly better than 0.25 in seven tests, worse in NRW, the US states and Victoria; the range 0.15–0.5 moves scores by one or two points [V].
- Building volume, building surface and the non-residential term lose everywhere, by 3 to 20 points: land value is about price, not how much is built [V].
- **Farmland needs no term.** A cropland term (SPAM 2020 area, national farm share 2–12%) never improved a test. A plain area term helps only in the two Australian states, by 1–2 points (broadacre farming, few people); elsewhere it moves scores by at most a point either way [V]. In NSW's 71 regional councils, land value per km² rises as population density^0.8 and cropland share adds nothing once density is known: productive farmland carries more people [V]. Drop step 2 of the method above.

### Circle scale, NRW

Model ÷ official circle totals, twelve centres (eight cities, four rural), both normalised to the state total. Median absolute log error by radius [V]:

| Radius | population | GDP layer | ½ pop×density^0.25 + ½ GDP |
|---|---|---|---|
| 3 km | 0.54 | 0.34 | 0.38 |
| 5 km | 0.52 | 0.26 | 0.35 |
| 10 km | 0.35 | 0.33 | 0.34 |
| 20 km | 0.32 | 0.34 | 0.32 |
| 30 km | 0.26 | 0.27 | 0.27 |
| 50 km | 0.23 | 0.27 | 0.23 |

A log error of 0.35 is a factor 1.4. City centres are the hard case: 3 km around Cologne cathedral holds €65 bn of land by the official values; population puts 0.36× that there, the mix 0.60×. Düsseldorf is 0.37× even with the mix. Rural circles land within 0.8–1.6× at 10–30 km [V].

### Recommended method

1. **National totals** as above, with two changes: drop Mexico, Croatia and New Zealand from the reporters; replace the non-reporter model with the big-city-share model (or a constant 1.9× GDP). Household-only countries ÷ 0.6.
2. **Within each country**, cell weight = ½ × cell share of population × (population density within ~40 km)^0.25 + ½ × cell share of the site's GDP layer. Two inputs the site already has; one fixed exponent; no farmland step, no non-residential step. The density field is smooth, so compute it on a 5 arc-minute grid and interpolate [I].
3. **Accuracy to expect** [V]: 13–22% of a country's land value in the wrong municipality or district; 10 km circles within a factor 1.4 in the median; 30–50 km circles within 1.3. City-centre circles in rich cities read low by up to 2×; non-reporting countries carry a further factor of about 1.6–1.9 on the total.
4. What the model cannot see: regional price levels at equal density (Düsseldorf against Gelsenkirchen, Aspen, Nantucket, mining towns) and resort land. Only official valuations would fix that, and they exist for a handful of countries.
