Written by AI on 2026.10.16 by model claude opus 5.5.

# Company benchmark for tech-hub circles

Question: are the big tech circles short of GDP? Check: add up the value added of each circle's largest employers. This is a floor, because it leaves out every other employer. All values are $bn. The API reports 2021 international dollars, which for the US are about 2024 dollars ÷ 1.015, so I compare them directly.

## Method

Value added = pay + US-booked pre-tax profit + depreciation and amortisation. I use US-booked profit because profit booked abroad is not US GDP.

- **Low:** the site's own pay (local headcount × BLS QCEW 2024 average pay for that county and industry), plus a headcount share of the company's US profit and depreciation.
- **High:** a pay share of the company's US value added. The site's share is its pay ÷ company pay. This is close to how BEA allocates profit.
- Company pay is median pay (from the proxy statement) × employees. Meta and Visa publish total pay, so I use that. For Apple and Amazon the median worker is in a shop or a warehouse, so I add stock-based pay.

| Company (year) | US value added | Per employee | Inputs |
|---|---:|---:|---|
| Alphabet (2024) | 184 | $1.0m | 183,323 staff × $331,894; US profit 108.1; depreciation 15.3 |
| Apple (FY Sep 2024) | 88 | $0.54m | 164,000 × $114,738 + stock pay 11.7; US profit 46.2 (63% booked abroad); D&A 11.4 |
| Meta (2024) | 123 | $1.66m | pay 41.3; US profit 66.3; D&A 15.5 |
| Nvidia (FY Jan 2025) | 90 | $2.5m | 36,000 × $301,233; US profit 77.5; D&A 1.9 |
| Microsoft (average of FY Jun 2024 and Jun 2025) | 140 | $0.61m | 228,000 × $200,972; US profit 66.0 (42% booked abroad); D&A 28.2 |
| Amazon (2024) | 193 | $0.12m | 1,556,000 × $36k (my estimate) + stock pay 22.0; US profit 61.9; D&A 52.8 |

## Circles

"Live" is the deployed API, which uses the earlier spreading method (v3). "v4" is the local, undeployed build that spreads county GDP by high-pay workplace jobs; I computed it from `data/layers/gdp` with the Worker's own circle method, and it reproduces the README's Mountain View figure of 193.6.

| Circle | Companies (local staff) | Floor, low–high | Live | v4 |
|---|---|---:|---:|---:|
| Mountain View 10 km | Google, Mountain View (30,600); Apple Park, 8.7 km away (12,000) | 45–60 | 126.8 | 193.6 |
| Cupertino 5 km | Apple, Cupertino (24,000) | 18–29 | 47.2 | 48.4 |
| Menlo Park 5 km | Meta, Menlo Park (12,159) | 22–24 | 33.0 | 53.2 |
| Santa Clara 5 km | Nvidia headquarters (6,000–12,000, **my estimate**) | 17–55 | 80.1 | 117.3 |
| San Jose 10 km | Nvidia, 7.7 km from the centre | 17–55 | 236.0 | 196.2 |
| SF Financial District 3 km | Salesforce (8,400–10,000); Visa (1,000) | 4–6 | 139.1 | 199.9 |
| Seattle South Lake Union 3 km | Amazon, Seattle (50,000) | 19–38 | 76.4 | 136.3 |
| Redmond 5 km | Microsoft, Redmond (44,782) | 34–47 | 36.6 | 61.7 |

At campus scale the gaps are much larger. Each site sits within about 1–2 km of the point given:

| Campus | Floor | Live | v4 |
|---|---:|---:|---:|
| Apple Park, 1 km | 9–15 | 1.6 | 20.9 |
| Meta, 1 km | 22–24 | 2.3 | 22.8 |
| Googleplex (37.4220, −122.0841), 2 km / 3 km | 35–45 | 7.2 / 13.3 | 24.1 / 31.7 |
| Nvidia, 1 km / 2 km | 17–55 | 4.8 / 17.8 | 10.4 / 28.4 |
| Microsoft, 1 km / 3 km | 34–47 | 4.3 / 15.1 | 26.7 / 35.1 |
| Amazon (South Lake Union), 2 km | 19–38 | 47.4 | 90.1 |

