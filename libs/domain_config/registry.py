"""SNOMED mapping config loader and domain registry.

All config is loaded via from_fhir() at startup from FHIR ValueSet
resources stored in the Knowledge Graph. Falls back to predefined
domain configs when FHIR data is unavailable.

Ported from VRB clinical-ai/app/configs/domain_registry.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Clinical abbreviation expansion ──────────────────────────────────────

_CLINICAL_ABBREVS = [
    ("gastrointestinal", "GI"),
    ("lower gastrointestinal", "lower GI"),
    ("upper GI (gastrointestinal)", "upper GI"),
    ("urological", "urology"),
    ("haematology malignancy", "haematology"),
    ("colorectal", "bowel"),
    ("gynaecological", "gynae"),
    ("two week wait", "2ww"),
    ("2 week wait", "2ww"),
]

_DOMAIN_EXTRA_TERMS: Dict[str, List[str]] = {
    "fast_track_referrals": [
        "fast track referral",
        "fast track",
        "2ww",
        "2 week wait",
        "two week wait",
        "suspected cancer referral",
        "urgent cancer referral",
        "PRISM 2WW",
    ],
}


def _dedupe_terms(terms: List[str]) -> List[str]:
    seen: set = set()
    unique: List[str] = []
    for t in terms:
        low = t.lower()
        if low not in seen:
            seen.add(low)
            unique.append(t)
    return unique


def _expand_abbreviations(term: str) -> List[str]:
    extras: List[str] = []
    low = term.lower()
    for full_form, abbrev in _CLINICAL_ABBREVS:
        if full_form.lower() in low:
            expanded = low.replace(full_form.lower(), abbrev.lower())
            extras.append(expanded)
        if abbrev.lower() in low and full_form.lower() not in low:
            expanded = low.replace(abbrev.lower(), full_form.lower())
            extras.append(expanded)
    if "(" in term and term.rstrip().endswith(")"):
        stripped = term[: term.rindex("(")].strip()
        if len(stripped) > 5:
            extras.append(stripped)
    return extras


# ── Data classes ─────────────────────────────────────────────────────────


@dataclass
class NCDAConcept:
    """A single SNOMED concept from a mapping file."""

    term: str
    concept_id: int
    preferred_term: str
    semantic_tag: Optional[str]
    score: float
    llm_disambiguated: bool
    domain: str
    guideline_synonyms: List[str] = field(default_factory=list)
    cancer_category: Optional[str] = None
    category: Optional[str] = None


@dataclass
class NCDADomain:
    """Configuration for a single NCDA domain."""

    name: str
    file: str
    description: str
    time_window_months: Optional[int] = None
    most_recent_only: bool = False
    semantic_tags: List[str] = field(default_factory=list)
    milestone_type: Optional[str] = None


# ── Predefined domain configs (fallback) ─────────────────────────────────

NCDA_DOMAIN_CONFIGS: Dict[str, NCDADomain] = {
    "cancer_types": NCDADomain(name="cancer_types", file="snomed_ncda_cancer_types_mapping.json", description="Cancer type diagnosis concepts", semantic_tags=["Disease"], milestone_type="diagnosis"),
    "fast_track_referrals": NCDADomain(name="fast_track_referrals", file="snomed_ncda_fast_track_referrals_mapping.json", description="Fast-track (2WW) referral procedures", semantic_tags=["Procedure"], milestone_type="referral"),
    "treatment": NCDADomain(name="treatment", file="snomed_ncda_treatment_mapping.json", description="Cancer treatment procedures", semantic_tags=["Procedure"], milestone_type="treatment"),
    "symptoms": NCDADomain(name="symptoms", file="snomed_ncda_symptom_mappings.json", description="Presenting symptoms", time_window_months=12, semantic_tags=["Clinical_finding", "Situation"]),
    "comorbidities": NCDADomain(name="comorbidities", file="snomed_ncda_comorbidities_mappings.json", description="Comorbid conditions", semantic_tags=["Clinical_finding", "Disease"]),
    "physical_signs": NCDADomain(name="physical_signs", file="snomed_ncda_physical_signs_mappings.json", description="Physical examination findings", semantic_tags=["Clinical_finding"]),
    "investigations": NCDADomain(name="investigations", file="snomed_ncda_primary_care_investigations_mappings.json", description="Primary care investigations", semantic_tags=["Procedure"]),
    "lifestyle_factors": NCDADomain(name="lifestyle_factors", file="snomed_ncda_lifestyle_factors_mapping.json", description="Lifestyle and risk factors", semantic_tags=["Clinical_finding", "Situation"]),
    "family_history": NCDADomain(name="family_history", file="snomed_ncda_family_history_mapping.json", description="Family history of cancer", semantic_tags=["Situation"]),
    "cancer_risk_factors": NCDADomain(name="cancer_risk_factors", file="snomed_ncda_cancer_risk_factors_mapping.json", description="Cancer risk factors", semantic_tags=["Clinical_finding"]),
    "place_of_presentation": NCDADomain(name="place_of_presentation", file="snomed_ncda_place_of_first_presentation_mapping.json", description="Place of first presentation", semantic_tags=["Environment"]),
    "seen_by_specialist": NCDADomain(name="seen_by_specialist", file="snomed_ncda_seen_by_specialist_mapping.json", description="Seen by specialist encounters", semantic_tags=["Procedure"], milestone_type="specialist_visit"),
    "referral_outcomes": NCDADomain(name="referral_outcomes", file="snomed_ncda_referral_outcomes_mapping.json", description="Referral outcome codes", semantic_tags=["Situation"]),
    "screening": NCDADomain(name="screening", file="snomed_ncda_screening_mapping.json", description="NHS cancer screening programmes — offered/declined/completed situations, FIT/FOB/sigmoidoscopy results, lung/bowel/breast/cervical programme findings, DNA events, eligibility", semantic_tags=["Procedure", "Situation", "Clinical_finding"]),
    "observable_entities": NCDADomain(name="observable_entities", file="snomed_ncda_observable_entities_mapping.json", description="Observable entity measurements", semantic_tags=["Observable_entity"]),
    "ethnicity": NCDADomain(name="ethnicity", file="snomed_ncda_ethnicity_mapping.json", description="Ethnicity codes", semantic_tags=["Ethnic_group"]),
    "housebound_status": NCDADomain(name="housebound_status", file="snomed_ncda_housebound_status_mapping.json", description="Housebound status", semantic_tags=["Situation"]),
    "living_arrangement": NCDADomain(name="living_arrangement", file="snomed_ncda_living_arrangement_mapping.json", description="Living arrangement", semantic_tags=["Situation"]),
    "communication_difficulty": NCDADomain(name="communication_difficulty", file="snomed_ncda_communication_difficulty_mapping.json", description="Communication difficulties", semantic_tags=["Clinical_finding"]),
    "english_language_competency": NCDADomain(name="english_language_competency", file="snomed_ncda_english_language_competency_mapping.json", description="English language competency", semantic_tags=["Clinical_finding"]),
    "performance_status": NCDADomain(name="performance_status", file="snomed_ncda_who_performance_status_mapping.json", description="WHO performance status", semantic_tags=["Clinical_finding"]),
    "temporal_analysis": NCDADomain(name="temporal_analysis", file="snomed_ncda_temporal_analysis_mapping.json", description="Temporal analysis concepts", semantic_tags=["Situation"]),
}


# ── Registry ─────────────────────────────────────────────────────────────


class DomainRegistry:
    """Loads and caches all SNOMED mapping configs."""

    _instance: Optional[DomainRegistry] = None

    def __init__(self) -> None:
        self._concepts: Dict[str, List[NCDAConcept]] = {}
        self._concept_by_id: Dict[int, NCDAConcept] = {}
        self._domain_configs: Dict[str, NCDADomain] = {}
        self._loaded = False

    @classmethod
    def get_instance(cls) -> DomainRegistry:
        if cls._instance is None:
            raise RuntimeError(
                "DomainRegistry not initialised. "
                "Call DomainRegistry.from_fhir() at startup."
            )
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # ── FHIR loading ──────────────────────────────────────────────

    @classmethod
    def from_fhir(
        cls,
        valuesets: Dict[str, Dict],
        conceptmaps: Optional[Dict[str, Dict]] = None,
    ) -> DomainRegistry:
        """Build a DomainRegistry from FHIR ValueSet and ConceptMap resources."""
        registry = cls()

        for vs_id, vs in valuesets.items():
            domain_name = cls._domain_name_from_valueset(vs)
            if not domain_name:
                continue

            domain_config = cls._parse_domain_config(vs, domain_name)
            registry._domain_configs[domain_name] = domain_config

            concepts: List[NCDAConcept] = []
            for include in (vs.get("compose") or {}).get("include") or []:
                for concept_entry in include.get("concept") or []:
                    code = concept_entry.get("code", "")
                    display = concept_entry.get("display", "")
                    try:
                        concept_id = int(code)
                    except (ValueError, TypeError):
                        concept_id = 0

                    synonyms: List[str] = []
                    for desig in concept_entry.get("designation") or []:
                        use = desig.get("use") or {}
                        if use.get("code") == "synonym":
                            val = desig.get("value", "")
                            if val:
                                synonyms.append(val)

                    c = NCDAConcept(
                        term=display,
                        concept_id=concept_id,
                        preferred_term=display,
                        semantic_tag=None,
                        score=1.0,
                        llm_disambiguated=False,
                        domain=domain_name,
                        guideline_synonyms=synonyms,
                    )
                    concepts.append(c)
                    registry._concept_by_id[concept_id] = c

            registry._concepts[domain_name] = concepts

        registry._loaded = True
        logger.info(
            "DomainRegistry loaded from FHIR: %d domains, %d total concepts",
            len(registry._domain_configs),
            sum(len(v) for v in registry._concepts.values()),
        )

        cls._instance = registry
        return registry

    @classmethod
    def from_defaults(cls) -> DomainRegistry:
        """Build a registry from predefined domain configs (no FHIR data)."""
        registry = cls()
        registry._domain_configs = dict(NCDA_DOMAIN_CONFIGS)
        registry._loaded = True
        cls._instance = registry
        logger.info(
            "DomainRegistry loaded from defaults: %d domains",
            len(registry._domain_configs),
        )
        return registry

    @staticmethod
    def _domain_name_from_valueset(vs: Dict) -> Optional[str]:
        vs_id = vs.get("id", "")
        if vs_id.startswith("ncda-"):
            return vs_id[5:].replace("-", "_")
        return None

    @staticmethod
    def _parse_domain_config(vs: Dict, domain_name: str) -> NCDADomain:
        milestone_type: Optional[str] = None
        time_window_months: Optional[int] = None
        semantic_tags: List[str] = []

        for ext in vs.get("extension") or []:
            if ext.get("url", "").endswith("/domain-config"):
                for sub in ext.get("extension") or []:
                    sub_url = sub.get("url", "")
                    if sub_url == "milestoneType":
                        milestone_type = sub.get("valueCode")
                    elif sub_url == "timeWindowMonths":
                        time_window_months = sub.get("valueInteger")
                    elif sub_url == "semanticTag":
                        tag = sub.get("valueString")
                        if tag:
                            semantic_tags.append(tag)

        return NCDADomain(
            name=domain_name,
            file="",
            description=vs.get("description", ""),
            milestone_type=milestone_type,
            time_window_months=time_window_months,
            semantic_tags=semantic_tags,
        )

    # ── Accessors ─────────────────────────────────────────────────

    def get_all_domains(self) -> List[str]:
        return list(self._domain_configs.keys())

    def get_domain_config(self, domain: str) -> Optional[NCDADomain]:
        return self._domain_configs.get(domain)

    def get_domain_concepts(self, domain: str) -> List[NCDAConcept]:
        return self._concepts.get(domain, [])

    def get_concept_ids(self, domain: str) -> List[int]:
        return [c.concept_id for c in self._concepts.get(domain, [])]

    def get_concept_by_id(self, concept_id: int) -> Optional[NCDAConcept]:
        return self._concept_by_id.get(concept_id)

    def get_search_terms(self, domain: str) -> List[str]:
        terms: List[str] = []
        for concept in self._concepts.get(domain, []):
            terms.append(concept.preferred_term)
            terms.extend(concept.guideline_synonyms)
            terms.extend(_expand_abbreviations(concept.preferred_term))
        terms.extend(_DOMAIN_EXTRA_TERMS.get(domain, []))
        return _dedupe_terms(terms)

    def get_milestone_domains(self) -> Dict[str, NCDADomain]:
        return {
            name: cfg
            for name, cfg in self._domain_configs.items()
            if cfg.milestone_type
        }
