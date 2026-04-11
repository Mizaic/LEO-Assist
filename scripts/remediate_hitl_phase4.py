"""HITL Queue Remediation — Phase 4: Additional surface forms & fixes.

Groups:
  4a: Generic suspected cancer / head-and-neck / colorectal / LGI shorthand
  4b: Common clinical terms — constipation, infection, fracture, AKI
  4c: IBS synonyms (13 surface forms)
  4d: Hypertension synonyms (14 surface forms)
  4e: CVA / Stroke synonyms
  4f: TIA synonyms
  4g: Fatty liver synonyms
  4h: Fungal infection / Mycosis synonyms
  4i: Smoking status terms
  4j: Miscellaneous clinical terms (HPV, Lives with partner, cyst, etc.)
  4k: Misspellings & brand names (haematemisis, Dehydrocodien, Fluclox, etc.)
  4l: Ignore rules (pub meal, surpress sxs)
  4m: Bad match fixes (perdios heavier -> menorrhagia)

Usage:
    # Dry-run (default)
    .venv\\Scripts\\python scripts\\remediate_hitl_phase4.py

    # Execute for real
    .venv\\Scripts\\python scripts\\remediate_hitl_phase4.py --execute
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unicodedata import normalize as unicode_normalize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------


def get_neo4j_driver():
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "")
    if not uri or not pwd:
        logger.error("NEO4J_URI / NEO4J_PASSWORD not set")
        sys.exit(1)
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    driver.verify_connectivity()
    return driver


def _normalize(text: str) -> str:
    return unicode_normalize("NFD", text.strip().lower())


# ---------------------------------------------------------------------------
# Cypher templates (same as main script)
# ---------------------------------------------------------------------------

UPSERT_SURFACE_FORM = """
MATCH (c:Concept {id: $concept_id})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form,
              sf.source = $source,
              sf.status = 'active',
              sf.created_at = datetime(),
              sf.created_by = $created_by
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(),
              m.created_by = $created_by,
              m.approved_at = datetime()
SET m.confidence = $confidence,
    m.provenance = $provenance
RETURN sf.normalized AS normalized, sf.form AS form, c.id AS concept_id
"""

BATCH_RESOLVE_BY_ENTITY_TEXT = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false
  AND t.include = true
  AND cr.entity_text = $entity_text
SET cr.resolved               = true,
    cr.resolved_concept_id    = $resolved_concept_id,
    cr.resolved_term          = $resolved_term,
    cr.resolved_by            = $reviewer,
    cr.resolved_at            = datetime(),
    cr.updated_at             = datetime(),
    cr.resolved_method        = 'batch_resolve',
    cr.resolved_assertion     = coalesce($resolved_assertion, 'present'),
    cr.reviewer_tier_override = CASE
        WHEN cr.decision_tier = 1
             AND $resolved_concept_id <> coalesce(cr.snomed_concept_id, '')
        THEN true
        WHEN cr.decision_tier = 3
        THEN true
        ELSE false
    END
RETURN count(cr) AS resolved_count
"""

UPDATE_TRAINING_LABEL_ENTITIES = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.entities_json = $entities_json,
    t.updated_at    = datetime()
RETURN t.label_id AS label_id
"""

UPSERT_CODING_IGNORE_RULE = """
MERGE (r:CodingIgnoreRule {entity_text: $entity_text})
ON CREATE SET r.rule_id = $rule_id, r.created_at = datetime()
SET r.entity_label = $entity_label,
    r.reason       = $reason,
    r.created_by   = coalesce(r.created_by, $created_by),
    r.active       = true,
    r.updated_at   = datetime()
RETURN r.rule_id AS rule_id, r.entity_text AS entity_text
"""

ALSO_RESOLVE_IGNORE = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false
  AND t.include = true
  AND cr.entity_text = $entity_text
SET cr.resolved     = true,
    cr.resolved_by  = $reviewer,
    cr.resolved_term = '__ignored_by_rule__',
    cr.resolved_at  = datetime(),
    cr.updated_at   = datetime(),
    cr.resolved_method = 'ignore_rule'
RETURN count(cr) AS resolved_count
"""

GET_LABELS_WITH_ENTITY_TEXT = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE t.include = true
  AND cr.entity_text = $entity_text
  AND cr.entity_label = $entity_label
