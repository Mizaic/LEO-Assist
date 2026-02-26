"""Shared domain configuration library.

Loads clinical domain definitions from FHIR ValueSets stored in the
Knowledge Graph. Used by Coding Worker and Analysis Worker to know
which domains to process and their associated SNOMED ancestor concepts.

Replaces the static JSON config files from auditor_2 and the
DomainRegistry from visual-report-builder.
"""

from libs.domain_config.registry import DomainRegistry, DomainDefinition

__all__ = ["DomainRegistry", "DomainDefinition"]
