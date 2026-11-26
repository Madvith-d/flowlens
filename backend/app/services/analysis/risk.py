"""Explainable risk scoring (Phase 6A).

The risk score is a *versioned, configurable heuristic that prioritizes change
impact*. It is explicitly **not** a probability of failure; every response
carries a factor breakdown, the exact weights applied, and caveats that state
what was included, what was excluded, and why.

Factor model (version from ``risk_score_version``; default weights follow
phases.md §20):

* ``upstream_reachable_dependents`` (default 35%) — union of nodes that
  (transitively) depend on the targets, normalized against a configurable cap.
* ``in_degree_centrality`` (default 20%) — largest target in-degree relative
  to the graph's maximum in-degree.
* ``downstream_breadth`` (default 15%) — union of nodes the targets
  (transitively) depend on, normalized against the same cap.
* ``public_entry_point`` (default 15%) — fraction of targets that are
  module-level definitions or modules (structural proxies for "public API").
* ``coverage_deficiency`` (default 15%) — only when coverage data is present
  (Phase 7A); when absent the factor is excluded, the remaining weights are
  renormalized, and the fact is disclosed via ``coverage_included: false``
  plus a caveat.

Custom weights are renormalized to sum to 1 for the factors actually
included, so the score stays comparable across configurations. All inputs are
bounded, so the score is deterministic and always within 0–100.
"""

import logging

logger = logging.getLogger("flowlens.risk")

FACTOR_UPSTREAM = "upstream_reachable_dependents"
FACTOR_IN_DEGREE = "in_degree_centrality"
FACTOR_DOWNSTREAM = "downstream_breadth"
FACTOR_PUBLIC_ENTRY = "public_entry_point"
FACTOR_COVERAGE = "coverage_deficiency"

FACTOR_LABELS = {
    FACTOR_UPSTREAM: "Upstream reachable dependents",
    FACTOR_IN_DEGREE: "In-degree centrality",
    FACTOR_DOWNSTREAM: "Downstream dependency breadth",
    FACTOR_PUBLIC_ENTRY: "Public API / entry-point indicator",
    FACTOR_COVERAGE: "Coverage deficiency",
}

# Caveat text reproduced on every risk payload.
_CAVEAT_NOT_PROBABILITY = (
    "Risk is a change-impact prioritization heuristic and is NOT a probability"
    " of failure."
)
_CAVEAT_NO_COVERAGE = (
    "No coverage data is attached to this analysis; the coverage factor was"
    " excluded and the remaining weights were renormalized accordingly."
)
_CAVEAT_STATIC_RESOLUTION = (
    "Unresolved and ambiguous references are excluded from the dependency graph"
    " and therefore from this score."
)
_CAVEAT_METRICS_BUDGET = (
    "The dependency graph exceeds the configured metrics node budget;"
    " reachability factors were excluded from scoring and the remaining weights"
    " were renormalized."
)


def compute_risk(
    *,
    version: str,
    weights: dict[str, float],
    normalization_cap: int,
    upstream_union_size: int | None,
    downstream_union_size: int | None,
    max_target_in_degree: int | None,
    graph_max_in_degree: int,
    public_entry_fraction: float,
    coverage_present: bool,
    coverage_deficiency: float | None = None,
) -> dict:
    """Deterministic, explainable 0–100 risk score with factor breakdown.

    ``upstream_union_size``/``downstream_union_size``/``max_target_in_degree``
    are ``None`` when the metrics node budget was exceeded — the factor is then
    excluded rather than estimated.
    """
    raw_factors: dict[str, dict] = {
        FACTOR_UPSTREAM: {
            "raw_value": upstream_union_size,
            "normalized": (
                min(upstream_union_size / normalization_cap, 1.0)
                if upstream_union_size is not None
                else None
            ),
            "description": (
                f"Size of the union of transitive dependents of the targets,"
                f" normalized against a cap of {normalization_cap} nodes."
            ),
        },
        FACTOR_IN_DEGREE: {
            "raw_value": max_target_in_degree,
            "normalized": (
                min(max_target_in_degree / graph_max_in_degree, 1.0)
                if max_target_in_degree is not None and graph_max_in_degree > 0
                else (0.0 if max_target_in_degree == 0 else None)
            ),
            "description": (
                "Largest direct-dependents count among the targets relative to"
                " the maximum in-degree in this analysis graph."
            ),
        },
        FACTOR_DOWNSTREAM: {
            "raw_value": downstream_union_size,
            "normalized": (
                min(downstream_union_size / normalization_cap, 1.0)
                if downstream_union_size is not None
                else None
            ),
            "description": (
                f"Size of the union of transitive dependencies of the targets,"
                f" normalized against a cap of {normalization_cap} nodes."
            ),
        },
        FACTOR_PUBLIC_ENTRY: {
            "raw_value": public_entry_fraction,
            "normalized": min(max(public_entry_fraction, 0.0), 1.0),
            "description": (
                "Fraction of targets that are module-level definitions or"
                " modules (a structural proxy for public API exposure)."
            ),
        },
        FACTOR_COVERAGE: {
            "raw_value": coverage_deficiency if coverage_present else None,
            "normalized": coverage_deficiency if coverage_present else None,
            "description": (
                "Uncovered executable fraction among the targets' spans; only"
                " included when a Coverage.py artifact has been attached."
            ),
        },
    }

    included = {
        key: entry["normalized"] is not None and weights.get(key, 0) > 0
        for key, entry in raw_factors.items()
    }
    active_weight_sum = sum(weights.get(key, 0.0) for key in raw_factors if included[key])
    if active_weight_sum <= 0:
        included = {FACTOR_PUBLIC_ENTRY: True}
        weights = {FACTOR_PUBLIC_ENTRY: 1.0}
        active_weight_sum = 1.0

    factors: list[dict] = []
    weighted_total = 0.0
    for key in (FACTOR_UPSTREAM, FACTOR_IN_DEGREE, FACTOR_DOWNSTREAM, FACTOR_PUBLIC_ENTRY, FACTOR_COVERAGE):
        entry = raw_factors[key]
        use = included[key]
        applied_weight = (weights.get(key, 0.0) / active_weight_sum) if use else 0.0
        if use:
            weighted_total += applied_weight * entry["normalized"]
        factors.append(
            {
                "key": key,
                "label": FACTOR_LABELS[key],
                "weight": round(applied_weight, 4),
                "raw_value": entry["raw_value"],
                "normalized_value": round(entry["normalized"], 4) if use else None,
                "included": use,
                "description": entry["description"],
            }
        )

    score = int(100 * weighted_total + 0.5)
    score = max(0, min(100, score))

    caveats = [_CAVEAT_NOT_PROBABILITY, _CAVEAT_STATIC_RESOLUTION]
    if not coverage_present:
        caveats.append(_CAVEAT_NO_COVERAGE)
    if upstream_union_size is None or downstream_union_size is None or max_target_in_degree is None:
        caveats.append(_CAVEAT_METRICS_BUDGET)

    return {
        "score": score,
        "version": version,
        "coverage_included": coverage_present,
        "factors": factors,
        "caveats": caveats,
    }
