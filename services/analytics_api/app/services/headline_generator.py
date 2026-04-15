"""Plain-English headline generator for Pathway Explorer algorithm results.

Each mission has a template that turns raw algorithm output into a
single, confident, jargon-free sentence that a clinician will understand.

Design rule (health-literacy.mdc): short sentences, active voice, no acronyms
on first use, reading age 9-11.  Technical method information is deferred to
the 'How did we work this out?' layer.
"""

from __future__ import annotations

from typing import Any, Dict, List


def generate_headline(
    mission_id: str,
    results: List[Dict[str, Any]],
    scope_label: str,
    detail: str = "summary",
) -> str:
    """Return a plain-English headline for a mission result set.

    Args:
        mission_id: The mission identifier (e.g. "groups", "bottleneck").
        results: Ranked list of result items from the algorithm runner.
        scope_label: Human-readable scope (e.g. "Lung pathway, last 6 months").
        detail: "summary" | "detailed" | "everything".

    Returns:
        A single plain-English sentence describing the key finding.
    """
    generator = _GENERATORS.get(mission_id)
    if generator is None:
        return f"Analysis complete for {scope_label}."
    return generator(results, scope_label, detail)


def generate_method_text(mission_id: str, scope_label: str) -> Dict[str, str]:
    """Return plain-English and technical method text for a mission.

    Returns dict with keys 'plain' and 'technical'.
    """
    templates = _METHOD_TEMPLATES.get(mission_id, {})
    plain = templates.get("plain", "We analysed the patient graph.")
    technical = templates.get("technical", "")
    return {
        "plain": plain.format(scope=scope_label),
        "technical": technical,
    }


