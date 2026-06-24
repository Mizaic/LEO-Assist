"""Pydantic models for the audit template system.

Atlas trace:
  DO: DO-3775670C
  DI: DI-64CA7740, DI-758B73A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3775670C")
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Tile types
# ---------------------------------------------------------------------------

TileType = Literal[
    "bar_chart",
    "line_chart",
    "kpi_strip",
    "table",
    "interval_plot",
    "text",
]

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


class TileLayout(BaseModel):
    x: int = Field(ge=0, description="Column index (react-grid-layout col)")
    y: int = Field(ge=0, description="Row index (react-grid-layout row)")
    w: int = Field(ge=1, le=12, description="Column span")
    h: int = Field(ge=1, description="Row span")


# ---------------------------------------------------------------------------
# AuditTile
# ---------------------------------------------------------------------------


class AuditTileBase(BaseModel):
    label: str = Field(max_length=120)
    tile_type: TileType
    metric_id: str = Field(
        max_length=80,
        description="References a metric_id in METRIC_REGISTRY",
    )
    param_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Caller-configurable param values for the metric param_schema",
    )
    layout: TileLayout


class AuditTileCreate(AuditTileBase):
    tile_id: Optional[str] = None


class AuditTile(AuditTileBase):
    tile_id: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# AuditTemplate
# ---------------------------------------------------------------------------


class AuditTemplateCreate(BaseModel):
    title: str = Field(max_length=200)
    tiles: list[AuditTileCreate] = Field(default_factory=list)


class AuditTemplateUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    tiles: Optional[list[AuditTileCreate]] = None


class AuditTemplate(BaseModel):
    template_id: str
    title: str
    version: int
    status: Literal["draft", "published", "archived"]
    tiles: list[AuditTile]
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# TemplateAssignment
# ---------------------------------------------------------------------------


class TemplateAssignmentCreate(BaseModel):
    template_id: str
    scope_type: Literal["org", "group"]
    scope_id: str


class TemplateAssignment(BaseModel):
    assignment_id: str
    template_id: str
    version: int
    scope_type: Literal["org", "group"]
    scope_id: str
    published_at: datetime
    published_by: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Metric run request / response
# ---------------------------------------------------------------------------


class MetricRunRequest(BaseModel):
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Caller-supplied param values to merge with the metric defaults",
    )


class MetricRunResponse(BaseModel):
    metric_id: str
    columns: list[str]
    rows: list[list[Any]]
