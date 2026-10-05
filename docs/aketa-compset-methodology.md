# Aketa hotel inventory and comparison methodology

Order 012; research observed on 28 September 2026. This is a reproducible inventory and product/service comparison, not a live-rate shop or a claim that every operating hotel has been found.

## Deliverables and rebuilding

From the standalone CompSet Studio root:

```powershell
.\.venv\Scripts\python.exe -m compset.hotel_compset
.\.venv\Scripts\python.exe -m unittest tests.test_hotel_compset -v
```

The builder makes **no network requests**. It reads `data/hotel-compsets/aketa/research.json` and `raw/osm-accommodation-bbox.json`, then writes `latest.json`, a formula-safe `candidates.csv`, and content-addressed `history/<sha256>.json`. Rebuilding the same inputs preserves the same output hash. A changed result appends history and updates the latest projection; it does not remove older evidence. `--manifest`, `--osm` and `--output` support another reviewed snapshot.

The raw directory holds the successful public captures, SHA-256 values for captured HTML, exact request provenance, failed attempts and official map-link destinations. Public web research that was not saved as HTML is explicitly identified as an indexed observation, with date-granularity timestamps and a short factual note. A blocked or failed capture cannot support a researched field. It is not silently replaced with a guessed value.

## Subject and geographic discovery

