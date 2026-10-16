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
