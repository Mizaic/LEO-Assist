"""Canonical NCDA cohort definitions shared by every analytics endpoint.

See DI-LEO-AI-134 and R-LEO-AI-092.

The helpers below return pure Cypher text fragments -- no Neo4j session,
no side effects. Every analytics router composes its query by inserting
one of these fragments so that /audit/summary, /audit/cancer-stage,
/audit/cancer-type, the overview tile, and mission-control agree on the
meaning of 'confirmed cancer'.

Canonical definition ('confirmed cancer episode'):
    ep.status = 'completed'
    AND coalesce(ep.letter_inferred_benign, false) = false
    AND EXISTS (Encounter)-[:IS_PART_OF {milestone_type IN
        ['diagnosis','diagnosis_confirmed']}]->(ep)

This is the NCDA publication definition: an episode where a cancer
diagnosis has been recorded in the audit period, regardless of whether
the route was a documented 2WW referral.

Suspected-cancer-referral variant ('2WW-route diagnoses'):
    canonical confirmed-cancer clause
    AND EXISTS (Encounter)-[:IS_PART_OF {milestone_type: 'referral'}]->(ep)

This is the narrower cohort surfaced alongside the headline -- it
measures how many confirmed cancers went through a documented 2WW
referral pathway.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Cypher snippets (ep must already be bound in the caller's query)
# ---------------------------------------------------------------------------

_STATUS_AND_BENIGN = (
    "{alias}.status = 'completed' "
    "AND coalesce({alias}.letter_inferred_benign, false) = false"
)

_DIAGNOSIS_MILESTONE_EXISTS = (
    "EXISTS {{ "
    "MATCH (:Encounter)-[__dx:IS_PART_OF]->({alias}) "
    "WHERE __dx.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
    "}}"
)

_REFERRAL_MILESTONE_EXISTS = (
    "EXISTS {{ "
    "MATCH (:Encounter)-[__ref:IS_PART_OF]->({alias}) "
    "WHERE __ref.milestone_type = 'referral' "
    "}}"
)

# Default alias. Every analytics endpoint binds the episode as ``ep``;
# use confirmed_cancer_where("ep") -- or the module-level constant -- to
# get the canonical clause with that alias pre-applied.
_DEFAULT_ALIAS = "ep"


def confirmed_cancer_where(alias: str = _DEFAULT_ALIAS) -> str:
    """Return the canonical NCDA 'confirmed cancer episode' WHERE clause.

    The returned fragment is a Cypher predicate that assumes ``alias``
    is already bound as an ``EpisodeOfCare`` node in the caller's query.
    It can be appended to an existing WHERE / AND chain or used as a
    standalone predicate.

    Example::

        query = (
            "MATCH (p:Patient)-[:HAS_EPISODE]->(ep:EpisodeOfCare) "
            f"WHERE {confirmed_cancer_where('ep')} "
            "RETURN count(ep)"
        )
    """
    status = _STATUS_AND_BENIGN.format(alias=alias)
    diag = _DIAGNOSIS_MILESTONE_EXISTS.format(alias=alias)
    return f"{status} AND {diag}"


def suspected_cancer_referral_where(alias: str = _DEFAULT_ALIAS) -> str:
    """Canonical confirmed-cancer clause PLUS documented 2WW referral.

    Surface this cohort separately as '2WW-route diagnoses' -- it is
    NEVER a synonym for 'confirmed cancer'.
    """
    canonical = confirmed_cancer_where(alias)
    ref = _REFERRAL_MILESTONE_EXISTS.format(alias=alias)
    return f"{canonical} AND {ref}"


CONFIRMED_CANCER_CLAUSE: str = confirmed_cancer_where()
SUSPECTED_CANCER_REFERRAL_CLAUSE: str = suspected_cancer_referral_where()
