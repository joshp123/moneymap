Written by AI on 2026.10.16 by model claude opus 5.5.

# How the numbers are calculated

[moneymap](https://moneymap.jjpcodes.com) adds up what lies inside a circle drawn anywhere on Earth: residents, public transport stops, GDP, and the value of land and buildings. This page explains where each number comes from, how we tested it and where we know it is wrong. It is for anyone who wants to check the numbers or improve them.

## How this was made

moneymap was built in about a day, on 16 October 2026. Josh decided what to build and made the main choices. AI agents did almost all of the research, code and writing: Claude Opus 5.5 planned the work and researched the methods, GPT-6.1 Sol wrote most of the code, and Claude Fable 5.1 reviewed the land value method independently. The project was vibe-coded: AI wrote nearly all of it, and people checked little of the code or data by hand. Claude Opus 5.5 wrote this page and Claude Fable 5.1 checked it against the code and data.

We publish the method, the test results and the known errors so that others can check the work and improve it. Treat every figure as a rough estimate.

## Summary

| Number | What it counts | Year and unit | Main sources | How good it is |
|---|---|---|---|---|
| Population | People who live in the circle | 2025; people | GHS-POP, European Commission | Matches Tom Forth's site, which uses the same GHSL 2025 population data, within 0.8% |
| Stops | Bus, tram, metro and train stops | Mapped by September 2026; stops | OpenStreetMap, via Overture Maps | Bus stops within 3% of Tom Forth's counts in the test circles; tram and rail differ in some areas |
| GDP | Value of what is produced in the circle | 2024; international dollars (PPP) | National and official regional GDP, spread by jobs, buildings and business locations | In tests, 5% to 25% of GDP lands in the wrong small region; business districts in much of Asia are probably too low |
| Land value | Market value of land, without buildings | 2024; US dollars | National balance sheets, or a model | In tests, 12% to 29% of value lands in the wrong municipality or county; rich city centres can read 2 to 3 times too low |
| Building value | Value of homes and other buildings, after wear | 2024; US dollars | National balance sheets, or a model | In tests, 13% to 23% lands in the wrong area; dense business districts read too high |
| Property value | Land plus buildings | 2024; US dollars | As above | In tests, 10% to 26% lands in the wrong area |

## Reading a result

**The circle.** The site divides the world into cells of 30 arc-seconds (1/120 of a degree). A cell is about 0.93 km from north to south, and narrower from east to west away from the equator: 0.58 km in London. A circle's total is the sum of every cell whose centre lies within the chosen distance of the clicked point, measured along the Earth's surface. The table under the map gives the same sums within each whole kilometre. The radius runs from 3 to 100 km. Tom Forth's site has the same 3 km minimum, because small city-centre circles are likely to be wrong. Circles of 1 and 2 km appear only as rows of that table; the 1 and 2 km figures on this page are such rows from a 3 km circle.

**Units.** GDP uses purchasing power parity (PPP): each currency is converted at the rate that buys the same goods and services as a US dollar buys in the US. The result is called international dollars. Kummu's release, the source of every country's GDP total, labels its unit 2021 international dollars. But its 2024 totals agree within 1% to 2% with the World Bank's GDP at PPP in current 2024 international dollars, so the figures behave like 2024 PPP dollars:

| Area | moneymap GDP, $ trillion | World Bank, 2024 PPP, current prices | World Bank, 2024 PPP, 2021 prices |
|---|---:|---:|---:|
| United States | 29.57 | 29.30 | 25.74 |
| China | 38.93 | 38.24 | 33.59 |
| World | 196.88 | 199.8 | 174.2 |

The site's US total is 1.5% above BEA's official 2024 figure. Land and buildings are assets, so they use 2024 US dollars at market exchange rates. In poorer countries GDP at PPP is much higher than at market rates, so the ratio of property value to GDP cannot be compared between rich and poor countries.

**GDP per head** divides the circle's GDP by the people who live in it. GDP is placed where people work and population where they live, so business districts have very high GDP per head. The 1 km circle around Meta's head office has 2,254 residents and $50.9 billion of GDP.

**Precision.** The site shows money to one decimal place of a million, billion or trillion, and people to the person. The estimates are far less precise than that.

**Billionaires.** For scale, property value mode names up to three billionaires whose net worth is nearest the circle's total (between a quarter and ten times it), with a key of what each owns. The ladder runs from Rihanna ($1.0 billion) through Oprah, Steven Spielberg, James Dyson, Peter Thiel, Michael Bloomberg, Bill Gates and Mark Zuckerberg to Elon Musk ($908.5 billion), using each person's Forbes real-time profile on 16 October 2026. The list is in `worker/index.js`.

## How we tested the numbers

Four kinds of test recur below.

**Totals add up.** Every build stops unless each country total, and each official regional total, comes back out of the grid to within the rounding of the stored numbers (1 part in 10 million). It then reads every stored tile back and checks the sum again.

**Hold-out tests.** Take an area whose official total we know, such as a US state. Pretend we know only that total. Spread it over the grid with our rule, add up the cells inside each smaller official area within it, such as counties, and compare with the official figures we held back. We report two scores:

- *Wrong-area share:* the share of the total that ends up in the wrong smaller area: half the sum of the absolute differences between predicted and official figures, divided by the official total. 0% is perfect. For GDP, spreading by population alone scores between 10% and 40%.
- *Median absolute log ratio:* for each smaller area, take |ln(predicted ÷ official)|; report the median across areas. It gives the typical area's error as a factor: 0.10 is about 10% out, 0.41 a factor of 1.5, 0.69 a factor of 2.

For land and buildings, each test first scales our total over the valued areas to the official total, so it compares shares only.

**Independent figures.** We compare with Tom Forth's site, with lower bounds built from big companies' accounts, and with official land and property valuations that no rule was fitted to.

**The website matches the grids.** `checks/circles.py` asks the site for 36 named circles and compares every total and every kilometre row with sums taken directly from the source grids, without reading the stored tiles. All 36 match, both on a local copy of the site and on the live site after the current version was deployed.

These tests have limits:

- The hold-out tests chose between a few rules fixed in advance, with simple weights such as halves and thirds. So their scores flatter the chosen rule a little. The land rule's two parameters were set on New South Wales, which is therefore not among its tests.
- Hold-out tests spread a large area's total over areas of thousands to millions of people. The site often spreads a county's or a province's total over cells 1 km wide. At the scale of a 1 to 3 km circle, only the company bounds and a few named places test the result.
- The land, building and property tests compare shares within an area. National totals have their own tests.

## Population

Code: `layers/population.py`.

**What it measures.** People who live in each cell in 2025, from GHS-POP R2023A, the European Commission Joint Research Centre's population grid at 30 arc-seconds. GHS-POP is itself a model: it spreads census counts over mapped built-up land. moneymap uses it unchanged. The world total is 8,191,988,536 people.

**How we checked it.** Tom Forth's site uses the same GHSL 2025 population data. In nine circles moneymap is between 0.01% and 0.74% higher:

| Circle | Radius, km | moneymap | Tom Forth | Difference |
|---|---:|---:|---:|---:|
| Amsterdam | 3 | 291,889 | 291,863 | +0.01% |
| Amsterdam | 5 | 561,613 | 561,541 | +0.01% |
| Lagos | 10 | 3,017,217 | 3,016,975 | +0.01% |
| London | 20 | 9,008,206 | 8,994,827 | +0.15% |
| Luxembourg | 25 | 680,034 | 678,096 | +0.29% |
| Tokyo | 30 | 20,997,094 | 20,983,001 | +0.07% |
| Rotterdam | 50 | 6,177,783 | 6,154,432 | +0.38% |
| Tromsø | 50 | 83,268 | 82,659 | +0.74% |
| Paris | 100 | 14,240,092 | 14,216,474 | +0.17% |

The example loading code on Tom Forth's page, written for an older and finer GHS-POP grid, skips cells with fewer than one person and rounds every other cell down to a whole number. If his live database was loaded the same way, which we have not confirmed, his totals would be slightly lower, most of all in thinly settled places such as Tromsø.

**Known problems.**

- *Svalbard.* A 10 km circle around Longyearbyen, where most of Svalbard's people live, returns no one. Tom Forth's live site, asked for the same circle, also returns no one. GHS-POP puts Svalbard's population, about 2,800 people, around Sveagruva, a former mining settlement about 45 km to the south-east. Svalbard's GDP and property value follow the same cells.
- *Small or changing places.* Tom Forth notes that this GHS-POP release is less accurate for small areas, especially where population has changed fast.
- *Residents only.* Business districts have few residents, so a city-centre circle's population says little about how many people are there by day.

## Bus, tram, metro and train stops

Code: `sources/overture_stops.sql`, `layers/transit_stops.py`.

**What it measures.** Stops in OpenStreetMap, the map built by volunteers, as published by Overture Maps in its release of 23 September 2026.

**How it is calculated.** Three kinds of stop, chosen to reproduce Tom Forth's counts:

- bus: `bus_stop`;
- tram: stop positions tagged `railway=tram_stop` in the original OpenStreetMap data, because Overture has no tram class;
- metro and train: `railway_station`, `railway_halt` and `subway_station`, including stations mapped as areas, which are placed at the centre of their bounding box.

Each stop counts in the cell that contains it. The data holds 4,167,514 bus, 51,083 tram and 138,265 metro and train stops, and the stored layers hold exactly these. As Tom Forth explains, a bus or tram stop is usually mapped once for each direction of travel, and a metro or train station once.

**How we checked it.** Counts against Tom Forth's site, shown as moneymap / Tom Forth. The 3 km rows and Amsterdam 1 km count each stop at its exact position. The site itself counts whole cells, shown for Amsterdam 5 km and Rotterdam 50 km.

| Circle | Bus | Tram | Metro and train |
|---|---:|---:|---:|
| Amsterdam 1 km | 39 / 40 | 33 / 33 | 6 / 6 |
| Berlin 3 km | 411 / 405 | 135 / 135 | 60 / 59 |
| London 3 km | 861 / 877 | 0 / 0 | 63 / 63 |
| Manchester 3 km | 727 / 734 | 37 / 37 | 7 / 7 |
| New York 3 km | 640 / 632 | 0 / 0 | 68 / 66 |
| Paris 3 km | 969 / 982 | 0 / 0 | 137 / 138 |
| Tokyo 3 km | 565 / 567 | 0 / 0 | 112 / 111 |
| Utrecht 3 km | 314 / 317 | 0 / 20 | 14 / 5 |
| Amsterdam 5 km, site | 684 / 696 | 352 / 345 | 33 / 33 |
| Rotterdam 50 km, site | 11,645 / 11,622 | 900 / 1,036 | 238 / 180 |

Counting whole cells changes small circles: by cells, Amsterdam 1 km has 38 bus, 37 tram and 3 metro and train stops.

**Known problems.**

- *Utrecht's trams.* According to the [stop research](stops-research.md), on 18 May 2026, after Tom Forth's extract, OpenStreetMap editors retagged Utrecht's tram stops from `railway=tram_stop` to `railway=stop` with `light_rail=yes`. moneymap therefore finds no tram stops in Utrecht. Rules based on the new tags miscount Berlin's S-Bahn, which Tom Forth counts as rail, so we kept the simple rule.
- *Rotterdam 50 km* has 136 fewer tram stops than Tom Forth's site and 58 more metro and train stops. Utrecht lies inside this circle.
- *Coverage.* OpenStreetMap is uneven. Tom Forth notes that many stops are missing, especially outside Europe, and that rarely used and heritage stops are included.

## GDP

Code: `layers/gdp/`, `sources/regional_gdp.py`, `sources/lodes_jobs.py`, `sources/us_industry_gdp.py`, `sources/overture_places.sql`.

**What it measures.** Gross domestic product (GDP) is the value of goods and services produced, less the goods and services used up in producing them. Economists call this value added. For a company it is roughly pay plus profit plus depreciation. moneymap places GDP at workplaces rather than at workers' homes. Year: 2024. Unit: international dollars at purchasing power parity (see Units above).

### How it is calculated

**Step 1: country totals.** Each country's total is the sum of Kummu et al.'s 2024 GDP grid over that country. Kummu's grid places GDP where people live (for 2024 it uses 2025 population), so we keep only its totals: national totals everywhere, and provincial totals outside the countries in step 2. The world total is $196.88 trillion.

**Step 2: official regions.** In 34 countries, official statistics give GDP for smaller regions. We split each country's total in proportion to the official figures:

```
region GDP = country GDP × official GDP of the region ÷ official GDP of all the country's regions
```

Only the official shares are used, so currency, price year and PPP conversion do not affect them.

| Country | Regions | Official source | Year |
|---|---|---|---|
| United States | 3,115 counties (BEA publishes some small Virginia cities, and Hawaii's Kalawao County, combined with a neighbouring county) | Bureau of Economic Analysis (BEA) county GDP | 2024 |
| United Kingdom | 42,619 small statistical areas of a few hundred to a few thousand residents: lower layer super output areas (LSOAs) in England and Wales, data zones in Scotland, super output areas in Northern Ireland | Office for National Statistics (ONS) small-area gross value added (GVA, which is GDP before taxes and subsidies on products) | 2023 |
| Netherlands | 52 COROP-plus regions, the Dutch statistical regions, each roughly a city or district and its surroundings | Statistics Netherlands (CBS) | 2023 |
| 26 other EU countries, and Albania, Montenegro, North Macedonia, Serbia and Turkey | 1,252 NUTS3 regions, the smallest standard statistical regions in the EU, mostly of 150,000 to 800,000 people | Eurostat, on GISCO 2024 boundaries | 2023 |

France's five overseas departments keep their own Kummu totals. Everywhere else, the regions are Kummu's provinces or states where it reports them (31 in China, 36 in India, 47 in Japan), or the whole country (as for Taiwan). These 1,276 regions hold 67% of world GDP.

A cell belongs to the region that contains its centre. Occupied coastal cells that fall outside every boundary go to the nearest region, so no GDP is lost.

**Step 3: within each region.** Each region uses the first of these three rules that it can (`layers/gdp/allocation.py`).

1. **US counties: each industry by its well-paid jobs.** BEA splits each county's GDP into 20 industries. Each industry's GDP is spread over the county's cells in proportion to that industry's jobs, weighted by how many of the jobs pay well:

   ```
   cell GDP = Σ over industries ( county GDP in the industry
                                  × cell's weighted jobs in the industry ÷ county's weighted jobs in the industry )
   weighted jobs = jobs in the industry × share of the block's private-sector jobs that pay over $3,333 a month
   ```

   The jobs come from LODES, the US Census Bureau's count of jobs by the census block where people work. Each block counts in the cell that holds its internal point. LODES gives pay bands for each block but not for each industry, so each private industry uses the block's private-sector share of well-paid jobs. Government jobs are all jobs minus private jobs, with their own count of well-paid jobs; this keeps public schools and hospitals in government, as BEA counts them. Releases are for 2023, except Alaska (2016) and Michigan (2021). The grid holds 150,944,613 jobs, of which 86,331,982 pay over $3,333 a month.

   BEA withholds 12,883 of its 62,300 county-industry figures to protect confidential data. Where BEA's published sub-totals fix a withheld figure exactly, we solve it. The rest share what is left of their published parent total, in proportion to county jobs in the industry × state GDP per job in that industry. These estimates carry 2.5% of US GDP. County totals are unchanged. Industry GDP with no jobs in its county (0.08% of US GDP) follows all the county's well-paid jobs.

2. **Regions with good business coverage: thirds.** Where a region has at least 3.9 workplace places per 1,000 residents, and has both residents and building weight, its GDP is split into equal thirds, spread by residents, by building weight and by workplace places:

   ```
   cell GDP = region GDP × ( ⅓ × cell residents ÷ region residents
                           + ⅓ × cell building weight ÷ region building weight
                           + ⅓ × cell workplace places ÷ region workplace places )
   ```

   Workplace places are businesses in Overture Maps in office, business-service, industrial, government-office and research categories: 13.9 million worldwide. 3.9 per 1,000 is the lowest coverage among the countries we tested (Brazil). This rule covers 16,757 regions holding 21% of world GDP: nearly all of Germany, Italy, Spain, the Netherlands, Canada and Australia, most of France, and parts of the UK, Turkey, Brazil and Mexico. It covers almost none of China, India, Japan, Korea, Indonesia, Russia or Taiwan.

3. **All other regions: halves.** Half by residents, half by building weight. This covers 63% of world GDP. A region with only one of the two uses that one. A region with neither in any of its cells puts all its GDP in the cell that contains its centre point. These are 13,311 UK small areas, mostly too small to contain a cell centre, holding $844 billion, about a fifth of UK GDP.

**Building weight.** For each cell, non-residential building volume squared, divided by non-residential building footprint, from GHSL's 2025 built-up grids. This equals volume × average height, so a tower counts for more than a warehouse of the same volume (`layers/gdp/building_weight.py`). The GHSL building grid is offset by 0.8 of a cell from the population grid, so each building cell is shared between the two population cells it overlaps.

### How we checked it

**Business locations.** The thirds rule (2) against the halves rule (3), in four hold-out tests:

| Hold-out test | Areas | Wrong-area share, halves → thirds | Median absolute log ratio, halves → thirds |
|---|---:|---:|---:|
| US counties within states, BEA 2024 | 3,115 | 13.95% → 11.58% | 0.258 → 0.239 |
| UK middle layer areas (MSOAs, 5,000 to 15,000 residents) within local authorities, ONS 2023 | 7,199 | 27.86% → 24.68% | 0.453 → 0.411 |
| EU NUTS3 regions within NUTS2 regions, Eurostat 2023 | 1,245 | 9.48% → 7.65% | 0.134 → 0.113 |
| Brazilian municipalities within states, IBGE (Brazil's statistics institute) 2023 | 5,569 | 18.64% → 17.47% | 0.272 → 0.273 |

Spreading by population alone scores 17.4%, 39.5%, 9.9% and 19.6% in the same tests. Only 6 of Brazil's 26 states reach the coverage threshold, so its gain is small, and its median log ratio is slightly worse.

**US jobs.** Each state's official total spread to its counties:

| Rule for US counties | Wrong-area share | Median absolute log ratio |
|---|---:|---:|
| Residents, buildings and business locations (rule 2) | 11.6% | 0.239 |
| All jobs | 8.3% | 0.165 |
| Well-paid jobs | 6.2% | 0.147 |
| Half all jobs, half well-paid jobs | 6.9% | 0.142 |
| Each industry by its well-paid jobs (used) | 5.1% | 0.146 |

For the industry rule, each state's GDP is first split by BEA's state industry shares. Going from well-paid jobs to the industry rule, the wrong-area share falls from 12.3% to 8.4% in the nine Bay Area counties, from 7.1% to 1.9% in King, Pierce and Snohomish counties around Seattle, and from 11.2% to 1.8% across New York City's five boroughs. The industry rule puts Manhattan at 1.02 times its official GDP, King County at 0.97, Santa Clara at 0.84 and San Mateo at 0.66.

Part of this agreement is built in. BEA spreads some state GDP to counties using county payroll and sales data, and a count of well-paid jobs follows payroll.

**Before these steps.** Kummu's grid put 0.97% of mainland US GDP in Manhattan (official figure 3.52%), and 0.05% of England and Wales GVA in the City of London (official figure 4.98%). Most of the error came from Kummu's coarse inputs, which official regions (step 2) replace.

**Company lower bounds.** For tech campuses we estimated the value added of each circle's largest employer. The low estimate is the site's pay (local staff × the county's average pay in that industry) plus a per-head share of the company's US profit and depreciation; profit booked abroad is not US GDP. The high estimate gives the site the same share of the company's US value added as it has of the company's pay. Either is a floor, because it leaves out every other employer. Floors are in 2024 US dollars; the site's US figures run 1.5% above BEA's, so we compare them directly. The company figures come from the [company benchmark](company-benchmark.md), which gives the method and sources; we have not rechecked them against the filings. The 1 and 2 km rows come from the table under a 3 km circle.

| Circle | Largest employer | Floor, $ billion | moneymap, $ billion |
|---|---|---:|---:|
| Apple Park, 1 km | Apple | 9–15 | 19.0 |
| Meta, Menlo Park, 1 km | Meta | 22–24 | 50.9 |
| Googleplex, 2 km | Google | 35–45 | 37.6 |
| Googleplex, 3 km | Google | 35–45 | 45.8 |
| Nvidia, Santa Clara, 1 km | Nvidia | 17–55 | 10.6 |
| Nvidia, Santa Clara, 2 km | Nvidia | 17–55 | 32.6 |
| Microsoft, Redmond, 1 km | Microsoft | 34–47 | 52.3 |
| Microsoft, Redmond, 3 km | Microsoft | 34–47 | 61.1 |
| Amazon, South Lake Union, 2 km | Amazon | 19–38 | 82.2 |
| Cupertino, 5 km | Apple | 18–29 | 40.8 |
| Menlo Park, 5 km | Meta | 22–24 | 81.5 |
| Redmond, 5 km | Microsoft | 34–47 | 91.9 |
| Mountain View, 10 km | Google, Apple Park | 45–60 | 222.8 |

Nvidia's floor is wide because its local headcount is our estimate (6,000 to 12,000). Later city figures put Google's Mountain View staff at about 24,000 rather than 30,600, which lowers Google's floor, and Microsoft's Redmond staff at over 52,000 rather than 44,782, which raises Microsoft's.

**Totals.** All 48,314 regional totals and 235 country totals come back out of the grid. The largest error is 6 parts in 100 million for a region; across the world the grid differs from the source by $18,197 in $196.88 trillion.

### Known problems

- **Business districts in much of Asia are probably too low.** Japan, China, India, Korea, Indonesia, Russia and Taiwan have too few businesses in Overture's data for the thirds rule (Japan has 2.2 workplace places per 1,000 residents, India 0.6, China 0.01). So their GDP follows residents and buildings within each province or prefecture. When we tested that rule in England, office districts came out 2 to 4 times too low: spread from its borough's official total, Canary Wharf got 16% of the borough's GVA against 60% in the official figures. The 3 km circle around Tokyo's Marunouchi holds 2.0% of Tokyo prefecture's residents and 13.7% of its building weight. It gets $86 billion, 7.9% of the prefecture's GDP. In the business-locations experiment, adding workplace places gave it $137 billion; Tokyo's totals and weights have not changed since. We have no official figure for central Tokyo to say which is closer.
- **Nvidia is too low, and the cause is BEA's county total.** BEA puts the GDP of all manufacturing in Santa Clara County at $73.7 billion, less than Nvidia's own US value added of about $90 billion. Santa Clara County's GDP grew $34 billion from 2023 to 2024, while Nvidia's US profit grew about $48 billion. No rule for spreading GDP inside the county can fix this. Within the county's manufacturing, every well-paid job also carries the same GDP, although Nvidia's value added is about $2.5 million per employee.
- **LODES seems to count some staff at head offices.** LODES places 28,900 information-industry jobs within 1 km of Meta's head office; Menlo Park's own figures count 12,159 Meta staff in the whole city. The Meta 1 km circle, at $50.9 billion, is about twice its floor. Other head-office campuses may be too high in the same way. County totals are not affected.
- **Profit booked abroad is not in US GDP.** BEA counts profit where companies operate, not where they are incorporated: Delaware's whole 2024 GDP is $111 billion, less than Nvidia's US value added. But profit that companies book in other countries is not US GDP at all. Apple booked 63% of its profit abroad and Microsoft 42%, against 6% to 10% for Alphabet, Meta, Nvidia and Amazon. So the Apple and Microsoft circles are lower than their world profits suggest, as GDP's definition requires.
- **Most of the world uses coarse regions.** 67% of world GDP is spread within provinces, states or whole countries, using residents, non-residential buildings and, in some regions, business locations. Inside a Chinese province, two districts with similar residents and buildings get similar GDP, whatever their industries.
- **Single-cell UK areas.** The 13,311 UK areas that put their GDP in one cell are mostly smaller than a cell, so their GDP moves by less than a cell's width. But it makes the map lumpy: in the 3 km circle around Bank in the City of London, $126 billion arrives this way. That figure was measured in the business-locations experiment; the UK regions and their totals have not changed since.
- **Mixed years.** UK, Dutch and European shares are from 2023, applied to 2024 totals.

## Land value

Code: `sources/land_value.py`, `layers/land_value/`.

**What it measures.** The market value of land without the buildings on it, in 2024 US dollars at market exchange rates. It covers all land: housing, business, farm and public land, as national balance sheets count it.

### How it is calculated

**Step 1: national totals.** A national balance sheet is the official account of a country's assets. Some include the value of land. We use, in order:

| Source of the national total | Countries and territories | Land value, $ trillion |
|---|---:|---:|
| OECD Table 9B: all land in the economy | 14 | 62.32 |
| OECD Table 9B: land owned by households, ÷ 0.6 | 13 | 68.31 |
| Taiwan's national wealth statistics (DGBAS, Taiwan's statistics office) | 1 | 4.18 |
| Model based on the share of people in big cities | 207 | 104.43 |
| World | 235 | 239.24 |

- The 14 full reporters are Australia, Austria, Canada, Czechia, Estonia, Finland, France, Germany, Japan, Korea, the Netherlands, Slovakia, Sweden and the UK. Mexico, Croatia and New Zealand also report, but their figures are partial, so they use the model.
- The 13 household-only countries include the US, Italy, Spain and Poland. Where both figures exist, households own between 31% and 84% of all land; the median is 60%.
- Each published figure becomes a ratio of land to GDP, in its own year and currency. We multiply that ratio by 2024 GDP in US dollars from the World Bank. UN figures fill 12 gaps. 18 small territories with no GDP figure at market exchange rates use Kummu's GDP, scaled by a named reference country's ratio of GDP at market rates to GDP at purchasing power parity; they hold 0.06% of world GDP. Six territories use their latest GDP, from 2021 to 2023.
- Taiwan's land was worth NT$134.12 trillion at the end of 2024; we convert at the central bank's 2024 rate of NT$32.108 per US dollar.
- For all other countries:

  ```
  land ÷ GDP = exp(0.1675 + 1.7479 × s)
  ```

  where *s* is the share of the population living in cities of over one million people (World Bank). The build fits this by least squares to the 14 full reporters. It gives China 2.1 times GDP, India 1.6, Brazil 2.6 and Russia 1.8. 108 countries and territories, mostly small, have no figure for *s*; the model treats them as having no city of a million people, which gives 1.18 times GDP.

**Step 2: within each country.**

```
cell land = country land × ( ½ × cell's weighted residents ÷ country's weighted residents
                           + ½ × cell GDP ÷ country GDP )
weighted residents = cell residents × (people per km² within about 40 km)^0.25
```

"People per km² within about 40 km" counts residents up to 320 km away, each weighted by e^(−distance ÷ 40 km), divided by the area under that weight. It is computed on a grid of 5 arc-minutes (about 9 km) and interpolated to the cells. GDP is the site's own GDP layer.

Land prices rise with city size. Urban economics studies, as cited in the [land value research](land-value-research.md), find that land prices at city centres rise by about 0.3% for each 1% more people (Combes, Duranton and Gobillon, 2019); the exponent 0.25 is close to that. The GDP half adds where the economy is. There is no separate farmland term: in tests, a cropland term never helped.

### How we checked it

**National totals.** The independent review of the land method left each full reporter out in turn, refitted the model and predicted the missing country. The typical error was a factor of 1.56. On the 13 household-only countries, which the model never saw, it was a factor of 1.95, with no bias up or down. A model using GDP per head fitted the reporters better but failed on other countries: it put India's land at 0.21 times GDP. Independent figures agree better with the chosen model, although the review had to infer the ratios from them: India's 2019 All India Debt and Investment Survey suggests roughly 1.7 times GDP (model 1.6), and China's national balance sheet from the Chinese Academy of Social Sciences suggests roughly 1.5 to 2.5 times (model 2.1). For the US, BEA researchers' estimate of all private land in 2015, set against the Federal Reserve's household land figure, implies that households held roughly 0.59 of it, close to the 0.6 we assume.

**Within countries.** The production layer against official land values that no rule was fitted to:

| Official land values | Areas | Wrong-area share | Median absolute log ratio |
|---|---:|---:|---:|
| North Rhine-Westphalia municipalities: official land prices (Bodenrichtwerte) 2026 × zone area | 396 | 14.80% | 0.278 |
| Japanese municipalities: fixed-asset tax land values, 2025 | 1,719 | 19.15% | 0.655 |
| Danish municipalities: taxable land value, 2025 | 98 | 14.72% | 0.259 |
| Victorian councils: site value, 2026 | 79 | 18.60% | 0.388 |
| British Columbia municipalities: land value, 2026 roll | 160 | 11.91% | 0.579 |
| US counties: residential land only (Federal Housing Finance Agency (FHFA) land share × American Community Survey (ACS) home values) | 2,423 | 28.88% | 0.791 |
| New York City community districts: Department of Finance land values | 59 | 26.44% | 0.356 |

The review chose this rule from seven fixed candidates across ten such tests, on an earlier GDP layer. It was best in five and within 2.5 percentage points of the best in all ten, with a mean wrong-area share of 17.1% against 20.2% for population alone. Details: [land value research](land-value-research.md#fable-review).

**Circles.** The review also drew circles on North Rhine-Westphalia's official land prices around eight cities and four rural centres. It ran on the earlier GDP layer, but German GDP has not changed since, so the results hold. The typical error of the circle total (median absolute log ratio, both scaled to the state total) is:

| Radius | 3 km | 5 km | 10 km | 20 km | 30 km | 50 km |
|---|---:|---:|---:|---:|---:|---:|
| Median absolute log ratio | 0.38 | 0.35 | 0.34 | 0.32 | 0.27 | 0.23 |

So a 10 km circle is typically out by a factor of 1.4, and a 50 km circle by a factor of 1.26.

**Totals.** All 235 country totals come back out of the grid; across the world the grid differs from the target by $22,791 in $239.24 trillion.

### Known problems

- **Rich city centres read low, cheaper cities of the same density read high.** Against the official land prices, the 3 km circle around Cologne cathedral gets 0.60 times its value and Düsseldorf 0.37 times. In the municipality test, the density weight alone puts Düsseldorf and Cologne 2 to 2.5 times too low and the Ruhr cities, such as Gelsenkirchen, 2.5 times too high; the GDP half narrows this gap. The model sees density, not regional price levels, and it cannot see resort towns or mining towns.
- **Tokyo's centre is about half what it should be.** Tokyo's 23 wards hold 21.8% of Japan's official land value; moneymap puts 11.3% there.
- **US residential land by county** is typically out by a factor of 2.2 (median absolute log ratio 0.79).
- **Modelled national totals are uncertain.** The 207 modelled countries hold $104 trillion, 44% of world land value. Their totals carry a typical error of a factor of 1.6 to 1.9.

## Building and property value

Code: `sources/building_value.py`, `layers/building_value.py`.

**What it measures.** Building value is the net value of homes and other buildings: what they would cost to replace, less wear and age (depreciation). It is in 2024 US dollars at market exchange rates. It excludes roads, bridges, pipelines and other civil engineering, and improvements to land. Property value is land plus buildings. The site adds the two layers and shows both.

### How it is calculated

**Step 1: national totals.** OECD Table 9B gives net dwellings plus net other buildings for 32 countries. As for land, each country's latest ratio to GDP is multiplied by 2024 GDP in US dollars: 20 countries use 2024, 10 use 2023, Latvia 2022 and Russia 2019. Mexico and Croatia report complete building figures even though their land figures are partial. Australia, Chile and Romania do not report non-residential buildings separately, so they use the model, as does Taiwan, whose national wealth table combines buildings with other structures. For the other 203 countries and territories:

```
buildings = 1.9296 × 2024 GDP in US dollars
```

1.9296 is the geometric mean ratio across the 32 reporters. We compared four simple models by leaving each reporter out in turn. The constant has the fewest parameters and the smallest error:

| National model of buildings ÷ GDP | Typical error when each reporter is left out (root mean square of the log error) |
|---|---:|
| Constant (used) | 0.297, a factor of 1.35 |
| Share of people in big cities | 0.308 |
| GDP per head | 0.301 |
| Both | 0.312 |

| Source of the national total | Countries and territories | Building value, $ trillion |
|---|---:|---:|
| OECD Table 9B | 32 | 134.38 |
| Constant ratio to GDP | 203 | 90.40 |
| World | 235 | 224.78 |

With land, the world's property comes to $464 trillion. Savills, a property firm, put the world's real estate at $393 trillion in 2025, as cited in the [land value research](land-value-research.md); ours is 18% higher.

**Step 2: within each country.**

```
cell buildings = country buildings × ( ⅓ × cell residents ÷ country residents
                                     + ⅓ × cell GDP ÷ country GDP
                                     + ⅓ × cell building volume ÷ country building volume )
```

Building volume is GHSL's total built volume for 2025, homes and other buildings together, shifted onto the population grid as for GDP.

### How we checked it

We compared four fixed rules for spreading buildings within a country, against official valuations. Each entry is wrong-area share / median absolute log ratio. The first four rows score buildings; Amsterdam scores homes, land and buildings together.

| Official values | Areas | Volume | Residents | Residents and GDP | Thirds (used) |
|---|---:|---:|---:|---:|---:|
| Victorian councils, 2026 | 79 | 19.5% / 0.37 | 16.1% / 0.16 | 15.0% / 0.19 | 15.3% / 0.25 |
| British Columbia municipalities, 2026 roll | 160 | 16.9% / 0.39 | 10.4% / 0.22 | 11.3% / 0.32 | 12.9% / 0.35 |
| US counties, owner-occupied homes | 2,423 | 18.0% / 0.44 | 13.9% / 0.32 | 14.3% / 0.25 | 14.2% / 0.31 |
| New York City community districts | 59 | 26.1% / 0.45 | 25.2% / 0.40 | 26.4% / 0.36 | 23.4% / 0.35 |
| Amsterdam area, homes | 73 | 25.9% / 0.49 | 23.2% / 0.44 | 26.1% / 0.52 | 26.1% / 0.49 |
| Mean wrong-area share | | 21.3% | 17.8% | 18.6% | 18.4% |

Residents alone had the lowest mean, but in New York it put 7.1% of building value in Manhattan's six core community districts, against 23.9% in the official figures. The thirds rule had the lowest error in New York and the second-lowest mean, so we chose it, accepting that it puts too much in the core.

For property, land plus buildings, the production layers score: Victoria 15.3% / 0.26, British Columbia 10.4% / 0.29, US owner-occupied homes 17.2% / 0.36, New York City 23.2% / 0.35, Amsterdam 26.1% / 0.49.

What the tests measure:

- *Victoria:* capital improved value minus site value, 2026. Improvements can include more than buildings.
- *British Columbia:* the 2026 roll at July 2025 values. Improvements include fixtures.
- *US:* census figures for owner-occupied homes (ACS 2023), split into land and buildings with FHFA land shares. Rented homes and commercial property are missing, so this is a rough guide to where value sits.
- *New York City:* Department of Finance market values on the 2024 final roll, for 1,146,125 lots in 59 community districts, homes and commercial property together. These are valuations set for property tax: they total $1.70 trillion, against moneymap's $3.67 trillion in the same districts, so only shares are compared.
- *Amsterdam area:* the CBS 500 m grid for 2023, average home tax value (WOZ, valued at 1 January 2022) × number of homes, summed into 73 squares of 2 km. Homes only, land and buildings together.

**Totals.** All 235 country totals come back out of the grid; across the world the grid differs from the target by $14,895 in $224.78 trillion.

### Known problems

- **Manhattan's core is too high.** The thirds rule puts 42.6% of New York City's building value in Manhattan's six core districts, 1.78 times their official 23.9%. Across all of Manhattan it puts 50.3% against 34.6%. None of the four rules comes close in the core.
- **The rule matters most in dense centres.** Across the four rules, buildings in the 6 km circle over Midtown and Lower Manhattan range from $104 billion (volume) to $1,338 billion (residents and GDP); the site shows $927 billion. Around Bank in London (3 km) they range from $22 billion to $222 billion; the site shows $155 billion.
- **One ratio covers most of the world.** 203 countries, including China ($36.1 trillion of buildings), India and Australia, use 1.93 times GDP. The typical error is a factor of 1.35, and the worst reporter, Poland, would be 3 times too high.
- **Tests and the site define buildings differently.** Victoria and British Columbia include fixtures, the US and Amsterdam tests cover homes only, and New York uses tax valuations.

## How to improve it

The evidence above points to these next steps.

- **Official GDP for smaller regions** in the large economies that now use provinces, states or whole countries. Each table plugs in beside the existing ones in `sources/regional_gdp.py`.
- **Workplace data for Asia.** Overture's business coverage is too thin in Japan, China and India for the thirds rule. A jobs source like LODES, or a fuller business map, would matter most in places like central Tokyo. Testing the thirds rule against Japanese or Chinese official figures would show whether a lower coverage threshold is safe.
- **Head-office jobs in LODES.** Compare LODES block counts with published site headcounts, such as the city employer tables in the [company benchmark](company-benchmark.md), and correct blocks that hold far more jobs than the site has staff.
- **Official land values where they exist.** North Rhine-Westphalia, Japan, Denmark, Korea, New South Wales, Victoria and British Columbia publish land values that are only tests today. Using them directly would also fix the regional price levels the model cannot see.
- **Buildings in dense centres.** Open valuation rolls, as in New York, Victoria, British Columbia and the Netherlands, could replace the model where they exist, and could test a rule based on floor area or building height.
- **National totals without balance sheets.** Cross-check China and India against the World Inequality Database's housing and farmland wealth, as the [land value research](land-value-research.md) suggests.
- **Stops.** A tag rule that counts Utrecht's light rail as tram without moving Berlin's S-Bahn.
- **Population.** Correct places where GHS-POP is wrong, such as Svalbard, for example with national census grids.
- **Publish the reports.** The figures on this page come from build and check reports under `data/`, which is not in git because of its size. Publishing them would let others check the figures without rebuilding.

## Credits and licences

moneymap is adapted from Tom Forth's [Population around a point](https://www.tomforth.co.uk/circlepopulations/), his page and code. His page says "All the code stuff above is Creative Commons Licence BY 4.0" ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)). We changed it: we added GDP and property value, radii up to 100 km and a new server. The code is under the [MIT licence](../LICENSE). The data keeps its sources' licences:

| Data | Used for | Licence and required attribution |
|---|---|---|
| [GHSL](https://human-settlement.emergency.copernicus.eu/datasets.php) GHS-POP, GHS-BUILT-V and GHS-BUILT-S, R2023A, 2025 | Population, building weight, building volume | European Commission, Joint Research Centre (JRC). [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Cite: Schiavina M., Freire S., Carioli A., MacManus K. (2023), GHS-POP R2023A, [doi:10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE](https://doi.org/10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE); Pesaresi M., Politis P. (2023), GHS-BUILT-V R2023A; Pesaresi M., Politis P. (2023), GHS-BUILT-S R2023A, [doi:10.2905/9F06F36F-4B11-47EC-ABB0-4F8B7B1D72EA](https://doi.org/10.2905/9F06F36F-4B11-47EC-ABB0-4F8B7B1D72EA). |
| Kummu et al., paper ([Scientific Data, 2025](https://doi.org/10.1038/s41597-025-04487-x)) and dataset, March 2026 release ([doi:10.5281/zenodo.18429133](https://doi.org/10.5281/zenodo.18429133)): band 8, `gdp_2024`, of `rast_gdpTot_1990_2024_30arcsec.tif`, and the admin-1 polygons. The release labels the unit 2021 international dollars, but its totals behave like 2024 PPP dollars (see Units); the file's embedded 2017 unit tag is out of date. | National and provincial GDP | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Cite both the paper and the dataset. |
| [BEA](https://apps.bea.gov/regional/) county GDP and GDP by industry (CAGDP1, CAGDP2); [US Census](https://www2.census.gov/geo/tiger/GENZ2024/shp/) county boundaries; [LODES8](https://lehd.ces.census.gov/data/lodes/LODES8/) | US GDP regions and jobs | US government works, public domain |
| [ONS small-area GVA](https://www.ons.gov.uk/economy/grossvalueaddedgva/datasets/uksmallareagvaestimates) and LSOA boundaries | UK GDP regions | [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). "Source: Office for National Statistics licensed under the Open Government Licence v.3.0. Contains OS data © Crown copyright and database right 2026." |
| [Scottish data zone boundaries, 2011](https://www.data.gov.uk/dataset/ab9f1f20-3b7f-4efa-9bd2-239acf63b540/data-zone-boundaries-2011) | UK GDP regions | Open Government Licence v3.0. "Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right 2026." |
| [Northern Ireland super output area boundaries, 2011](https://www.nisra.gov.uk/files/nisra/publications/SOA2011_Esri_Shapefile_0.zip) | UK GDP regions | Open Government Licence v3.0 ([NISRA terms](https://www.nisra.gov.uk/crown-copyright)). "Source: NISRA. Contains Ordnance Survey of Northern Ireland information licensed under the Open Government Licence v3.0." |
| [Eurostat regional GDP](https://ec.europa.eu/eurostat/web/regions/database) (nama_10r_3gdp) | European GDP regions | [Eurostat reuse policy](https://ec.europa.eu/eurostat/help/copyright-notice). "Source: Eurostat." Because we modify the data, the policy also asks us to say so: moneymap uses these figures only as each region's share of its country's GDP, applied to other national totals, and Eurostat is not responsible for the results. |
| [GISCO NUTS 2024 boundaries](https://ec.europa.eu/eurostat/web/gisco/geodata/statistical-units) | European GDP regions | "© EuroGeographics for the administrative boundaries." The notice must be visible on any publication that uses the data. GISCO's terms allow non-commercial use only; the GDP layer depends on these boundaries. |
| [CBS 85924NED](https://opendata.cbs.nl/ODataApi/OData/85924NED) and [PDOK COROP-plus boundaries](https://api.pdok.nl/cbs/gebiedsindelingen/ogc/v1) | Dutch GDP regions | Statistics Netherlands (CBS). [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| [Overture Maps](https://overturemaps.org/) places, release 2026-09-23.1 | Workplace places | [CDLA Permissive 2.0](https://cdla.dev/permissive-2-0/), [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) and [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (the AllThePlaces source), depending on the source of each place ([Overture attribution](https://docs.overturemaps.org/attribution/)). "Overture Maps Foundation, overturemaps.org." Overture warns that joining CDLA-licensed places to OpenStreetMap data may make the result fall under the ODbL; moneymap keeps places and stops in separate layers and does not join them. |
| [Overture Maps](https://overturemaps.org/) transit infrastructure, release 2026-09-23.1 | Stops | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). "© OpenStreetMap contributors, Overture Maps Foundation." The stop layers are derived from OpenStreetMap, so they are available under the ODbL, not the MIT licence. |
| [OECD Table 9B](https://data-explorer.oecd.org/vis?df[ag]=OECD.SDD.NAD&df[id]=DSD_NASEC10@DF_TABLE9B) | Land and building totals | [OECD terms and conditions](https://www.oecd.org/en/about/terms-conditions.html): any use, with credit, passed on to anyone who reuses ours. Cite: OECD (2026), Table 9B, balance sheets for non-financial assets, OECD Data Explorer, https://data-explorer.oecd.org/vis?df[ag]=OECD.SDD.NAD&df[id]=DSD_NASEC10@DF_TABLE9B (accessed on 16 October 2026). |
| [World Bank](https://data.worldbank.org/) World Development Indicators | Land and building totals | [CC BY 4.0](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets), passed on to anyone who reuses ours. "The World Bank: GDP (current US$), GDP (current LCU), GDP per capita, PPP (constant 2021 international $), and Population in urban agglomerations of more than 1 million (% of total population): World Development Indicators." |
| [UN Statistics Division national accounts](https://unstats.un.org/unsd/snaama/) | GDP gaps | [UNdata terms](https://data.un.org/Host.aspx?Content=UNdataUse): free to copy and redistribute if UNdata is cited. "UN Statistics Division, National Accounts Main Aggregates Database, via UNdata." |
| Taiwan DGBAS [national wealth](https://eng.stat.gov.tw/cl.aspx?n=2411) and [national accounts](https://eng.stat.gov.tw/News_Content.aspx?n=2336&s=235628); [Taiwan Central Bank](https://www.cbc.gov.tw/en/) exchange rate | Taiwan land and GDP | [Open Government Data License, version 1.0](https://data.gov.tw/en/license) (compatible with CC BY 4.0; [DGBAS](https://eng.stat.gov.tw/cp.aspx?n=2313) and [Central Bank](https://www.cbc.gov.tw/en/cp-958-40419-F8209-2.html) terms). "Directorate-General of Budget, Accounting and Statistics, 2024, National Wealth Statistics and National Accounts; Central Bank of the Republic of China (Taiwan), 2024, exchange rates. Open Government Data License, version 1.0, https://data.gov.tw/en/license." |
| Map tiles | Background map | Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL. Tiles from the OpenStreetMap Foundation, used under its [tile usage policy](https://operations.osmfoundation.org/policies/tiles/). Map library: [Leaflet](https://leafletjs.com/), BSD 2-Clause. |

The tests use further data that the site does not show or redistribute: official valuations from New South Wales, Victoria, British Columbia, North Rhine-Westphalia, Japan, Korea, Denmark and New York City; FHFA land shares and US census home values; CBS's 500 m grid; Brazil's IBGE municipal GDP; and company filings, US Bureau of Labor Statistics pay data and city reports for the company bounds. The research notes list each source.

## Reproducing the numbers

[README.md](../README.md) lists the input files, by the names the code expects, and the commands that build every layer and run every check. The `data/` folder is not in git.

Build reports:

- population: `data/build/population.json`;
- stops: `data/build/transit-stops.json`;
- GDP: `data/build/gdp/conservation.json`, with every region's target, weights and rule;
- land and buildings: `data/build/land_value/` and `data/build/building_value/`, each with `country_totals.csv` (every country's target, source and year) and `conservation.json`.

Checks write `data/checks/`: `holdouts.json` for GDP, `land_value.json`, `building_value.json` and `building_value_candidates.json` for property, and `circles.json` for the site's answers.

Two checks need outputs from the research scripts, which the build itself does not use. `checks/holdouts.py` reads `data/experiments/places/{us,uk,eu,br}_sums.json` and `unit_sums_summary.json`, written by `research/gdp/places_eval.py`. `checks/land_value.py` reads `data/experiments/land-value/*_scores.json` and `nrw_official_grid.npz`, written by the scripts in `research/land-value/`. Run those first.

## Background notes

These notes record the research behind each choice, including the alternatives that failed. Where they disagree with this page, this page and the code are current.

- [GDP method research](gdp-method-research.md): why official regions and the building weight, and the business-locations experiment.
- [Land value research](land-value-research.md): what land data exists, the worldwide method, and the independent review by Claude Fable 5.1.
- [Stop research](stops-research.md): matching Tom Forth's stop counts.
- [Company benchmark](company-benchmark.md): lower bounds for tech-campus GDP, and where BEA puts company profit.
