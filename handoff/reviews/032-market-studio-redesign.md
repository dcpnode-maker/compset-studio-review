# Order 022 integration review

Integrator: Codex root, 28 September 2026. Branch: `phase-0/compset-market-studio`.

The research compares PriceLabs Dynamic Pricing, Market Dashboards, Portfolio Analytics, Revenue Estimator Pro, Listing Optimizer and API with Lighthouse Pricing, Performance, Direct, Distribution and its named legacy insight tools. It distinguishes public vendor claims from current saved-data capabilities. The selected map design retains Leaflet and the existing local draft controller, adds a validated editable polygon beside the existing circle, and keeps map/table/CSV membership synchronized. Named local selections are scoped to source revision and do not rewrite saved decisions or start collection. The hotel calendar now exposes each recorded source on a date; its dense table has one row per recorded offer with search, filter, sort and column controls, and the inspector shows the complete saved offer conditions. CSS adapts Yellow's yellow selected state, compact ribbon, table density, and responsive structure. The concept image is illustrative only.

Independent reviewer: the visual implementation agent did not edit map or hotel JavaScript. It inspected the map and hotel work, returned five map issues and three hotel interaction issues, and personally reran the focused proof after fixes. Findings, corrections, and reviewer commands are in `032-market-studio-map-review.md`. Root inspected the CSS diff and design contract and found no integration blocker. No high-risk Yellow domain code, database schema, or collector behavior changed.

Final executable proof from this shared working tree:

```text
COMPSET_DUAL_REAL_DATA=1 COMPSET_DUAL_BENCH=1 node --test tests/test_*.js
114 tests; 114 passed; 0 failed (28 September 2026)

Python suite: 573 tests; OK (saved output E:\CompSetStudio\data\order022-python-proof.log)
git diff --check: no whitespace error
```

At `http://127.0.0.1:8765/`, the page returned HTTP 200. The server-served `dual-workspace.js` and `dual-workspace.css` matched the on-disk SHA-256 hashes byte for byte (`316E7F861D42253ACFFAFD2BE74C17E205FFC7860F3C0F920C1B2F4890155698` and `9FC2AB10D93668497199A42C10E6A263B1AAFD607E5F3A30AE5196B11163E10F`). The Yellow reservation calendar public tunnel returned HTTP 200, separately from this CompSet branch.

Browser visual and physical touch acceptance are unverified: both the available Chrome and in-app browser providers returned `Browser not available`. The tests prove DOM behavior, state transitions and saved-data invariants, and HTTP proves live asset delivery; neither proves final pixel rendering. Product parity with PriceLabs/Lighthouse is limited by the actual saved source coverage and absent vendor integrations, as detailed in `docs/market-studio-research.md`.
