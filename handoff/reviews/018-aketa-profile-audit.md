# Order 009 independent profile-audit and price-label review

Reviewer: Codex sub-agent `/root/ota_review`. Implementation owner: `/root/ota_mmt_agoda`; audit/import owner: root. The reviewer changed only this review file. No production code or data changes, remote requests, browser actions, process launches, bookings or logins were performed. The HTTP checks below read the existing loopback dashboard.

**Accepted for the narrow parser repair, saved evidence interpretation and published result at the hashes below. No open finding.** This does not establish sellability of legacy profiles or complete OTA coverage.

## Source change and personally executed proof

Order 009 permits two explicit source labels. The production diff adds exact recognition of `['Per night before taxes & fees']` alongside the existing `['Per night before taxes']`. The new label sets both `taxes_included=false` and `fees_included=false`; the old label retains unknown fee inclusion. Tax/fee amounts remain null. The change does not alter source identity, stay/party matching, currency, numeric agreement, availability or precision gates.

Before the owner changed the parser, I personally reparsed `data/hotels/aketa/profile-audit/agoda-20260928T065647650951Z.json`: it returned `unknown/no_verified_offer_prices` and zero rates despite HTTP 200, no stop condition and an otherwise matched response. The saved source contains the new explicit label.

After source freeze, I personally ran:

```text
.venv\Scripts\python.exe -m unittest tests.test_hotel_mmt_agoda tests.test_hotel_portfolio_review -q
Ran 48 tests in 2.031s — OK.
```

This includes all 31 adapter tests and 17 independent contract/job/SQLite tests. This review does not present another agent's full-suite execution as reviewer-executed proof.

I independently reparsed the unchanged actual capture through `hotel_jobs.parse_source`, including the shared contract. Assertions establish:

- **14 accepted indicative offers across five room types**, with minimum **INR 5,169**, for canonical Agoda property **110205**, 28–29 September 2026, one adult, one room and zero children.
- Every accepted decimal amount agrees with both the numeric field and displayed number at the saved JSON provenance path. Every accepted offer has the observed `Per night before taxes & fees` label.
- Prices remain `ota_display_price`, `nightly_room_rate` and `displayed_integer`, with `direct_supplier_quote=false`. Both tax and fee inclusion are false; their amounts remain unknown. No precise final checkout price is asserted.
- The minimum is the Premium Single Room with breakfast. Membership, automatically applied coupon, payment and cancellation terms remain attached.
- The original raw bytes and SHA-256 remain unchanged after parsing and all mutation checks.

Eighteen mutations of copies of that real capture—missing/malformed/unknown/conflicting labels; wrong returned property/name/guest count; adult, room, child and date mismatches; alternate legacy property ID `27746358`; disagreeing numeric/display amounts; and HTTP 429—produce no accepted rates and no verified unavailable result. This specifically prevents the new label from weakening property or stay attribution.

I also reparsed the older real packaged Agoda capture (`agoda-20260928T054814068388Z.json`): it still returns 14 rates with tax inclusion false and fee inclusion null. A separate controlled mutation of the fresh capture to the old supported label gives the same fee-unknown behavior. The new explicit fee exclusion is not applied retroactively to old evidence.

## Import, history and local publication

The original `canonical-agoda-observation.json` remains an unknown interpretation with zero rates. The separate corrected interpretation contains 14 indicative rates. Read-only SQLite inspection confirms that the fresh capture ID `efda34b53d8fdf8753f7c741eebe5495e00761fce0d0a66b6dfe922ba7b3973d` has the corrected result and that older Agoda amounts, including INR 5,182 with unknown fee inclusion, remain in history. At inspection, Agoda had five distinct captures and eight interpretations; no old source record was rewritten to the new price.

The published job `d1b97cf80d17273ed496810258cf6846b90935ac3fb9dd93605a550fd0d32952` retains 150 source/date cells: **31 indicative, one verified contextual unavailable, 118 unknown and zero exact supplier quote cells**. Its 51 price rows include the 14 current Agoda observations, minimum INR 5,169 with taxes and fees excluded. The prior stay-specific unavailable observation remains separate.

I independently read `/api/hotels/aketa` and `/exports/hotel-aketa-rates.csv` from the existing `127.0.0.1:8765` runtime. Both returned HTTP 200, `Cache-Control: no-store` and exact saved-file bytes. No server restart or browser inspection was used.

## Duplicate-profile scope

I inspected `docs/hotel-aketa-profile-audit.md`, `profiles.json` and the saved legacy Agoda UI observation. They keep the canonical Agoda ID 110205 separate from legacy ID 27746358 and the current Expedia ID 92850456 separate from legacy ID 133767894. Hotels.com is explicitly an Expedia inventory mirror; language/country URLs are not counted as additional physical hotels. Canonical registry mappings were not changed by this repair.

The saved legacy Agoda observation marks context unverified, rates empty and sale status unknown because displayed controls and navigation dates did not consistently establish a completed room-rate search. The audit correctly avoids calling that profile sold out, closed or currently sellable. Indexed historical prices and recommendation prices do not become current offers. Other profiles retain their explicit unknown/access-blocked status. This reviewer did not repeat the remote identity discovery or independently establish legacy sellability; acceptance here covers the evidence separation and conservative claims in the saved audit.

## Reviewed identity

| File | SHA-256 |
| --- | --- |
| `compset/hotel_mmt_agoda.py` | `15aa4d1192d37dc86d1cb4b07a938968f41079af6a92e47ea5fe15116c7ec9a7` |
| `tests/test_hotel_mmt_agoda.py` | `868281700eff4aad369a428de08c7ad883f433a84c3b1c8c8dcf5e8737e04b8d` |
| `docs/hotel-mmt-agoda.md` | `9e3dbf6c8bdfbb0d7ccb1cb9fcebe9445146060a5c1b965e94cbddf0805fd424` |
| `docs/hotel-aketa-profile-audit.md` | `aed91263d20cac840eabe69f617ec38dcfedd9dd83f0eadd763584c91fe09db3` |
| `data/hotels/aketa/profile-audit/agoda-20260928T065647650951Z.json` | `c30e46b82bbcc69c53560daf6aee49b5d6dbe131c12b31d586e8c42c9f30bd16` |
| `data/hotels/aketa/profile-audit/profiles.json` | `95810e543bb95493b0525ce867e31b5359c3022ee2d1fb3158a46d63594a9c38` |
| `data/hotels/aketa/profile-audit/legacy-agoda-ui-observation.json` | `cda1978324ec670555f94d1a7254d6e7ca8988cd026a4815e50d506172436ffa` |
| `data/hotels/aketa/profile-audit/canonical-agoda-observation.json` | `fa311253cd5fb4cf3b0ab045aa9db5a2313b0015e80eb6b339edf9a91b075bee` |
| `data/hotels/aketa/profile-audit/canonical-agoda-observation-corrected.json` | `dd144f0db76b2369fca706bb3c62781392d7d7cb47a3478df7d79bb9fb2540ec` |
| `data/hotel-pipelines/latest.json` | `5e8982e6f258f757126004270d03cb8bbe8c72d00b1ee7b9fee2ee97e68a7e0f` |
| `data/hotels/aketa/latest.json` | `1a2151f13c32a6f268647d445adccfde08c684bb2f8181081684483b55039776` |
| `data/hotels/aketa/rates.csv` | `97eee299e27bf84326db39ceed5982c1e25468d9065af4d6b0d9ce6f7262b3ed` |