RETURN DISTINCT t.label_id AS label_id, t.entities_json AS entities_json
"""

GET_UNRESOLVED_FOR_TEXT = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false
  AND t.include = true
  AND cr.entity_text = $entity_text
RETURN count(cr) AS pending_count
"""

REVIEWER = "remediate_hitl_phase4.py"

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SurfaceFormEntry:
    form: str
    concept_id: str
    concept_fsn: str
    entity_label: str
    assertion: str = "present"
    confidence: float = 0.95
    provenance: str = "hitl_remediation_phase4"


@dataclass
class IgnoreRuleEntry:
    entity_text: str
    entity_label: str
    reason: str


@dataclass
class Phase4Fix:
    entity_text: str
    old_concept_id: Optional[str]
    new_concept_id: str
    new_concept_fsn: str
    new_entity_label: str
    assertion: str = "present"
    note: str = ""


@dataclass
class Report:
    surface_forms_added: list = field(default_factory=list)
    reviews_resolved: list = field(default_factory=list)
    entities_json_updated: list = field(default_factory=list)
    ignore_rules_added: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    dry_run: bool = True

    def to_dict(self):
        return {
            "dry_run": self.dry_run,
            "summary": {
                "surface_forms_added": len(self.surface_forms_added),
                "reviews_resolved": sum(
                    r.get("resolved_count", 0) for r in self.reviews_resolved
                ),
                "entities_json_updated": len(self.entities_json_updated),
                "ignore_rules_added": len(self.ignore_rules_added),
                "errors": len(self.errors),
            },
            "surface_forms_added": self.surface_forms_added,
            "reviews_resolved": self.reviews_resolved,
            "entities_json_updated": self.entities_json_updated,
            "ignore_rules_added": self.ignore_rules_added,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Core write functions
# ---------------------------------------------------------------------------


def _sf(
    form, concept_id, concept_fsn, entity_label, assertion="present", confidence=0.95
) -> SurfaceFormEntry:
    return SurfaceFormEntry(
        form=form,
        concept_id=concept_id,
        concept_fsn=concept_fsn,
        entity_label=entity_label,
        assertion=assertion,
        confidence=confidence,
    )


def upsert_surface_form(
    session, entry: SurfaceFormEntry, execute: bool, report: Report
):
    normalized = _normalize(entry.form)
    if execute:
        try:
            session.run(
                UPSERT_SURFACE_FORM,
                normalized=normalized,
                form=entry.form,
                concept_id=entry.concept_id,
                source="hitl_remediation",
                created_by=REVIEWER,
                confidence=entry.confidence,
                provenance=entry.provenance,
            ).single()
            report.surface_forms_added.append(
                {
                    "form": entry.form,
                    "normalized": normalized,
                    "concept_id": entry.concept_id,
                    "concept_fsn": entry.concept_fsn,
                }
            )
            logger.debug("  SF upserted: %r -> %s", entry.form, entry.concept_id)
        except Exception as exc:
            report.errors.append(
                {"op": "upsert_surface_form", "form": entry.form, "error": str(exc)}
            )
            logger.warning("  SF FAILED %r: %s", entry.form, exc)
    else:
        report.surface_forms_added.append(
            {
                "form": entry.form,
                "normalized": normalized,
                "concept_id": entry.concept_id,
                "concept_fsn": entry.concept_fsn,
                "dry_run": True,
            }
        )


def batch_resolve(
    session, entity_text, concept_id, concept_fsn, assertion, execute, report
):
    if execute:
        try:
            result = session.run(
                BATCH_RESOLVE_BY_ENTITY_TEXT,
                entity_text=entity_text,
                resolved_concept_id=concept_id,
                resolved_term=concept_fsn,
                reviewer=REVIEWER,
                resolved_assertion=assertion,
            ).single()
            resolved_count = result["resolved_count"] if result else 0
            report.reviews_resolved.append(
                {
                    "entity_text": entity_text,
                    "concept_id": concept_id,
                    "resolved_count": resolved_count,
                    "assertion": assertion,
                }
            )
            logger.debug("  Resolved %d reviews for %r", resolved_count, entity_text)
        except Exception as exc:
            report.errors.append(
                {"op": "batch_resolve", "entity_text": entity_text, "error": str(exc)}
            )
            logger.warning("  Resolve FAILED %r: %s", entity_text, exc)
    else:
        pending_row = session.run(
            GET_UNRESOLVED_FOR_TEXT, entity_text=entity_text
        ).single()
        pending_count = pending_row["pending_count"] if pending_row else 0
        report.reviews_resolved.append(
            {
                "entity_text": entity_text,
                "concept_id": concept_id,
                "resolved_count": pending_count,
                "assertion": assertion,
                "dry_run": True,
            }
        )


def upsert_ignore_rule(session, entry: IgnoreRuleEntry, execute: bool, report: Report):
    if execute:
        try:
            session.run(
                UPSERT_CODING_IGNORE_RULE,
                entity_text=entry.entity_text,
                rule_id=str(uuid.uuid4()),
                entity_label=entry.entity_label,
                reason=entry.reason,
                created_by=REVIEWER,
            )
            result = session.run(
                ALSO_RESOLVE_IGNORE,
                entity_text=entry.entity_text,
                reviewer=REVIEWER,
            ).single()
            resolved_count = result["resolved_count"] if result else 0
            report.ignore_rules_added.append(
                {
                    "entity_text": entry.entity_text,
                    "reason": entry.reason,
                    "resolved_count": resolved_count,
                }
            )
            logger.info(
                "  Ignore rule added: %r (resolved %d)",
                entry.entity_text,
                resolved_count,
            )
        except Exception as exc:
            report.errors.append(
                {
                    "op": "upsert_ignore_rule",
                    "entity_text": entry.entity_text,
                    "error": str(exc),
                }
            )
            logger.warning("  Ignore rule FAILED %r: %s", entry.entity_text, exc)
    else:
        pending_row = session.run(
            GET_UNRESOLVED_FOR_TEXT, entity_text=entry.entity_text
        ).single()
        pending_count = pending_row["pending_count"] if pending_row else 0
        report.ignore_rules_added.append(
            {
                "entity_text": entry.entity_text,
                "reason": entry.reason,
                "resolved_count": pending_count,
                "dry_run": True,
            }
        )


def update_entities_json_for_text(
    session, entity_text, old_label, new_label, execute, report
):
    rows = list(
        session.run(
            GET_LABELS_WITH_ENTITY_TEXT,
            entity_text=entity_text,
            entity_label=old_label,
        )
    )
    for row in rows:
        label_id = row["label_id"]
        entities = json.loads(row["entities_json"] or "[]")
        changed = False
        for ent in entities:
            if ent.get("text") == entity_text and ent.get("label") == old_label:
                ent["label"] = new_label
                changed = True
        if not changed:
            continue
        new_json = json.dumps(entities)
        if execute:
            try:
                session.run(
                    UPDATE_TRAINING_LABEL_ENTITIES,
                    label_id=label_id,
                    entities_json=new_json,
                )
                report.entities_json_updated.append(
                    {
                        "label_id": label_id,
                        "entity_text": entity_text,
                        "old_label": old_label,
                        "new_label": new_label,
                    }
                )
            except Exception as exc:
                report.errors.append(
                    {
                        "op": "update_entities_json",
                        "label_id": label_id,
                        "error": str(exc),
                    }
                )
        else:
            report.entities_json_updated.append(
                {
                    "label_id": label_id,
                    "entity_text": entity_text,
                    "old_label": old_label,
                    "new_label": new_label,
                    "dry_run": True,
                }
            )


# ---------------------------------------------------------------------------
# Phase 4 data
# ---------------------------------------------------------------------------


def build_surface_forms() -> list[SurfaceFormEntry]:
    entries: list[SurfaceFormEntry] = []

    # -- 4a: Generic / head-and-neck / colorectal / LGI suspected cancers ---
    CANCERS = [
        (
            "Suspected cancer",
            "162572001",
            "Malignant neoplastic disease suspected (situation)",
            "situation",
        ),
        (
            "suspected cancer",
            "162572001",
            "Malignant neoplastic disease suspected (situation)",
            "situation",
        ),
        (
            "?cancer",
            "162572001",
            "Malignant neoplastic disease suspected (situation)",
            "situation",
        ),
        (
            "Malignancy suspected",
            "162572001",
            "Malignant neoplastic disease suspected (situation)",
            "situation",
        ),
        (
            "malignancy suspected",
            "162572001",
            "Malignant neoplastic disease suspected (situation)",
            "situation",
        ),
        (
            "suspected malignancy",
            "162572001",
            "Malignant neoplastic disease suspected (situation)",
            "situation",
        ),
        (
            "Suspected malignancy",
            "162572001",
            "Malignant neoplastic disease suspected (situation)",
            "situation",
        ),
        (
            "Suspected head and neck cancer",
            "315277001",
            "Malignant neoplasm of head and/or neck suspected (situation)",
            "situation",
        ),
        (
            "suspected head and neck cancer",
            "315277001",
            "Malignant neoplasm of head and/or neck suspected (situation)",
            "situation",
        ),
        (
            "?head and neck cancer",
            "315277001",
            "Malignant neoplasm of head and/or neck suspected (situation)",
            "situation",
        ),
        (
            "Ca head and neck",
            "315277001",
            "Malignant neoplasm of head and/or neck suspected (situation)",
            "situation",
        ),
        (
            "suspected colorectal cancer",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
        (
            "Suspected colorectal cancer",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
        (
            "?colorectal cancer",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
        (
            "Suspected lower gastrointestinal cancer",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
        (
            "suspected lower gastrointestinal cancer",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
        (
            "Suspected lgi cancer",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
        (
            "suspected lgi cancer",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
        (
            "?lgi cancer",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
        (
            "?lg cx",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
        (
            "?LGI cancer",
            "315274008",
            "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
            "situation",
        ),
    ]
    for form, cid, fsn, label in CANCERS:
        entries.append(_sf(form, cid, fsn, label))

    # -- 4b: Common clinical terms -------------------------------------------
    COMMON = [
        ("constipation", "14760008", "Constipation (finding)", "finding"),
        ("Constipation", "14760008", "Constipation (finding)", "finding"),
        ("infection", "40733004", "Infectious disease (disorder)", "disorder"),
        ("Infection", "40733004", "Infectious disease (disorder)", "disorder"),
        ("fracture", "125605004", "Fracture of bone (disorder)", "disorder"),
        ("Fracture", "125605004", "Fracture of bone (disorder)", "disorder"),
        (
            "Acute Kidney Injury",
            "14669001",
            "Acute kidney injury (disorder)",
            "disorder",
        ),
        (
            "acute kidney injury",
            "14669001",
            "Acute kidney injury (disorder)",
            "disorder",
        ),
        ("AKI", "14669001", "Acute kidney injury (disorder)", "disorder"),
    ]
    for form, cid, fsn, label in COMMON:
        entries.append(_sf(form, cid, fsn, label))

    # -- 4c: IBS synonyms ----------------------------------------------------
    IBS_CID = "10743008"
    IBS_FSN = "Irritable bowel syndrome (disorder)"
    IBS_FORMS = [
        "IBS",
        "Irritable colon",
        "irritable colon",
        "Adaptive colitis",
        "adaptive colitis",
        "Membranous colitis",
        "membranous colitis",
        "Spastic colon",
        "spastic colon",
        "Irritable bowel syndrome",
        "irritable bowel syndrome",
        "Mucous colitis",
        "mucous colitis",
        "Colon spasm",
        "colon spasm",
        "Functional bowel disease",
        "functional bowel disease",
        "Nervous colitis",
        "nervous colitis",
        "IBS - Irritable bowel syndrome",
        "Irritable bowel",
        "irritable bowel",
        "Spastic colitis",
        "spastic colitis",
        "Irritable colon syndrome",
        "irritable colon syndrome",
        "IC - Irritable colon",
    ]
    for form in IBS_FORMS:
        entries.append(_sf(form, IBS_CID, IBS_FSN, "disorder"))

    # -- 4d: Hypertension synonyms -------------------------------------------
    HTN_CID = "38458008"
    HTN_FSN = "Hypertensive disorder, systemic arterial (disorder)"
    HTN_FORMS = [
        "High blood pressure",
        "high blood pressure",
        "Hypertensive vascular disease",
        "hypertensive vascular disease",
        "Hypertensive vascular degeneration",
        "hypertensive vascular degeneration",
        "Hypertension",
        "hypertension",
        "BP - High blood pressure",
        "Systemic arterial hypertension",
        "systemic arterial hypertension",
        "HBP - High blood pressure",
        "HT - Hypertension",
        "High blood pressure disorder",
        "high blood pressure disorder",
        "BP+ - Hypertension",
        "Hypertensive disorder, systemic arterial",
        "Hypertensive disorder",
        "hypertensive disorder",
        "HTN - Hypertension",
        "HTN",
        "Hypertensive disorder, systemic arterial (disorder)",
    ]
    for form in HTN_FORMS:
        entries.append(_sf(form, HTN_CID, HTN_FSN, "disorder"))

    # -- 4e: CVA / Stroke ----------------------------------------------------
    CVA_CID = "230690007"
    CVA_FSN = "Cerebrovascular accident (disorder)"
    CVA_FORMS = [
        "CVA",
        "Cerebrovascular accident",
        "cerebrovascular accident",
        "Stroke",
        "stroke",
    ]
    for form in CVA_FORMS:
        entries.append(_sf(form, CVA_CID, CVA_FSN, "disorder"))

    # -- 4f: TIA synonyms ----------------------------------------------------
    TIA_CID = "266257000"
    TIA_FSN = "Transient ischemic attack (disorder)"
    TIA_FORMS = [
        "Transient ischaemic attack",
        "transient ischaemic attack",
        "Transient cerebral ischemia",
        "transient cerebral ischemia",
        "Transient ischemic attack",
        "transient ischemic attack",
        "Transient cerebral ischaemia",
        "transient cerebral ischaemia",
        "Transient ischemic attack (disorder)",
        "TIA - transient ischemic attack",
        "TIA - transient ischaemic attack",
        "TIA",
    ]
    for form in TIA_FORMS:
        entries.append(_sf(form, TIA_CID, TIA_FSN, "disorder"))

    # -- 4g: Fatty liver / steatosis -----------------------------------------
    LIVER_CID = "197321007"
    LIVER_FSN = "Steatosis of liver (disorder)"
    LIVER_FORMS = [
        "Steatosis of liver",
        "steatosis of liver",
        "Steatosis of liver (disorder)",
        "Fatty liver",
        "fatty liver",
        "Hepatic lipidosis",
        "hepatic lipidosis",
        "Steatotic liver disease",
        "steatotic liver disease",
        "SLD - steatotic liver disease",
    ]
    for form in LIVER_FORMS:
        entries.append(_sf(form, LIVER_CID, LIVER_FSN, "disorder"))

    # -- 4h: Fungal infection / Mycosis ---------------------------------------
    MYC_CID = "3218000"
    MYC_FSN = "Mycosis (disorder)"
    MYC_FORMS = [
        "Mycosis",
        "mycosis",
        "Fungal infection",
        "fungal infection",
        "Disease caused by fungus",
        "disease caused by fungus",
        "Fungal infectious disease",
        "fungal infectious disease",
        "Fungus infection",
        "fungus infection",
        "Mycoses",
        "mycoses",
        "Mycosis (disorder)",
        "Mycotic disease",
        "mycotic disease",
    ]
    for form in MYC_FORMS:
        entries.append(_sf(form, MYC_CID, MYC_FSN, "disorder"))

    # -- 4i: Smoking status ---------------------------------------------------
    SMOKING = [
        ("Stopped smoking", "160617001", "Stopped smoking (finding)", "finding"),
        ("stopped smoking", "160617001", "Stopped smoking (finding)", "finding"),
        ("Never Smoked", "266919005", "Never smoked tobacco (finding)", "finding"),
        ("never smoked", "266919005", "Never smoked tobacco (finding)", "finding"),
        ("Never smoked", "266919005", "Never smoked tobacco (finding)", "finding"),
        (
            "Ex-cigarette smoker",
            "281018007",
            "Ex-cigarette smoker (finding)",
            "finding",
        ),
        (
            "ex-cigarette smoker",
            "281018007",
            "Ex-cigarette smoker (finding)",
            "finding",
        ),
        (
            "Ex cigarette smoker",
            "281018007",
            "Ex-cigarette smoker (finding)",
            "finding",
        ),
        ("ex smoker", "281018007", "Ex-cigarette smoker (finding)", "finding"),
        ("Ex smoker", "281018007", "Ex-cigarette smoker (finding)", "finding"),
        (
            "smoking cannabis",
            "347841000119106",
            "Long-term current use of cannabis (situation)",
            "situation",
        ),
        (
            "Smoking cannabis",
            "347841000119106",
            "Long-term current use of cannabis (situation)",
            "situation",
        ),
        (
            "cannabis use",
            "347841000119106",
            "Long-term current use of cannabis (situation)",
            "situation",
        ),
    ]
    for form, cid, fsn, label in SMOKING:
        entries.append(_sf(form, cid, fsn, label))

    # -- 4j: Miscellaneous clinical terms -------------------------------------
    MISC = [
        (
            "smear HPV positive",
            "293201000119102",
            "History of human papillomavirus infection (situation)",
            "situation",
        ),
        (
            "HPV positive",
            "293201000119102",
            "History of human papillomavirus infection (situation)",
            "situation",
        ),
        ("Lives with partner", "408821002", "Lives with partner (finding)", "finding"),
        ("lives with partner", "408821002", "Lives with partner (finding)", "finding"),
        ("feels like a cyst", "441457006", "Cyst (disorder)", "disorder"),
        ("freq", "70232002", "Frequent (qualifier value)", "qualifier_value"),
    ]
    for form, cid, fsn, label in MISC:
        entries.append(_sf(form, cid, fsn, label))

    # feels like a cyst — hypothetical assertion
    for e in entries:
        if e.form == "feels like a cyst":
            e.assertion = "hypothetical"

    # -- 4k: Misspellings & brand names ----------------------------------------
    MISSPELLINGS = [
        ("haematemisis", "8765009", "Hematemesis (disorder)", "disorder"),
        (
            "Dehydrocodien",
            "775592007",
            "Product containing only dihydrocodeine (medicinal product)",
            "medicinal_product",
        ),
        (
            "dehydrocodien",
            "775592007",
            "Product containing only dihydrocodeine (medicinal product)",
            "medicinal_product",
        ),
        (
            "Dehydrocodeine",
            "775592007",
            "Product containing only dihydrocodeine (medicinal product)",
            "medicinal_product",
        ),
        (
            "dehydrocodeine",
            "775592007",
            "Product containing only dihydrocodeine (medicinal product)",
            "medicinal_product",
        ),
        ("hoseiry", "228183008", "Hosiery (physical object)", "physical_object"),
        ("hosiery", "228183008", "Hosiery (physical object)", "physical_object"),
        ("Hosiery", "228183008", "Hosiery (physical object)", "physical_object"),
        (
            "Fluclox",
            "775979003",
            "Product containing only flucloxacillin (medicinal product)",
            "medicinal_product",
        ),
        (
            "fluclox",
            "775979003",
            "Product containing only flucloxacillin (medicinal product)",
            "medicinal_product",
        ),
        (
            "flucloxacillin",
            "775979003",
            "Product containing only flucloxacillin (medicinal product)",
            "medicinal_product",
        ),
        (
            "Flucloxacillin",
            "775979003",
            "Product containing only flucloxacillin (medicinal product)",
            "medicinal_product",
        ),
        ("Cosmocol", "11980301000001107", "CosmoCol (product)", "medicinal_product"),
        ("cosmocol", "11980301000001107", "CosmoCol (product)", "medicinal_product"),
        ("CosmoCol", "11980301000001107", "CosmoCol (product)", "medicinal_product"),
        ("Diuretics", "372695000", "Diuretic (substance)", "substance"),
        ("diuretics", "372695000", "Diuretic (substance)", "substance"),
        ("diuretic", "372695000", "Diuretic (substance)", "substance"),
        ("fidgetting", "247910009", "Fidgeting (finding)", "finding"),
        ("fidgeting", "247910009", "Fidgeting (finding)", "finding"),
        ("Fidgeting", "247910009", "Fidgeting (finding)", "finding"),
        ("distractability", "28102002", "Distractibility (finding)", "finding"),
        ("distractibility", "28102002", "Distractibility (finding)", "finding"),
        ("Distractibility", "28102002", "Distractibility (finding)", "finding"),
        ("anergia", "248274002", "Lack of energy (finding)", "finding"),
        ("Anergia", "248274002", "Lack of energy (finding)", "finding"),
    ]
    for form, cid, fsn, label in MISSPELLINGS:
        entries.append(_sf(form, cid, fsn, label))

    return entries


def build_ignore_rules() -> list[IgnoreRuleEntry]:
    return [
        IgnoreRuleEntry(
            entity_text="eating a pub meal (mixed grill) last Wednesday,",
            entity_label="",
            reason="Dietary context, not a codeable clinical concept.",
        ),
        IgnoreRuleEntry(
            entity_text="eating a pub meal",
            entity_label="",
            reason="Dietary context, not a codeable clinical concept.",
        ),
        IgnoreRuleEntry(
            entity_text="surpress sxs",
            entity_label="",
            reason="Too vague to code — shorthand for 'suppress symptoms' with no specific clinical concept.",
        ),
    ]


def build_fixes() -> list[Phase4Fix]:
    return [
        Phase4Fix(
            entity_text="perdios heavier",
            old_concept_id=None,
            new_concept_id="161782001",
            new_concept_fsn="History of menorrhagia (situation)",
            new_entity_label="situation",
            note="Misspelling of 'periods heavier'",
        ),
    ]


# ---------------------------------------------------------------------------
# Phase runner
# ---------------------------------------------------------------------------


def run_phase4(driver, execute: bool, report: Report):
    surface_forms = build_surface_forms()
    ignore_rules = build_ignore_rules()
    fixes = build_fixes()

    logger.info(
        "Phase 4: %d surface forms, %d ignore rules, %d fixes",
        len(surface_forms),
        len(ignore_rules),
        len(fixes),
    )

    resolved_texts: set[str] = set()

    with driver.session() as session:
        # Surface forms + resolve
        for idx, entry in enumerate(surface_forms):
            if idx % 20 == 0:
                logger.info("  Progress: %d/%d surface forms", idx, len(surface_forms))
            upsert_surface_form(session, entry, execute, report)
            if entry.form not in resolved_texts:
                batch_resolve(
                    session,
                    entity_text=entry.form,
                    concept_id=entry.concept_id,
                    concept_fsn=entry.concept_fsn,
                    assertion=entry.assertion,
                    execute=execute,
                    report=report,
                )
                resolved_texts.add(entry.form)

        # Ignore rules
        for rule in ignore_rules:
            upsert_ignore_rule(session, rule, execute, report)

        # Fixes (surface form + resolve + entities_json update)
        for fix in fixes:
            logger.info(
                "  Fix: %r -> %s | %s",
                fix.entity_text,
                fix.new_concept_id,
                fix.new_concept_fsn,
            )
            sf_entry = _sf(
                fix.entity_text,
                fix.new_concept_id,
                fix.new_concept_fsn,
                fix.new_entity_label,
                assertion=fix.assertion,
            )
            upsert_surface_form(session, sf_entry, execute, report)

            batch_resolve(
                session,
                entity_text=fix.entity_text,
                concept_id=fix.new_concept_id,
                concept_fsn=fix.new_concept_fsn,
                assertion=fix.assertion,
                execute=execute,
                report=report,
            )

            for from_label in [
                "finding",
                "disorder",
                "situation",
                "observable_entity",
                "procedure",
                "qualifier_value",
            ]:
                if from_label != fix.new_entity_label:
                    update_entities_json_for_text(
                        session,
                        entity_text=fix.entity_text,
                        old_label=from_label,
                        new_label=fix.new_entity_label,
                        execute=execute,
                        report=report,
                    )

    logger.info("Phase 4 complete.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="HITL Queue Remediation — Phase 4")
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually write to Neo4j (default: dry-run)",
    )
    args = parser.parse_args()

    execute = args.execute
    mode = "EXECUTE" if execute else "DRY-RUN"
    logger.info("=== HITL Queue Remediation Phase 4 — %s ===", mode)

    driver = get_neo4j_driver()
    logger.info("Connected to Neo4j")

    report = Report(dry_run=not execute)

    try:
        run_phase4(driver, execute, report)
    finally:
        driver.close()

    report_dict = report.to_dict()
    output_path = ROOT / "scripts" / "hitl_phase4_report.json"
    output_path.write_text(json.dumps(report_dict, indent=2, default=str))
    logger.info("Report written to %s", output_path)

    s = report_dict["summary"]
    logger.info(
        "=== Summary (%s) === "
        "surface_forms=%d | reviews_resolved=%d | entities_json_updated=%d "
        "| ignore_rules=%d | errors=%d",
        mode,
        s["surface_forms_added"],
        s["reviews_resolved"],
        s["entities_json_updated"],
        s["ignore_rules_added"],
        s["errors"],
    )

    if report.errors:
        logger.warning("%d errors encountered — check report", len(report.errors))
        sys.exit(1)


if __name__ == "__main__":
    main()
