"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-A23404E0
  DI: DI-23822663, DO-671C15BF
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A23404E0")
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from libs.staging.tnm_parser import TNMComponents, parse_tnm_triplet

RULES_DIR = Path("configs/staging_rules")
_EXPLICIT_STAGE_RE = re.compile(
    r"\b(?:stage\s*)?([0-4]|i{1,3}|iv)(?:\s*([abc]))?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StagingResult:
    cancer_stage: str
    cancer_stage_raw: str
    cancer_stage_group: str
    tnm_t: str
    tnm_n: str
    tnm_m: str
    staging_system: str
    staging_source: str
    staging_confidence: float


def _default_unknown() -> StagingResult:
    return StagingResult(
        cancer_stage="unknown",
        cancer_stage_raw="",
        cancer_stage_group="",
        tnm_t="",
        tnm_n="",
        tnm_m="",
        staging_system="unknown",
        staging_source="none",
        staging_confidence=0.0,
    )


def _normalise_group(value: str) -> str:
    text = str(value or "").strip().upper().replace("STAGE", "").strip()
    return re.sub(r"\s+", "", text)


def _match_axis(rule_axis: str, observed: str) -> bool:
    rule = str(rule_axis or "").strip().upper()
    obs = str(observed or "").strip().upper()
    if not rule or not obs:
        return False
    if rule.startswith("ANY"):
        return True
    for part in [p.strip() for p in rule.split(",") if p.strip()]:
        if part.endswith("*"):
            if obs.startswith(part[:-1]):
                return True
        elif part == obs:
            return True
    return False


class StagingRulesEngine:
    def __init__(self, rules_dir: Path = RULES_DIR) -> None:
        self.rules_dir = rules_dir
        self.site_index: dict[str, str] = {}
        self.site_rules: dict[str, dict[str, Any]] = {}
        self.non_tnm_systems: list[dict[str, Any]] = []

    def load_rules(self) -> None:
        self.site_rules = {}
        for path in sorted(self.rules_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            slug = str(payload.get("site_slug") or path.stem)
            self.site_rules[slug] = payload

        site_index_path = self.rules_dir / "_site_index.json"
        if site_index_path.exists():
            self.site_index = json.loads(site_index_path.read_text(encoding="utf-8"))

        non_tnm_path = self.rules_dir / "_non_tnm_systems.json"
        if non_tnm_path.exists():
            payload = json.loads(non_tnm_path.read_text(encoding="utf-8"))
            self.non_tnm_systems = list(payload.get("systems") or [])

    def _resolve_site(self, cancer_type_snomed: str) -> str | None:
        return self.site_index.get(str(cancer_type_snomed or ""))

    def _resolve_explicit_stage(
        self, explicit_stage: str, source: str
    ) -> StagingResult | None:
        text = explicit_stage.strip()
        if not text:
            return None

        for system in self.non_tnm_systems:
            aliases = [a.lower() for a in system.get("aliases", [])]
            hay = text.lower()
            if aliases and not any(a in hay for a in aliases):
                continue
            stage_map = {
                k.upper(): v for k, v in (system.get("stage_to_group") or {}).items()
            }
            for key in sorted(stage_map.keys(), key=len, reverse=True):
                val = stage_map[key]
                if key in hay.upper():
                    return StagingResult(
                        cancer_stage=val,
                        cancer_stage_raw=text,
                        cancer_stage_group=key,
                        tnm_t="",
                        tnm_n="",
                        tnm_m="",
                        staging_system=str(system.get("system") or "non-tnm"),
                        staging_source=source,
                        staging_confidence=0.95 if source == "coded" else 0.75,
                    )

        match = _EXPLICIT_STAGE_RE.search(text)
        if not match:
            return None
        base = match.group(1).upper()
        suffix = (match.group(2) or "").upper()
        grp = f"{base}{suffix}"
        if base in {"0", "1", "2", "I", "II"}:
            stage = "early"
        elif base in {"3", "4", "III", "IV"}:
            stage = "late"
        else:
            stage = "unknown"
        return StagingResult(
            cancer_stage=stage,
            cancer_stage_raw=text,
            cancer_stage_group=grp,
            tnm_t="",
            tnm_n="",
            tnm_m="",
            staging_system="explicit_stage",
            staging_source=source,
            staging_confidence=0.97 if source == "coded" else 0.72,
        )

    def _resolve_from_tnm(
        self,
        *,
        cancer_type_snomed: str,
        tnm: TNMComponents,
        source: str,
    ) -> StagingResult | None:
        site = self._resolve_site(cancer_type_snomed)
        if not site:
            return None
        payload = self.site_rules.get(site) or {}
        stage_map = payload.get("stage_group_to_early_late") or {}
        for row in payload.get("tnm_to_stage_group", []):
            if (
                _match_axis(str(row.get("t") or ""), tnm.t)
                and _match_axis(str(row.get("n") or ""), tnm.n)
                and _match_axis(str(row.get("m") or ""), tnm.m)
            ):
                stage_group = _normalise_group(str(row.get("stage_group") or ""))
                if stage_group in {"", "NAN", "NA"}:
                    continue
                cancer_stage = stage_map.get(stage_group)
                if cancer_stage is None:
                    # Try with stripped suffix for IIIA style values
                    cancer_stage = stage_map.get(
                        re.sub(r"[ABC]$", "", stage_group), "unknown"
                    )
                return StagingResult(
                    cancer_stage=str(cancer_stage),
                    cancer_stage_raw=tnm.raw or f"{tnm.t}{tnm.n}{tnm.m}",
                    cancer_stage_group=stage_group,
                    tnm_t=tnm.t,
                    tnm_n=tnm.n,
                    tnm_m=tnm.m,
                    staging_system="TNM",
                    staging_source=source,
                    staging_confidence=0.93 if source == "coded" else 0.68,
                )
        return None

    def resolve_stage(
        self,
        *,
        cancer_type_snomed: str,
        tnm: TNMComponents | str | None = None,
        explicit_stage: str | None = None,
        source: str = "coded",
    ) -> StagingResult:
        if not self.site_rules and not self.site_index:
            self.load_rules()

        if explicit_stage:
            resolved = self._resolve_explicit_stage(explicit_stage, source)
            if resolved:
                return resolved

        tnm_obj: TNMComponents | None
        if isinstance(tnm, TNMComponents):
            tnm_obj = tnm
        elif isinstance(tnm, str):
            tnm_obj = parse_tnm_triplet(tnm)
        else:
            tnm_obj = None
        if tnm_obj:
            resolved = self._resolve_from_tnm(
                cancer_type_snomed=cancer_type_snomed,
                tnm=tnm_obj,
                source=source,
            )
            if resolved:
                return resolved

        return _default_unknown()