## Delaware: where BEA puts corporate profit

BEA puts profit where companies operate. The state of incorporation plays no part. BEA's [GDP by State methodology](https://www.bea.gov/sites/default/files/methodologies/0417_GDP_by_State_Methodology.pdf) says: "For most industries and GDP by state components, the estimates are based on establishment data by state which are used directly." For services industries, BEA spreads each industry's national profit across states by an index: half BEA wages and salaries, half adjusted Census receipts. It assigns headquarters value added "to the states where the CAOs are located" (CAO means central administrative office). It then spreads state totals to counties with Economic Census data: "receipts and payroll county data are used to distribute state OIC for services-producing industries" ([BEA county primer](https://apps.bea.gov/scb/2020/03-march/0320-county-level-gdp.htm)).

Delaware's own numbers confirm this. Its whole 2024 GDP is $111bn (BEA CAGDP1), less than Nvidia's US value added. The leak that matters is profit booked abroad, which is not US GDP at all. In the latest annual reports, the share booked abroad was 63% for Apple, 42% for Microsoft, 90% for Applied Materials and 82% for PayPal, against 6–10% for Alphabet, Meta, Nvidia and Amazon.

## Judgement

- **The live campus figures are too low by 3–10 times.** Live gives Apple Park 1.6 against 9–15, Meta 2.3 against 22, the Googleplex 7 at 2 km against 35 or more, and Microsoft 4 at 1 km against 34 or more. Most of this GDP sits in the right county but has been spread onto homes.
- **Whole circles:** Redmond 5 km (36.6) is at or below Microsoft's floor alone, so it is under-counted by at least 1.3 times. Menlo Park 5 km is barely above Meta alone. The Mountain View, Cupertino, Santa Clara and Seattle totals are above the floor, but their insides are wrong.
- **San Jose is probably over-counted.** Its circle already includes Nvidia, Intel, AMD and Applied Materials, and the known firms explain little of its 236. The v4 build moves 40 out.
- **The v4 build fixes Apple, Meta, Microsoft and Amazon.** It still looks light for Google (32 at 3 km against 35–45) and for Nvidia, because a job count treats a $2.5m-per-head Nvidia job like any other high-pay job. Santa Clara County's GDP grew $34bn from 2023 to 2024, while Nvidia's US profit grew about $48bn. So the county total may itself miss part of Nvidia's 2024.
- **The SF Financial District gives no signal.** The companies I could source are small next to the circle's total.

## Sources and what is estimated

**Sourced:**
- Profit, depreciation and pay totals (Meta, Visa): SEC XBRL company facts from the 10-Ks. Total headcounts are the 10-K figures, but I did not re-read them this session.
- Medians: [Alphabet](https://www.sec.gov/Archives/edgar/data/1652044/000130817925000511/goog_courtesy-pdf.pdf), [Apple](https://www.sec.gov/Archives/edgar/data/320193/000130817925000008/aapl_courtesy-pdf.pdf), [Nvidia](https://www.sec.gov/Archives/edgar/data/1045810/000104581025000095/nvda-20250512.htm) and [Microsoft](https://www.sec.gov/Archives/edgar/data/789019/000119312525245150/d908201ddef14a.htm) 2025 proxies.
- Local pay: [BLS QCEW](https://data.bls.gov/cew/data/api/2024/a/area/06085.csv) 2024, one file per county. Average pay by county and industry: Santa Clara information $488,642, computer and electronic manufacturing $417,500, semiconductors $548,040; San Mateo information $669,097; King software publishers $340,370, company headquarters $303,595; San Francisco software publishers $300,787.
- Meta, 12,159 staff in fiscal 2023–24, city data ([Almanac](https://www.almanacnews.com/menlo-park/2026/06/11/metas-footprint-in-menlo-park-is-shrinking/)).
- Amazon, about 50,000 in Seattle, October 2024 ([KIRO 7](https://www.kiro7.com/news/local/part-amazon-heads-east-seattle-bellevue/GB4TZ6IE4NCCLLRBKMXX6SHWXU)).
- Microsoft, 44,782 in Redmond, City of Redmond data with the year not stated ([425 Business](https://www.425business.com/profiles/spotlight-on-redmond/article_74db4859-f94f-58b7-b973-2503788891f7.html)).
- Apple Park, more than 12,000 staff, Apple 2017; Apple Cupertino, 24,000, a city staff projection for 2020 (San Francisco Chronicle).
- Visa, nearly 1,000 staff, [Visa, June 2024](https://usa.visa.com/visa-everywhere/blog/bdp/2024/06/06/the-future-of-1717704297769.html).

**Weak:**
- Google, 30,600 in Mountain View: a Wikipedia mirror quoting city data, year not stated.
- Salesforce, 8,400 in San Francisco: an older San Francisco Chronicle figure.

**My estimates:**
- Nvidia's Santa Clara headcount (6,000–12,000).
- Amazon's median pay ($36k).
- Salesforce's median pay ($200k).
- Microsoft's depreciation for FY2024 and FY2025 (22.3 and 34.2), not re-checked.

**Not covered:** LinkedIn, Intuit, Apple's Sunnyvale sites, Intel, AMD, Applied Materials, Palo Alto Networks, ServiceNow, Cisco, Adobe, PayPal, Wells Fargo and Uber. With these included, every floor would be higher.

## Sourced site headcounts (follow-up)

Written by AI on 2026.10.16 by model claude opus 5.5 (research subagent). Company totals and median pay come from each company's 2024–25 10-K and proxy statement on SEC EDGAR; site headcounts are from city and county financial reports and business journals, because few companies publish local figures.

| Site | Headcount | Source |
|---|---|---|
| Google, Mountain View | 24,700 (FY to June 2024); 23,100 (FY to June 2025) | [Mountain View ACFR 2024](https://www.mountainview.gov/home/showpublisheddocument/10485/638781725319730000), [2025](https://laserfiche.mountainview.gov/WebLink/DocView.aspx?dbid=0&id=295072&repo=CityDocuments) |
| Google, Sunnyvale | 14,426 (FY to June 2025) | [Sunnyvale ACFR 2025](https://emma.msrb.org/P11915798.pdf) |
| Google, Santa Clara County | 44,244 (from Silicon Valley Business Journal, July 2023) | [County ACFR 2024](https://files.santaclaracounty.gov/exjcpb1531/2025-01/scc-acfr-fy-2024.pdf) |
| Apple, Santa Clara County | 25,000 (same source) | County ACFR 2024 |
| Apple, Sunnyvale | 12,458 (FY to June 2025) | Sunnyvale ACFR 2025 |
| Microsoft, Redmond | over 52,000 FTE (2024–25 licence data) | [City of Redmond](https://www.redmond.gov/943/Largest-Employers) |
| Microsoft, Washington | about 55,000 (July 2024) | Puget Sound Business Journal |
| Intel, California | more than 13,000 (Dec 2023, company spokesperson) | CRN |
| Nvidia, Santa Clara | 2,700 in the city report, from a business database; looks far too low. No company-stated figure found. | [Santa Clara ACFR 2025](https://www.santaclaraca.gov/home/showpublisheddocument/88632/639010527501630000) |
| LinkedIn, Mountain View | 2,500 | Mountain View ACFRs |
| Intuit, Mountain View | 3,200 (2024); 3,400 (2025) | Mountain View ACFRs |
| Salesforce, San Francisco | 8,252 (Aug 2025, from the firm) | San Francisco Business Times |

Median employee pay (proxy statements): Meta $417,400; Alphabet $331,894; Nvidia $301,233; Airbnb $271,657; Palo Alto Networks about $215,882; Adobe $209,583; Intuit $200,562; Microsoft $200,972 (FY25); ServiceNow $199,699; Salesforce $178,949; Cisco $166,915; Visa $154,266; AMD $143,804; Apple $114,738; Intel $96,100; Amazon $37,181 worldwide ($47,990 US full-time).

These revise two inputs above: Google Mountain View is about 24,000, not 30,600; Microsoft Redmond is over 52,000, not 44,782. Both move the floors in the same direction as the conclusions (Google light; Redmond under-counted on the live map).

## City principal-employer tables (follow-up)

Written by AI on 2026.10.16 by model claude opus 5.5 (research subagent). From each city's annual comprehensive financial report; figures checked against the PDF page. The "% of total" denominators differ by city (residents' labour force, daytime population or jobs), and some sources are commercial databases, so use counts, not percentages.

| City (report year) | Largest employers (employees) | Report |
|---|---|---|
| Mountain View (FY2023-24, PDF p.215) | Google 24,700; Intuit 3,200; LinkedIn 2,500; Microsoft 2,300; Waymo 1,600 | [ACFR](https://www.mountainview.gov/home/showpublisheddocument/10485) |
| Sunnyvale (2024, PDF p.256) | Google 14,426; Apple 12,458; Amazon 6,578; Intuitive Surgical 3,836; Lockheed Martin 3,576; Applied Materials 3,389; Facebook 3,090 | [ACFR](https://www.sunnyvale.ca.gov/home/showpublisheddocument/5526/638718778691930000) |
| Palo Alto (FY2024, PDF p.189) | Broadcom/VMware 18,817; Stanford (94305) 18,192; HP 14,673; VA 4,400; Tesla 2,500 | [ACFR](https://www.paloalto.gov/files/assets/public/v/1/administrative-services/financial-reporting/annual-comprehensive-financial-reports-acfr/current-2011-acfrs/city-of-palo-alto-acfr-single-audit-fy2024-final-unsercured.pdf) |
| Menlo Park (2023-24, PDF p.265) | Meta 12,159 | [ACFR](https://www.menlopark.gov/files/sharedassets/public/v/1/administrative-services/documents/finance/annual-comprehensive-financial-reports/2024-annual-comprehensive-financial-report-city-of-menlo-park.pdf) |
| Santa Clara city (2024, PDF p.261; commercial database, likely low) | Applied Materials 8,500; Intel 7,801; AMD 3,000; Nvidia 2,500 | [ACFR](https://www.santaclaraca.gov/home/showpublisheddocument/85732/638701326982270000) |
| San Jose (2024, PDF p.336) | County of Santa Clara 22,732; City 8,262; Cisco 7,500; Adobe 4,100; eBay 3,088; PayPal 2,808 | [ACFR](https://www.sanjoseca.gov/home/showpublisheddocument/116422/638678925166030000) |
| San Francisco (FY2024 report, 2022 data, PDF p.307) | City and County 35,643; UCSF Health 29,475; Salesforce 11,953; United Airlines 10,000 (mostly SFO, in San Mateo County); Wells Fargo 5,886; Uber 3,413 | [ACFR](https://media.api.sf.gov/documents/CCSF_ACFR_FY2024_Final_-_Upload_v2.pdf) |
| Redmond (2021, latest with the table, PDF p.165) | Microsoft 44,782 (later city page: over 52,000) | [ACFR](https://www.redmond.gov/DocumentCenter/View/26833/2021-ACFR-FINAL-AUDITED-12-27-2022-Statements) |
| Milpitas (2023-24, PDF p.206) | Cisco 3,600; KLA 2,760; Western Digital 1,700 | [ACFR](https://www.milpitas.gov/ArchiveCenter/ViewFile/Item/1354) |
| Bellevue (2024, PDF p.193) | Amazon 14,300; T-Mobile 7,800; Meta 5,400 | [Annual report](https://bellevuewa.gov/sites/default/files/media/pdf_document/2025/washington-2024-annual-report.pdf) |

Cupertino (FY2022–25) and Seattle (2024) publish no principal-employer table; Seattle gives King County jobs by industry instead (Information 132,700 of 1,510,500).
