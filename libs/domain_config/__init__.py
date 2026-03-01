"""FHIR-driven domain configuration registry.

Loads clinical domains (cancer types, referrals, treatment, etc.)
from FHIR ValueSet resources stored in the Knowledge Graph.

Ported from VRB clinical-ai/app/configs/domain_registry.py.
"""

from libs.domain_config.registry import DomainRegistry, NCDAConcept, NCDADomain

__all__ = ["DomainRegistry", "NCDAConcept", "NCDADomain"]