[OpenStreetMap node 11740798982](https://www.openstreetmap.org/node/11740798982) places Hotel Aketa at **30.3486066, 78.0617838**, address 113/1-2 Rajpur–Mussoorie Road. The node's edit timestamp is 18 March 2024; retrieval on 28 September 2026 does not turn it into a newly surveyed location. The [legacy operator factsheet](https://www.lemontreehotels.com/factsheet/Keys_Prima_by_Lemon_Tree_Hotels,_Aketa_Dehradun(16-feb).pdf) corroborates that street address and describes an upper-midscale city hotel with restaurant/bar, fitness, meeting facilities and 40 rooms. That room count, room categories and affiliation are historical evidence; **current brand affiliation and room count remain unverified**.

[Google's Aketa profile](https://www.google.com/travel/hotels/entity/ChgI98PmmYGh5fJgGgwvZy8xMmNueDRyN3IQAQ) describes a three-star hotel, whereas the [Goibibo category listing](https://www.goibibo.com/hotels/4-star-hotels-in-rajpur-road-area-dehradun-ac/) places it among four-star properties. Both claims remain in the dataset. Neither is relabeled as an observed government certificate. Restaurant, Wi-Fi and room service form the core guest-service comparison. Review scores remain separate from hotel classification.

The first public Overpass `around:10000` query timed out with HTTP 504. One optimized request to the same service succeeded using this containing bounding box:

```text
[out:json][timeout:25];
nwr["tourism"~"^(hotel|motel|guest_house|hostel|apartment|resort)$"]
(30.2586,77.9575,30.4387,78.1661);
out center tags;
```

The response contains **63 accommodation features** at OSM database timestamp **2026-09-28T09:02:58Z**. All features are retained, including guest houses, hostels, institutional accommodation and unnamed hotel buildings. Seven official-source supplements bring the audit to **70 records including Aketa**. The current snapshot has **23 named hotel-tagged candidates within 5 km, five between 5 and 10 km, and four supplemental hotels with unverified locations**. These are candidate records, not a deduplicated census of unique operating hotels. A property can have both a node and a building; similarly named Hotel Sunrise entries are not merged without evidence.

Coordinates support a Haversine straight-line calculation using Earth radius 6371.0088 km. A way's OSM `center` is its geometry bounding-box center, explicitly labeled as such. Radius decisions use unrounded distances, then presentation rounds to four decimal places. This is neither road distance nor survey precision. Unknown/rejected locations produce null distance and `radius_verified: false`; there is no address-based coordinate guessing. Bounding-box corner features outside 10 km would remain visible and be excluded. A response with an Overpass error `remark` or a mismatched declared denominator is rejected.

OSM attribution: **© OpenStreetMap contributors**, [ODbL and attribution information](https://www.openstreetmap.org/copyright). Its finite response is complete for that query, but its real-world mapping coverage is incomplete. The official supplements are bounded research, not an exhaustive OTA crawl. Map presence and an official website do not prove that a hotel is currently open or sellable.

## Selection policy

The policy is a transparent operational comparison rather than a hotel-quality certification:

1. Start with named hotel accommodation within **5 km**. Retain, but exclude from the peer set, hostels, guest houses, homestays, unnamed identities and specialized wellness/luxury products.
2. Require a published **3–4-star** classification or explicit midscale/upper-midscale operator positioning, plus affirmative evidence of **restaurant, Wi-Fi and room service**. A guest review of 4.6/5 is never transformed into a star grade. Conflicting 3/4 claims are disclosed; a conflicting grade outside that band does not pass.
3. Initially prefer at least one evidenced **fitness or meeting** service. If there are **ten or fewer** eligible results, expand the radius to 10 km. If there are still ten or fewer, relax only this optional preference. Every stage retains its count, criteria, trigger and exact selected IDs.
4. Missing core services or classification remain incomplete. A six-hotel result is preferable to pretending unverified hotels meet the product rule. Room-size facts are retained but not used as a hard match because Aketa's current room areas were not established.

For this snapshot, selection proceeds **4 → 6 → 6**. No unknown service is converted to “yes.” Six Senses Vana's wellness/package product and the map-tagged Stairway To Heaven homestay are retained outside the peer set. Major hotels such as Hyatt Centric and Fairfield are recorded as supplemental discovery with location gaps, not silently claimed inside the radius. The inventory still needs further source coverage and profile enrichment.

The deterministic evidence score totals at most 100: hotel product 5; classification/segment 25; restaurant 15; Wi-Fi 10; room service 15; air conditioning 5; parking 5; fitness 5; meetings 5; proximity up to 10. Unknown fields earn zero. This score sorts evidence-supported comparisons; it is **not an observed guest-quality rating or market ranking**. Reviews are retained as secondary evidence without a threshold or score contribution. Room counts, areas and categories are visible comparison details, not invented constraints.

## Current evidenced peers

| Hotel | Straight-line distance | Useful product/service evidence |
|---|---:|---|
| [Sarovar Portico Dehradun](https://www.sarovarhotels.com/sarovar-portico-dehradun/facilities/facilities.html) | 1.22 km | Four-star OTA classification; restaurant, room service, fitness and meetings; operator reports 41 rooms. |
| [Sterling Marbella Dehradun](https://www.sterlingholidays.com/resorts-hotels/marbella-dehradun) | 0.90 km | Four-star Google classification; boutique hotel, restaurant, in-room dining and boardroom; distinct room sizes retained. |
| [Lemon Tree Hotel, Dehradun](https://www.lemontreehotels.com/lemon-tree-hotel/dehradun/hotel-dehradun) | 2.15 km | Four-star Google classification; 49 rooms, restaurant, fitness and meetings. In-room dining is 07:00–23:00. |
| [Zip by Spree Hotels Grand Legacy Prime](https://www.spreehotels.com/zip-by-spree-hotels-grand-legacy-prime/) | 7.09 km | Operator midsegment positioning, dining, room service, parking and conference/banquet facilities. |
| [Hotel The Onix](https://www.hoteltheonix.com/) | 7.87 km | Three-star Google classification; restaurant, air-conditioned rooms, parking, events and room service. |
| [Ramada by Wyndham Dehradun Chakrata Road](https://www.wyndhamhotels.com/ramada/dehradun-india/ramada-dehradun-chakrata-road/overview) | 4.87 km | Four-star Google classification; restaurant, 24-hour room service, pool and meetings. **Official notice says gym and spa are closed for renovation.** |

## Identity and location conflicts

Official structured data is not automatically trustworthy. The manifest preserves these reviewed conflicts:

- Lemon Tree's schema point is several kilometres from Pacific Mall. The named map destination linked by its official page corroborates the OSM location and supplies the accepted coordinate. The bad schema point remains rejected evidence. The schema's decimal `starRating` is not used as hotel classification.
- Sterling Marbella's schema uses a conflicting Chakrata Road address/point. Its visible Rajpur Road address and named official map destination support the accepted coordinate. Its decimal schema rating is rejected as classification.
- The current Clarks Inn official page describes **2 Saharanpur Road, Niranjanpur** but embeds coordinates in Dhanbad. Those coordinates are rejected. The OSM Clarks Inn at **5 Old Survey Road** remains a separate identity; a shared brand name does not establish a match.
- Ramada's operator directions point differs from OSM by about 0.8 km. The operator destination is used, while the original map point and the disagreement stay visible. Both are inside the five-kilometre band.
- Grand Legacy Prime is bound by its exact hotel name and the official named map embed near the OSM point. It is not merged with other Grand Legacy hotels. Map-embed viewport coordinates corroborate identity but do not replace the observed OSM point.
- Manor House has conflicting three-star Google and four-star self-description claims. Nearby gym access does not establish an on-site fitness centre. Unverified room service prevents a positive match in this snapshot.

## Integration contract

`latest.json` uses `schema_version: hotel-compset.v1` and contains `observed_at`, `subject`, `search`, `candidates`, `selected_ids`, `summary`, `relaxation`, `sources` and `warnings`.

Each candidate contains stable namespaced identity, title/address/type, coordinates and all location evidence, distance/band/radius status, product attributes, tri-state amenities, classification/review evidence, selection status/reasons/missing fields, score components, original OSM tags, public URL and field-to-source bindings. `sources` resolves each source ID to its URL, original observation time, capture status and saved artifact when available. Classification conflicts and historical room counts are explicit. `observed_at` is derived from original evidence dates; rebuilding does not refresh source timestamps.

`summary.unique_real_hotel_count` is null, `summary.active_inventory_complete` is false, and `search.exhaustive` is false. All rows have `rate_status` and `availability_status` set to `not_collected`. No amount, occupancy, sold-out status, parity or median is generated from this research. Root's existing Aketa OTA workflow remains responsible for Aketa's dated price observations; peer quote collection requires a separate bounded job and identity/context validation.

## Verification

The offline suite covers finite coordinates, geometry bands and exclusions, exact-ten relaxation, stopping above ten, core unknown/absent services, classification conflicts, review-versus-star separation, non-hotel and unnamed records, retained homonyms, rejected coordinates, failed evidence, partial map responses, deterministic rebuilding, source immutability, safe CSV export and append-only result history. It also rebuilds the real local snapshot and checks the Clarks identity split, rejected Lemon Tree point, historical Aketa room count, Ramada closure and six selected peers.
