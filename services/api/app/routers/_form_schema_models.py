"""Request bodies for the form-schema teaching router.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from libs.pipeline.form_schema_section_types import validate_section_type


class AnalyteEntryRequest(BaseModel):
    label: str = ""
    snomed_code: str = ""
    display: str = ""


class FormSchemaItemRequest(BaseModel):
    pattern: str = ""
    entity_text: str = ""
    semantic_tag: str = "finding"
    assertion: str = "present"
    procedure_snomed: str = ""
    procedure_display: str = ""
    analytes: list[AnalyteEntryRequest] = Field(default_factory=list)
    value_placeholder: str = ""


class FormSectionRequest(BaseModel):
    section_id: str = Field(..., min_length=1)
    section_type: str = Field(..., min_length=1)
    label: str = ""
    start_pattern: str = ""
    items: list[FormSchemaItemRequest] = Field(default_factory=list)
    semantic_tags: list[str] = Field(default_factory=list)

    @field_validator("section_type")
    @classmethod
    def _known_section_type(cls, value: str) -> str:
        """Reject a section type the checkbox normaliser cannot dispatch on."""
        return validate_section_type(value)


class CompletenessGroupRequest(BaseModel):
    name: str = Field(..., min_length=1)
    kind: str = ""
    required: bool = True
    min_count: int = 1
    semantic_categories: list[str] = Field(default_factory=list)
    concept_ids: list[int] = Field(default_factory=list)
    members: list[dict[str, Any]] = Field(default_factory=list)
    if_group: dict[str, Any] | None = None
    then_group: dict[str, Any] | None = None


class SaveFormSchemaRequest(BaseModel):
    form_name: str = Field(..., min_length=1)
    sections: list[FormSectionRequest] = Field(..., min_items=1)
    saved_by: str = "unknown"
    status: str = "active"
    organization_id: str = ""
    service_id: str = ""
    organization_name: str = ""
    service_name: str = ""
    completeness_groups: list[CompletenessGroupRequest] = Field(default_factory=list)
    source_text: str = ""


class FingerprintRequest(BaseModel):
    text: str = Field(..., min_length=10)


class GenerateTemplateRequest(BaseModel):
    text: str = Field(..., min_length=10)


class DetectFormRequest(BaseModel):
    text: str = Field(..., min_length=10)
