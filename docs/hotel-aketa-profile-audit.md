# Hotel Aketa: duplicate OTA profile audit

Checked 28 September 2026. Subject: Hotel Aketa, 113/1-2 Rajpur Road, Hathibarkala Salwala, Dehradun 248001. The comparable stay is 28-29 September 2026, one adult, one room, zero children, INR. A published profile and a historical search-engine price are not current sellability evidence.

## Result

Two different Aketa profile IDs exist on Agoda and two on Expedia. The current Agoda profile returned dated offers in a fresh capture observed at **06:55:45 UTC / 12:25:45 IST**, completed at 06:56:47 UTC. Its 24 raw offers include 14 explicitly matching one adult and one room. The lowest display is **INR 5,169 per night before taxes and fees**, Premium Single Room, breakfast included, members-only with an automatically applied Agoda coupon. Pay-now and cancellation conditions apply. This establishes that an offer was displayed for sale at observation time; checkout price and booking success were not tested.

| Source | Profile ID / identity | Profile URL | Sale evidence |
| --- | --- | --- | --- |
| Agoda, Hotel Aketa | **110205** | [Current Aketa](https://www.agoda.com/hotel-aketa/hotel/dehradun-in.html) | Fresh dated positive room-grid response: 14 matching offers, minimum INR5,169 before taxes/fees. |
| Agoda, Keys Prima Aketa | **27746358** | [Legacy-name Aketa](https://www.agoda.com/key-prima-by-lemon-tree-hotels-aketa-dehradun/hotel/dehradun-in.html) | Distinct ID in live page links, same 113/1 address and 40 rooms. Browser controls showed 28-29 September and one adult/one room; no room price or explicit unavailable result was obtained. Sale status unknown, not sold out. |
| Expedia, Hotel Aketa | **92850456** | [Current Aketa](https://www.expedia.co.in/Dehradun-Hotels-Hotel-Aketa-Dehradun.h92850456.Hotel-Information) | Published matching profile. Earlier dated request hit 429/403; no repeat attempted. Current rates unknown. |
| Expedia, Keys Prima Aketa | **133767894** | [Legacy-name Aketa](https://www.expedia.co.kr/en/Dehradun-Hotels-Keys-Prima-By-Lemon-Tree-Aketa-Dehradun.h133767894.Hotel-Information) | Different profile ID with matching 113/1-2 address. Indexed page asks for dates; its recommendation prices belong to other hotels. Current Aketa rate unknown. |
| Hotels.com | **ho2972214592**; Expedia inventory **92850456** | [Aketa](https://in.hotels.com/ho2972214592/hotel-aketa-dehradun-dehradun-india/) | Cross-brand mirror linked to the current Expedia record; not proof of another physical property. Current sale status unknown. |
| Booking.com | Property slug **aketa**; numeric ID unknown | [Aketa](https://www.booking.com/hotel/in/aketa.en-gb.html) | One distinct property slug found; language suffixes are aliases. Matching Rajpur Road address. Earlier access challenge; indexed September 3-6 offers are historical. |
| MakeMyTrip | **202108231240265962** | [Aketa](https://www.makemytrip.com/hotels/hotel_aketa_rajpur_road_dehradun-details-dehradun.html) | One distinct Aketa profile found. Earlier live response supplied no usable quote; indexed different dates/party are excluded. |
| Goibibo | **3276063361333979623** | [Aketa](https://www.goibibo.com/hotels/aketa-rajpur-road-dehradun-hotel-in-dehradun-3276063361333979623/) | One distinct Aketa profile found at 113/1 Rajpur Road. Indexed prices show two guests and cannot establish this audit's current one-adult quote. |

This is a bounded search, not proof that no additional profile exists. Each distinct provider ID stays separate until its own price and availability context is verified. No canonical source mapping is replaced solely because the older profile is visible.

## Why the old name remains

The [official Keys Prima Aketa factsheet](https://www.lemontreehotels.com/factsheet/Keys_Prima_by_Lemon_Tree_Hotels,_Aketa_Dehradun(16-feb).pdf) identifies the same address and 40-room hotel. Lemon Tree's [termination disclosure](https://www.lemontreehotels.com/factsheet/Policies/Disclosure_Termination_Key_Aketa_Dehradun_03_10_2023.pdf), listed in its [investor announcements](https://investors.lemontreehotels.com/disclosures-announcements.html), records termination of the Aketa license agreement on 3 October 2023. This supports the old-brand relationship; it does not prove the old OTA profile is closed or still sells inventory.

Nearby Red Fox has a different address/profile and is listed by [MakeMyTrip as 110 metres from Aketa](https://www.makemytrip.com/hotels/hotels-nearby-hotel_aketa_rajpur_road_dehradun-dehradun.html). It is excluded. Aketa Trancoso in Brazil and Keys Prima Kempty Road, Mussoorie are also excluded. Language, country-domain, review, photo and room subpages are not counted as extra profiles.

## Evidence and pipeline repair

Fresh canonical capture: `data/hotels/aketa/profile-audit/agoda-20260928T065647650951Z.json`. The first parser output was unknown because Agoda changed the literal label from `Per night before taxes` to `Per night before taxes & fees`. The exact matched response still has numeric/display agreement, correct property, requested dates/party/currency, `isSoldOut=false`, six room types and 24 offers. A narrow parser repair accepts the observed label and marks both tax and fee inclusion false, while retaining indicative display precision. The original before-tax label keeps unknown fee inclusion. Unrecognized labels remain unknown.

The capture's original unknown interpretation is saved separately as `canonical-agoda-observation.json`; the immutable raw evidence allows corrected offline interpretation without another source request. Profile audit JSON and the legacy-page identity/result evidence live in the same directory. This audit does not add unverified alternate-profile rates to the canonical database. Independent parser proof and final import/export verification are recorded in review018.

Root's full suite passed **375 tests in 22.750 seconds**. The corrected observation is saved as `canonical-agoda-observation-corrected.json`. Offline import and dashboard publication made zero new capture calls; job `d1b97cf80d17273ed496810258cf6846b90935ac3fb9dd93605a550fd0d32952` retains all 150 source/date cells and 51 observations, with the 14 Agoda price rows refreshed to this capture. Root verified UTF-8 API/file equality, minimum INR5,169, explicit excluded fees/taxes, database integrity and preservation of the earlier capture history.