def _headline_groups(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    n = len({r.get("community_id") for r in results})
    largest = max((r.get("size", 0) for r in results), default=0)
    if n == 0:
        return f"We did not find enough data to group patients for {scope}."
    if n == 1:
        return (
            f"All patients in {scope} appear to follow a similar pattern. "
            f"No distinct subgroups were found."
        )
    return (
        f"We found {n} natural groups of patients in {scope}. "
        f"The largest group contains {largest} patients."
    )


def _headline_similar(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    n = len(results)
    if n == 0:
        return "We could not find any similar patients in the current data."
    top = results[0] if results else {}
    score = top.get("similarity_score", 0)
    pct = int(score * 100) if score else 0
    return (
        f"We found {n} patients with similar records. "
        f"The closest match shares {pct}% of the same coded conditions."
    )


def _headline_teams(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    n = len(results)
    if n == 0:
        return f"No tightly-linked groups were found in {scope}."
    top = results[0] if results else {}
    label = top.get("label", "")
    coeff = top.get("clustering_coefficient", 0)
    pct = int(coeff * 100) if coeff else 0
    label_part = f" (starting with {label!r})" if label else ""
    return (
        f"We found {n} tightly-linked groups in {scope}{label_part}. "
        f"The most connected group has a {pct}% clustering coefficient."
    )


def _headline_critical(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    if not results:
        return f"No critical nodes were identified in {scope}."
    top = results[0]
    label = top.get("label", "an unknown item")
    score = top.get("score", 0)
    return (
        f"The most important item in {scope} is {label!r}. "
        f"It has an influence score of {score:.2f}, "
        f"meaning changes here affect the widest range of patients."
    )


def _headline_busiest(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    if not results:
        return f"No volume data found for {scope}."
    top = results[0]
    label = top.get("label", "an item")
    degree = top.get("degree", 0)
    return (
        f"The busiest item in {scope} is {label!r}, "
        f"with {degree} connections to other items in the pathway."
    )


def _headline_missing(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    n = len(results)
    if n == 0:
        return f"No obvious missing connections were found in {scope}."
    top = results[0] if results else {}
    a = top.get("node_a_label", "")
    b = top.get("node_b_label", "")
    score = top.get("score", 0)
    pair = f" between {a!r} and {b!r}" if a and b else ""
    return (
        f"We found {n} connections that may be missing in {scope}. "
        f"The most likely missing link{pair} has a prediction score of {score:.2f}."
    )


def _headline_bottleneck(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    n_bottlenecks = sum(1 for r in results if r.get("is_bottleneck", False))
    if not results:
        return f"No pathway data found for {scope}."
    if n_bottlenecks == 0:
        return f"No significant delays were found in {scope}."
    top_bottleneck = next(
        (r for r in results if r.get("is_bottleneck", False)), results[0]
    )
    label = top_bottleneck.get("label", "an unknown step")
    wait = top_bottleneck.get("avg_wait_days", 0)
    patients = top_bottleneck.get("patient_count", 0)
    plural = "s" if n_bottlenecks != 1 else ""
    return (
        f"We found {n_bottlenecks} step{plural} where patients wait the longest "
        f"in {scope}. "
        f"The biggest delay is at {label!r}, "
        f"where the average wait is {wait:.0f} days. "
        f"This affects {patients} patients."
    )


def _headline_gaps(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    n = len(results)
    if n == 0:
        return f"All patients in {scope} appear to be connected to the pathway."
    largest = max((r.get("size", 0) for r in results), default=0)
    return (
        f"We found {n} isolated group{'' if n == 1 else 's'} of patients in {scope} "
        f"who may be falling through the gaps. "
        f"The largest isolated group contains {largest} patients."
    )


def _headline_circles(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    n = len(results)
    if n == 0:
        return f"No circular patterns were found in {scope}."
    largest = max((r.get("size", 0) for r in results), default=0)
    return (
        f"We found {n} circular pattern{'' if n == 1 else 's'} in {scope} "
        f"where patients or conditions loop back on themselves. "
        f"The largest loop involves {largest} items."
    )


def _headline_bridges(
    results: List[Dict[str, Any]],
    scope: str,
    detail: str,
) -> str:
    if not results:
        return f"No bridge conditions were identified in {scope}."
    top = results[0]
    label = top.get("label", "an unknown condition")
    score = top.get("score", 0)
    n = len(results)
    return (
        f"We found {n} condition{'' if n == 1 else 's'} that act as "
        f"bridges between different parts of the pathway in {scope}. "
        f"The most important bridge is {label!r} "
        f"with a centrality score of {score:.3f}."
    )


# -- Dispatch table ----------------------------------------------------------

_GENERATORS = {
    "groups": _headline_groups,
    "similar": _headline_similar,
    "teams": _headline_teams,
    "critical": _headline_critical,
    "busiest": _headline_busiest,
    "missing": _headline_missing,
    "bottleneck": _headline_bottleneck,
    "gaps": _headline_gaps,
    "circles": _headline_circles,
    "bridges": _headline_bridges,
}

# -- Method text templates (plain English + technical note) ------------------

_METHOD_TEMPLATES: Dict[str, Dict[str, str]] = {
    "groups": {
        "plain": (
            "We looked at every patient's coded conditions and grouped patients "
            "who share similar combinations of codes. We did not tell the system "
            "what the groups should look like -- it found the natural clusters in "
            "the data on its own. Scope: {scope}."
        ),
        "technical": (
            "Technical note: Leiden community detection algorithm on a "
            "patient-condition bipartite graph projection (GDS). "
            "Resolution parameter: default 1.0."
        ),
    },
    "similar": {
        "plain": (
            "We compared this patient's mix of coded conditions with every other "
            "patient in {scope} and found the patients with the most overlap. "
            "A higher similarity score means more conditions in common."
        ),
        "technical": (
            "Technical note: K-nearest neighbours (KNN) with Jaccard similarity "
            "on the patient-condition bipartite projection (GDS). k=20."
        ),
    },
    "teams": {
        "plain": (
            "We looked at which conditions always appear together in the same "
            "patients, and found the groups that are most tightly linked. "
            "A higher clustering score means conditions in the group almost "
            "always appear together. Scope: {scope}."
        ),
        "technical": (
            "Technical note: Triangle Count and Local Clustering Coefficient "
            "on the condition co-occurrence graph projection (GDS)."
        ),
    },
    "critical": {
        "plain": (
            "We worked out which conditions have the most influence over other "
            "conditions in {scope}. When a condition appears on many different "
            "patients' records and connects to many other conditions, we call it "
            "central. Conditions that are central affect more patients if they "
            "are missed or miscoded."
        ),
        "technical": (
            "Technical note: PageRank algorithm on the condition "
            "co-occurrence graph projection (GDS). Damping factor: 0.85."
        ),
    },
    "busiest": {
        "plain": (
            "We counted how many other conditions each condition connects to in "
            "{scope}. Conditions with more connections appear on more patients "
            "and link to a wider range of other coded conditions."
        ),
        "technical": (
            "Technical note: Degree Centrality on the condition co-occurrence "
            "graph projection (GDS)."
        ),
    },
    "missing": {
        "plain": (
            "We looked for pairs of conditions that often appear together in "
            "similar patients but are rarely coded together in {scope}. "
            "These may be genuine co-occurrences that have been missed."
        ),
        "technical": (
            "Technical note: Adamic-Adar link prediction on the condition "
            "co-occurrence graph projection (GDS)."
        ),
    },
    "bottleneck": {
        "plain": (
            "We looked at every patient's journey through the pathway in {scope} "
            "and measured how long patients waited at each step. Steps where "
            "many patients pass through AND where waits are longest are the "
            "biggest bottlenecks."
        ),
        "technical": (
            "Technical note: Weighted shortest path and betweenness centrality "
            "on the patient-journey projection. Wait times from EpisodeOfCare "
            "milestone timestamps (IS_PART_OF relationship with milestone_type). "
            "GDS."
        ),
    },
    "gaps": {
        "plain": (
            "We checked whether all patients in {scope} are connected to the "
            "main pathway. Patients whose records do not link to the rest of "
            "the pathway may be missing follow-up or have incomplete coding."
        ),
        "technical": (
            "Technical note: Weakly Connected Components (WCC) on the "
            "patient-condition bipartite projection (GDS). Components with "
            "fewer than 5 nodes are considered isolated."
        ),
    },
    "circles": {
        "plain": (
            "We looked for patterns where patients or conditions loop back to "
            "earlier states in {scope}. Circular patterns can indicate repeated "
            "referrals, recurring conditions, or incomplete pathway resolution."
        ),
        "technical": (
            "Technical note: Strongly Connected Components (SCC) on the "
            "patient-journey projection (GDS). Components with 2 or more "
            "members are considered circular."
        ),
    },
    "bridges": {
        "plain": (
            "We found conditions that act as bridges between different groups "
            "of conditions in {scope}. Bridge conditions connect areas of the "
            "pathway that would otherwise be separate. When a bridge condition "
            "is missed, it can break links between different parts of a "
            "patient's care record."
        ),
        "technical": (
            "Technical note: Betweenness Centrality on the condition "
            "co-occurrence graph projection (GDS). Scores normalised by "
            "graph size."
        ),
    },
}
