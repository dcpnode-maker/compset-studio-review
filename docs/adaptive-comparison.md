# Explicit adaptive comparison

`compset.adaptive` is a pure comparison layer around the existing `similarity.rank_candidates`. It performs no HTTP requests, schedules no work, and writes no files. Its runner must be invoked explicitly by an orchestration/UI layer.

Start with the canonical subject profile. A supplied unverified quality grade remains `unknown`; marketing words never establish an official grade. Missing room type or bedroom evidence on the subject blocks automatic transitions. Missing candidate core evidence remains provisional and is never selected.

The transition gate is **eligible count ≤10**, counted across the audited pool before the target selection limit. A target shortfall alone does not activate adaptation: 67 eligible candidates with target100 remain strict. Each transition rechecks this gate; the first result with more than ten eligible candidates stops further automatic changes.

The possible sequence is:

1. Strict ranking at the explicit circle, matching normalized room type, exact bedrooms, bathroom tolerance0.5, capacity difference tolerance2, and minimum requested guest capacity.
2. Widen bathroom tolerance to a visible cap, default1.0. Missing bathroom evidence remains provisional; the runner never disables this field or fills missing bathrooms. The configurable cap cannot exceed2.0.
3. Remove the relative capacity ceiling while keeping the requested guest-capacity floor. A larger known capacity may qualify; unknown/insufficient capacity cannot qualify.
4. Increase the radius by the configured multiplier, default2, within the explicit maximum, default10km and hard maximum10km. Defaults permit at most6 radius transitions; the configurable maximum is8.

Room type, exact bedrooms and minimum guests never relax. Size/type/building evidence, major amenity categories, reviews and all score weights keep their existing meaning. The runner neither boosts unknown values nor changes observed attributes to improve a match. It may stop with fewer than50–100 candidates; that is an explicit shortfall rather than fabricated coverage.

## Contracts

```python
from compset.adaptive import build_adaptive_plan, run_adaptive_comparison

criteria = {
    "center_lat": 25.1929,
    "center_lng": 55.2716,
    "radius_km": 2,
    "target": 100,
    "min_guest_capacity": 1,  # Exact requested adults; default1 for Order005.
}
policy = {
    "bathroom_tolerance_cap": 1.0,
    "max_radius_km": 10,
    "radius_multiplier": 2,
    "max_radius_steps": 6,
}
plan = build_adaptive_plan(subject, criteria, policy)
result = run_adaptive_comparison(
    subject, full_candidate_attributes, criteria,
    policy=policy,
    discovery_coverage=initial_search_report,
    discovery_callback=bounded_discovery_adapter,
)
```

`build_adaptive_plan` returns the canonical `subject`, `initial_criteria`, explicit `core_rules`, possible `steps`, effective `policy`, and `subject_core_unknown_fields`. Proposed steps are possibilities, not evidence that discovery or relaxation happened.

The optional callback contract is:

```python
def bounded_discovery_adapter(canonical_subject, next_criteria):
    # Root-owned adapter enforces total request budget, pacing and manual pause.
    # Read actual nearby candidates and enrich their full attributes first.
    return {"candidates": observed_candidates, "report": public_coverage_report}
```

The runner calls the adapter only for an executed radius transition and only while the eligible count remains at most ten. The adapter receives independent copies; mutating them cannot weaken the runner's criteria. The adapter owns all network authorization, request limits, cooldown, pause checks, observed templates and report redaction. Return a truthful `report.stop_reason` on an access limit, challenge, pause or exhausted budget: the runner retains any partial returned candidates and immediately stops further transitions. It never cycles routes after403/429. Callback exceptions retain their type only, without storing exception text or secrets.

Without a callback, a radius change only reconsiders already observed outside-circle candidates. Its step records `discovery_performed=False` and `complete_for_requested_cells=False` with state `retained_candidates_only`. An expanded radius does not turn the original small-circle discovery into complete coverage.

The result keeps existing `candidates`, `selected`, `summary`, plus canonical `subject`, final `criteria`, complete raw `candidate_observations`, and `adaptive` metadata. Each executed step contains stage/kind, exact before/after changes, full criteria, before/after eligibility counts, selected/excluded/provisional counts, source discovery coverage and per-candidate outcomes. Each final candidate has `adaptive_history`, including earlier rejection reasons. The final circle explicitly records whether it was automatically expanded and its initial radius.

Exact stable listing IDs deduplicate the ranking pool in first-observation order. Numeric1 and string`"1"` identify the same listing. Every duplicate source observation remains in `candidate_observations`; conflicting versions are not merged or silently substituted. ID-less rows remain separate provisional audit rows. Subject rows remain in raw observations and are excluded from competitor selection. An adapter should enrich a candidate before its first ranking submission; resolving later conflicting evidence is outside this pure layer.

The per-cell discovery report is retained as supplied. Even `complete_for_requested_cells=True` is limited to those source search cells and never establishes all Airbnb inventory. Without supplied coverage, the initial step explicitly reports `not_supplied` and no completeness claim.

## Validation

Run `.venv\Scripts\python.exe -m unittest tests.test_adaptive -v`. Regressions cover the >10 gate and target shortfall, exact10 boundary, secondary-before-radius order, immutable core requirements, guest floor, unknown/provisional exclusion, raw duplicate preservation, subject exclusion, source stops, callback errors, radius/transition caps, unchanged ranking weights and unverified grades. The module and tests perform no live HTTP.
