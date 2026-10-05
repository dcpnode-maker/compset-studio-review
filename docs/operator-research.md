# BnBME public business-account evidence

Observed on 28 September 2026. This bounded check used six focused searches and public Airbnb page content. It retained business identity and management evidence only.

| Public host | Identifier evidence | Company evidence | Listing count |
| --- | --- | --- | --- |
| [Laya](https://www.airbnb.co.in/users/profile/1462596679799875992) — Dubai | The same public host passport in two live listings maps `DemandUser:16121555` to `ContextualUser:1462596679799875992`. This is the subject's existing account. | [Forte / Opera District listing](https://www.airbnb.co.nz/rooms/1062081483082526816) and [Standpoint listing](https://www.airbnb.co.nz/rooms/1547081958814536406) identify bnbme as manager in their public content. | The user reported 60 on the profile. This lane did not independently count the profile's listings. |
| [Bnbme](https://www.airbnb.co.in/users/profile/1469970159791503339) — India | The public passport on [the Uttarakhand bungalow](https://www.airbnb.co.nz/rooms/53775779) maps `DemandUser:435544594` to `ContextualUser:1469970159791503339`. This is a distinct identifier from the Dubai subject. | The listing's business statement says bnbme homes, a Dubai Airbnb management company, has launched in India. This is explicit business self-description rather than a name match. | Unknown. The profile route returned public application HTML, but its listing card/count did not render in the HTML reader. The observed 39 is a **review count**. |

Confidence is high for these identifier mappings because each pair came from one public `StaysPdpHostInfo.passportData` object. The India company association is supported by a public self-description; it does not independently establish legal common ownership.

No additional distinct Dubai BnBME account was verified within this budget. “Bnbme UK” appeared in search results, but no explicit link to Dubai bnbme Holiday Homes was observed, so it was excluded. A Business Bay listing present in cached search results returned HTTP 410 when read directly and is not treated as confirmed active inventory.

These observations do not establish the company's complete inventory, all of its accounts, property ownership, or whether every listed property is currently bookable. No personal biography, private contact information or session data was retained. Machine-readable evidence is in [operator-research.json](../data/operator-research.json).

## Riyadh and London follow-up

Observed on 28 September 2026. This follow-up used four focused searches and one public Airbnb listing verification, with no login, host contact, private biography, or broad geographic discovery. It found **no additional verified company-affiliated Airbnb host**. Existing account evidence above is unchanged.

The saved [official catalog source](https://api.bnbmehomes.com/api/v1/property/search-property-v2) contains 35 Riyadh and 11 London records. Its recorded external Airbnb URL list is empty. The titles used included the Riyadh DAMAC property (`248699`, `1B-DamacTowerB-M07`), Chelsea Charm by Sloane Square (`277226`), and Parisian-Style Belgravia Home (`277419`). These are official catalog observations, not Airbnb mappings. Direct Chelsea and DAMAC property page reads were inaccessible in the web reader; the [official Belgravia page](https://www.bnbmehomes.com/property/room-1-277419) appeared in search results. A matching title or address alone would remain a candidate, not verified channel evidence.

The [Dorking Airbnb listing](https://www.airbnb.co.uk/rooms/1754387697591693057) is publicly hosted by “Bnbme UK | Premium Stays For UK Travellers”. Its business statement describes UK rentals and property management, without an observed explicit affiliation with Dubai bnbme Holiday Homes. It therefore remains outside the verified account list. Six shown on the host card is a **review count**, not an inventory count. No guessed profile IDs or company association were stored.

Searches performed:

- `site:airbnb.com/rooms "bnbme" "Riyadh" "Damac"`
- `site:airbnb.com/rooms "bnbme" "Chelsea" "Sloane"`
- `Airbnb "bnbme" "Damac" "Riyadh"`
- `Airbnb "bnbme" London "Belgravia"`

This bounded search does not prove an absence of Airbnb accounts or inventory in either market. The machine-readable batch retains the scope, unsuccessful mapping result, catalog examples, and excluded lead.
