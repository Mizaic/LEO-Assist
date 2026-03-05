"""HITL Queue Remediation — Three-phase batch fix.

Phase 1a: Surface forms for 5 medications
Phase 1b: ~120 surface forms for 24 suspected cancer types (? and Ca variations)
Phase 1c: Surface forms for clinical shorthand (CIBH, Fibroscan, NWB, apyrexic)
Phase 1d: Surface forms for common symptoms / misspellings
Phase 1e: CodingIgnoreRules for non-codeable terms (SSKIN, QMC)
Phase 2:  Bulk-accept observable_entity->procedure lab test mappings
Phase 3:  Fix bad SNOMED matches

Critical architecture note:
    Resolving a CodingReview writes a SurfaceForm but does NOT update
    TrainingLabel.entities_json (the NER training source).  Where entity
    labels change (Phases 2 and 3) this script updates entities_json too.

Usage:
    # Dry-run (default) — prints JSON report, no writes
    .venv\\Scripts\\python scripts\\remediate_hitl_queue.py

    # Execute for real
    .venv\\Scripts\\python scripts\\remediate_hitl_queue.py --execute

    # Single phase
    .venv\\Scripts\\python scripts\\remediate_hitl_queue.py --execute --phase 1
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
# Neo4j connection
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


# ---------------------------------------------------------------------------
# Normalisation helper (mirrors terminology API logic)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace, NFD-normalise."""
    return unicode_normalize("NFD", text.strip().lower())


# ---------------------------------------------------------------------------
# Shared write helpers
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

GET_LAB_TEST_REVIEWS = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE t.include = true AND cr.resolved = false
  AND cr.entity_label = 'observable_entity'
  AND cr.suggested_label = 'procedure'
RETURN DISTINCT cr.entity_text    AS text,
                cr.snomed_concept_id AS concept_id,
                cr.snomed_term    AS snomed_term
ORDER BY cr.entity_text
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

REVIEWER = "remediate_hitl_queue.py"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SurfaceFormEntry:
    """One surface form variation to upsert."""
    form: str           # display form
    concept_id: str
    concept_fsn: str    # human-readable label for the report
    entity_label: str   # NER label (for resolving reviews)
    assertion: str = "present"
    confidence: float = 0.95
    provenance: str = "hitl_remediation"


@dataclass
class IgnoreRuleEntry:
    entity_text: str
    entity_label: str
    reason: str


@dataclass
class Phase3Fix:
    entity_text: str
    old_concept_id: Optional[str]
    new_concept_id: str
    new_concept_fsn: str
    new_entity_label: str
    assertion: str = "present"
    note: str = ""


# ---------------------------------------------------------------------------
# Report accumulator
# ---------------------------------------------------------------------------

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
                "reviews_resolved": sum(r.get("resolved_count", 0) for r in self.reviews_resolved),
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

def upsert_surface_form(session, entry: SurfaceFormEntry, execute: bool, report: Report):
    normalized = _normalize(entry.form)
    if execute:
        try:
            result = session.run(
                UPSERT_SURFACE_FORM,
                normalized=normalized,
                form=entry.form,
                concept_id=entry.concept_id,
                source="hitl_remediation",
                created_by=REVIEWER,
                confidence=entry.confidence,
                provenance=entry.provenance,
            ).single()
            report.surface_forms_added.append({
                "form": entry.form,
                "normalized": normalized,
                "concept_id": entry.concept_id,
                "concept_fsn": entry.concept_fsn,
            })
            logger.debug("  SF upserted: %r -> %s", entry.form, entry.concept_id)
        except Exception as exc:
            report.errors.append({"op": "upsert_surface_form", "form": entry.form, "error": str(exc)})
            logger.warning("  SF FAILED %r: %s", entry.form, exc)
    else:
        report.surface_forms_added.append({
            "form": entry.form,
            "normalized": normalized,
            "concept_id": entry.concept_id,
            "concept_fsn": entry.concept_fsn,
            "dry_run": True,
        })


def batch_resolve(session, entity_text: str, concept_id: str, concept_fsn: str,
                  assertion: str, execute: bool, report: Report):
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
            report.reviews_resolved.append({
                "entity_text": entity_text,
                "concept_id": concept_id,
                "resolved_count": resolved_count,
                "assertion": assertion,
            })
            logger.debug("  Resolved %d reviews for %r", resolved_count, entity_text)
        except Exception as exc:
            report.errors.append({"op": "batch_resolve", "entity_text": entity_text, "error": str(exc)})
            logger.warning("  Resolve FAILED %r: %s", entity_text, exc)
    else:
        pending_row = session.run(
            GET_UNRESOLVED_FOR_TEXT, entity_text=entity_text
        ).single()
        pending_count = pending_row["pending_count"] if pending_row else 0
        report.reviews_resolved.append({
            "entity_text": entity_text,
            "concept_id": concept_id,
            "resolved_count": pending_count,
            "assertion": assertion,
            "dry_run": True,
        })


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
            # Also resolve any existing pending reviews
            session.run(
                ALSO_RESOLVE_IGNORE,
                entity_text=entry.entity_text,
                reviewer=REVIEWER,
            )
            report.ignore_rules_added.append({
                "entity_text": entry.entity_text,
                "reason": entry.reason,
            })
            logger.info("  Ignore rule added: %r", entry.entity_text)
        except Exception as exc:
            report.errors.append({"op": "upsert_ignore_rule", "entity_text": entry.entity_text, "error": str(exc)})
            logger.warning("  Ignore rule FAILED %r: %s", entry.entity_text, exc)
    else:
        report.ignore_rules_added.append({
            "entity_text": entry.entity_text,
            "reason": entry.reason,
            "dry_run": True,
        })


def update_entities_json_for_text(
    session, entity_text: str, old_label: str, new_label: str,
    execute: bool, report: Report
):
    """Update entities_json on all TrainingLabels where entity_text + label match."""
    rows = list(session.run(
        GET_LABELS_WITH_ENTITY_TEXT,
        entity_text=entity_text,
        entity_label=old_label,
    ))
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
                report.entities_json_updated.append({
                    "label_id": label_id,
                    "entity_text": entity_text,
                    "old_label": old_label,
                    "new_label": new_label,
                })
            except Exception as exc:
                report.errors.append({
                    "op": "update_entities_json",
                    "label_id": label_id,
                    "error": str(exc),
                })
        else:
            report.entities_json_updated.append({
                "label_id": label_id,
                "entity_text": entity_text,
                "old_label": old_label,
                "new_label": new_label,
                "dry_run": True,
            })


# ---------------------------------------------------------------------------
# Phase 1 data definitions
# ---------------------------------------------------------------------------

def _sf(form: str, concept_id: str, concept_fsn: str, entity_label: str,
        assertion: str = "present", confidence: float = 0.95) -> SurfaceFormEntry:
    return SurfaceFormEntry(
        form=form,
        concept_id=concept_id,
        concept_fsn=concept_fsn,
        entity_label=entity_label,
        assertion=assertion,
        confidence=confidence,
    )


def build_phase1_surface_forms() -> list[SurfaceFormEntry]:
    entries: list[SurfaceFormEntry] = []

    # -----------------------------------------------------------------------
    # 1a. Medications
    # -----------------------------------------------------------------------
    MEDS = [
        ("ezetimibe", "775914003", "Product containing only ezetimibe (medicinal product)", "medicinal_product"),
        ("Ezetimibe", "775914003", "Product containing only ezetimibe (medicinal product)", "medicinal_product"),
        ("?Ezetimibe", "775914003", "Product containing only ezetimibe (medicinal product)", "medicinal_product"),
        ("Mounjaro", "634991000001102", "Mounjaro (product)", "medicinal_product"),
        ("mounjaro", "634991000001102", "Mounjaro (product)", "medicinal_product"),
        ("Fybogel", "9500401000001102", "Fybogel (product)", "medicinal_product"),
        ("fybogel", "9500401000001102", "Fybogel (product)", "medicinal_product"),
        ("Cilest", "9567801000001100", "Cilest (product)", "medicinal_product"),
        ("cilest", "9567801000001100", "Cilest (product)", "medicinal_product"),
        ("NRT", "151159008", "Nicotine replacement therapy (procedure)", "procedure"),
        ("nicotine replacement therapy", "151159008", "Nicotine replacement therapy (procedure)", "procedure"),
        ("Nicotine replacement therapy", "151159008", "Nicotine replacement therapy (procedure)", "procedure"),
    ]
    for form, cid, fsn, label in MEDS:
        entries.append(_sf(form, cid, fsn, label))

    # -----------------------------------------------------------------------
    # 1b. Suspected cancers — for each base term we create:
    #     (i)  The base form as given
    #     (ii) ?<body part> cancer variant
    #     (iii) Ca <body part> / suspected Ca <body part>
    #     (iv) suspected <body part> malignancy
    # -----------------------------------------------------------------------
    CANCERS = [
        ("lung", "162573006", "Malignant neoplasm of lung suspected (situation)"),
        ("skin", "315276005", "Malignant neoplasm of skin suspected (situation)"),
        ("vulva", "762996008", "Malignant neoplasm of vulva suspected (situation)"),
        ("bowel", "762999001", "Malignant neoplasm of intestine suspected (situation)"),
        ("breast", "134405005", "Malignant neoplasm of breast suspected (situation)"),
        ("kidney", "315270004", "Malignant neoplasm of kidney suspected (situation)"),
        ("ovarian", "762997004", "Malignant neoplasm of ovary suspected (situation)"),
        ("bladder", "315269000", "Malignant neoplasm of urinary bladder suspected (situation)"),
        ("cervical", "315266007", "Malignant neoplasm of cervix uteri suspected (situation)"),
        ("prostate", "315268008", "Malignant neoplasm of prostate suspected (situation)"),
        ("testicular", "315272007", "Malignant neoplasm of testis suspected (situation)"),
        ("pancreatic", "247591000000101", "Suspected pancreatic cancer (situation)"),
        ("endometrial", "315267003", "Malignant neoplasm of endometrium of corpus uteri suspected (situation)"),
    ]
    for body_part, cid, fsn in CANCERS:
        cap = body_part.capitalize()
        forms = [
            f"Suspected {body_part} cancer",
            f"suspected {body_part} cancer",
            f"?{body_part} cancer",
            f"?{cap} cancer",
            f"Ca {body_part}",
            f"ca {body_part}",
            f"Ca {cap}",
            f"suspected Ca {body_part}",
            f"suspected ca {body_part}",
            f"?Ca {body_part}",
            f"?ca {body_part}",
            f"suspected {body_part} malignancy",
            f"Suspected {body_part} malignancy",
        ]
        for form in forms:
            entries.append(_sf(form, cid, fsn, "situation"))

    # Urothelial — no simple body-part shorthand, use specific forms
    uro_cid = "315271000"
    uro_fsn = "Urothelial cancer suspected (situation)"
    for form in [
        "Urothelial cancer suspected",
        "urothelial cancer suspected",
        "suspected urothelial cancer",
        "?urothelial cancer",
        "Ca urothelium",
        "suspected urothelial malignancy",
    ]:
        entries.append(_sf(form, uro_cid, uro_fsn, "situation"))

    # Urological cancer
    urol_cid = "397657005"
    urol_fsn = "Malignant neoplasm of urinary system suspected (situation)"
    for form in [
        "Suspected urological cancer",
        "suspected urological cancer",
        "?urological cancer",
        "Ca urological",
        "suspected urological malignancy",
    ]:
        entries.append(_sf(form, urol_cid, urol_fsn, "situation"))

    # Gynaecological / gynecological
    gynae_cid = "397682005"
    gynae_fsn = "Malignant neoplasm of female genital organ suspected (situation)"
    for form in [
        "Suspected gynaecological cancer",
        "suspected gynaecological cancer",
        "?gynaecological cancer",
        "Suspected gynecological cancer",
        "suspected gynecological cancer",
        "?gynecological cancer",
        "suspected gynaecological malignancy",
        "suspected gynecological malignancy",
        "Ca gynaecological",
        "Ca gynecological",
    ]:
        entries.append(_sf(form, gynae_cid, gynae_fsn, "situation"))

    # Haematological / hematological
    haem_cid = "315275009"
    haem_fsn = "Hematological malignancy suspected (situation)"
    for form in [
        "Suspected haematological cancer",
        "suspected haematological cancer",
        "?haematological cancer",
        "Suspected hematological cancer",
        "suspected hematological cancer",
        "?hematological cancer",
        "suspected haematological malignancy",
        "suspected hematological malignancy",
        "suspected haematological neoplasm",
        "suspected blood cancer",
        "?blood cancer",
    ]:
        entries.append(_sf(form, haem_cid, haem_fsn, "situation"))

    # Lower GI
    lgi_cid = "315274008"
    lgi_fsn = "Malignant neoplasm of lower gastrointestinal tract suspected (situation)"
    for form in [
        "Suspected lower gastrointestinal cancer",
        "suspected lower gastrointestinal cancer",
        "?lower gastrointestinal cancer",
        "Suspected lower GI cancer",
        "suspected lower GI cancer",
        "?lower GI cancer",
        "suspected lower GI malignancy",
        "suspected lower gastrointestinal malignancy",
    ]:
        entries.append(_sf(form, lgi_cid, lgi_fsn, "situation"))

    # Upper GI
    ugi_cid = "315273002"
    ugi_fsn = "Malignant neoplasm of upper gastrointestinal tract suspected (situation)"
    for form in [
        "Suspected upper gastrointestinal cancer",
        "suspected upper gastrointestinal cancer",
        "?upper gastrointestinal cancer",
        "Suspected upper GI cancer",
        "suspected upper GI cancer",
        "?upper GI cancer",
        "suspected upper GI malignancy",
        "suspected upper gastrointestinal malignancy",
    ]:
        entries.append(_sf(form, ugi_cid, ugi_fsn, "situation"))

    # CNS
    cns_cid = "397614000"
    cns_fsn = "Malignant neoplasm of central nervous system suspected (situation)"
    for form in [
        "Suspected central nervous system cancer",
        "suspected central nervous system cancer",
        "?central nervous system cancer",
        "Suspected cns cancer",
        "suspected cns cancer",
        "?cns cancer",
        "suspected CNS cancer",
        "?CNS cancer",
        "suspected CNS malignancy",
        "suspected brain cancer",
        "?brain cancer",
        "suspected brain tumour",
        "suspected brain tumor",
        "?brain tumour",
    ]:
        entries.append(_sf(form, cns_cid, cns_fsn, "situation"))

    # Children's cancer — all paediatric / pediatric variants
    child_cid = "397715008"
    child_fsn = "Malignant neoplasm of child suspected (situation)"
    for form in [
        "Suspected children's cancer",
        "suspected children's cancer",
        "suspected paediatric cancer",
        "Suspected paediatric cancer",
        "suspected pediatric cancer",
        "Suspected pediatric cancer",
        "?childhood cancer",
        "?paediatric cancer",
        "?pediatric cancer",
        "?children's cancer",
        "suspected childhood malignancy",
        "suspected paediatric malignancy",
        "suspected pediatric malignancy",
        "suspected childhood cancer",
        "Ca paediatric",
        "Ca pediatric",
    ]:
        entries.append(_sf(form, child_cid, child_fsn, "situation"))

    # -----------------------------------------------------------------------
    # 1c. Clinical shorthand
    # -----------------------------------------------------------------------
    SHORTHAND = [
        ("CIBH", "88111009", "Altered bowel function (finding)", "finding"),
        ("Change in bowel habit", "88111009", "Altered bowel function (finding)", "finding"),
        ("change in bowel habit", "88111009", "Altered bowel function (finding)", "finding"),
        ("Fibroscan", "441491005", "Ultrasound elastography of liver (procedure)", "procedure"),
        ("fibroscan", "441491005", "Ultrasound elastography of liver (procedure)", "procedure"),
        ("NWB", "261999007", "Non-weight-bearing (finding)", "finding"),
        ("non-weight-bearing", "261999007", "Non-weight-bearing (finding)", "finding"),
        ("Non-weight-bearing", "261999007", "Non-weight-bearing (finding)", "finding"),
        ("apyrexic", "86699002", "Apyrexial (situation)", "situation"),
        ("Apyrexic", "86699002", "Apyrexial (situation)", "situation"),
        ("Apyrexial", "86699002", "Apyrexial (situation)", "situation"),
        ("apyrexial", "86699002", "Apyrexial (situation)", "situation"),
    ]
    for form, cid, fsn, label in SHORTHAND:
        entries.append(_sf(form, cid, fsn, label))

    # -----------------------------------------------------------------------
    # 1d. Common symptoms / misspellings
    # -----------------------------------------------------------------------
    EXISTING = [
        ("cough", "49727002", "Cough (finding)", "finding"),
        ("Cough", "49727002", "Cough (finding)", "finding"),
        ("sore throat", "162397003", "Sore throat symptom (finding)", "finding"),
        ("Sore throat", "162397003", "Sore throat symptom (finding)", "finding"),
        ("headache", "25064002", "Headache (finding)", "finding"),
        ("Headache", "25064002", "Headache (finding)", "finding"),
        ("diarrhoea", "62315008", "Diarrhea (finding)", "finding"),
        ("Diarrhoea", "62315008", "Diarrhea (finding)", "finding"),
        ("diarrhea", "62315008", "Diarrhea (finding)", "finding"),
        ("abdominal pain", "21522001", "Abdominal pain (finding)", "finding"),
        ("Abdominal pain", "21522001", "Abdominal pain (finding)", "finding"),
        ("productive cough", "28743005", "Productive cough (finding)", "finding"),
        ("Productive cough", "28743005", "Productive cough (finding)", "finding"),
        ("?DM", "73211009", "Diabetes mellitus (disorder)", "disorder"),
        ("?Hypothyroid", "40930008", "Hypothyroidism (disorder)", "disorder"),
        ("?hypothyroid", "40930008", "Hypothyroidism (disorder)", "disorder"),
        ("High Cholesterol", "13644009", "Hypercholesterolaemia (disorder)", "disorder"),
        ("high cholesterol", "13644009", "Hypercholesterolaemia (disorder)", "disorder"),
        ("COPD", "13645005", "Chronic obstructive lung disease (disorder)", "disorder"),
        ("NDH", "714628002", "Prediabetes (finding)", "finding"),
        ("Pre-diabetes", "714628002", "Prediabetes (finding)", "finding"),
        ("pre-diabetes", "714628002", "Prediabetes (finding)", "finding"),
        ("prediabetes", "714628002", "Prediabetes (finding)", "finding"),
        # misspellings
        ("hematemsis", "8765009", "Hematemesis (disorder)", "disorder"),
        ("haematemesis", "8765009", "Hematemesis (disorder)", "disorder"),
        ("virtigo", "399153001", "Vertigo (disorder)", "disorder"),
        ("moodswings", "18963009", "Mood swings (finding)", "finding"),
        ("mood swings", "18963009", "Mood swings (finding)", "finding"),
        ("elevated bilirubin", "14783006", "Hyperbilirubinemia (disorder)", "disorder"),
        ("raised bilirubin", "14783006", "Hyperbilirubinemia (disorder)", "disorder"),
    ]
    for form, cid, fsn, label in EXISTING:
        entries.append(_sf(form, cid, fsn, label))

    return entries


def build_phase1_ignore_rules() -> list[IgnoreRuleEntry]:
    return [
        IgnoreRuleEntry(
            entity_text="SSKIN",
            entity_label="",
            reason=(
                "SSKIN is a structured assessment template name "
                "(Surface/Skin/Keep-moving/Incontinence/Nutrition) used as a section "
                "header in clinical documentation. Individual items within the template "
                "should be coded, not the template name itself."
            ),
        ),
        IgnoreRuleEntry(
            entity_text="QMC",
            entity_label="",
            reason="QMC is a non-clinical abbreviation (Quality Management / hospital code), not a codeable clinical concept.",
        ),
    ]


# ---------------------------------------------------------------------------
# Phase 3 data definitions
# ---------------------------------------------------------------------------

def build_phase3_fixes() -> list[Phase3Fix]:
    return [
        Phase3Fix(
            entity_text="tongue sore",
            old_concept_id=None,
            new_concept_id="30731004",
            new_concept_fsn="Glossodynia (disorder)",
            new_entity_label="disorder",
            note="User-corrected: was 399031001 Mouth ulcer",
        ),
        Phase3Fix(
            entity_text="Tongue sore",
            old_concept_id=None,
            new_concept_id="30731004",
            new_concept_fsn="Glossodynia (disorder)",
            new_entity_label="disorder",
        ),
        Phase3Fix(
            entity_text="sore tongue",
            old_concept_id=None,
            new_concept_id="30731004",
            new_concept_fsn="Glossodynia (disorder)",
            new_entity_label="disorder",
        ),
        Phase3Fix(
            entity_text="dad gets drunk regularly",
            old_concept_id=None,
            new_concept_id="266890009",
            new_concept_fsn="Family history of alcoholism (situation)",
            new_entity_label="situation",
            assertion="family",
            note="User-corrected: family assertion",
        ),
        Phase3Fix(
            entity_text="low mood",
            old_concept_id=None,
            new_concept_id="366979004",
            new_concept_fsn="Depressed mood (finding)",
            new_entity_label="finding",
        ),
        Phase3Fix(
            entity_text="Low mood",
            old_concept_id=None,
            new_concept_id="366979004",
            new_concept_fsn="Depressed mood (finding)",
            new_entity_label="finding",
        ),
        Phase3Fix(
            entity_text="low in mood",
            old_concept_id=None,
            new_concept_id="366979004",
            new_concept_fsn="Depressed mood (finding)",
            new_entity_label="finding",
        ),
        Phase3Fix(
            entity_text="Persistent low mood",
            old_concept_id=None,
            new_concept_id="366979004",
            new_concept_fsn="Depressed mood (finding)",
            new_entity_label="finding",
        ),
        Phase3Fix(
            entity_text="persistent low mood",
            old_concept_id=None,
            new_concept_id="366979004",
            new_concept_fsn="Depressed mood (finding)",
            new_entity_label="finding",
        ),
        Phase3Fix(
            entity_text="anxiety symptoms",
            old_concept_id=None,
            new_concept_id="48694002",
            new_concept_fsn="Anxiety (finding)",
            new_entity_label="finding",
        ),
        Phase3Fix(
            entity_text="Anxiety symptoms",
            old_concept_id=None,
            new_concept_id="48694002",
            new_concept_fsn="Anxiety (finding)",
            new_entity_label="finding",
        ),
        Phase3Fix(
            entity_text="Recurrent Diarrhoea",
            old_concept_id=None,
            new_concept_id="236071009",
            new_concept_fsn="Chronic diarrhea (disorder)",
            new_entity_label="disorder",
        ),
        Phase3Fix(
            entity_text="recurrent diarrhoea",
            old_concept_id=None,
            new_concept_id="236071009",
            new_concept_fsn="Chronic diarrhea (disorder)",
            new_entity_label="disorder",
        ),
    ]


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------

def run_phase1(driver, execute: bool, report: Report):
    """Surface forms for medications, cancers, shorthand, ignore rules."""
    surface_forms = build_phase1_surface_forms()
    ignore_rules = build_phase1_ignore_rules()

    logger.info("Phase 1: %d surface forms to upsert, %d ignore rules", len(surface_forms), len(ignore_rules))

    # Group surface forms by canonical entity_text for resolving reviews
    # We track which texts we've already resolved to avoid duplicates
    resolved_texts: set[str] = set()

    with driver.session() as session:
        for idx, entry in enumerate(surface_forms):
            if idx % 20 == 0:
                logger.info("  Phase 1 progress: %d/%d surface forms", idx, len(surface_forms))

            upsert_surface_form(session, entry, execute, report)

            # Resolve any pending CodingReview items for this exact form text
            # (only once per unique text to avoid duplicate report entries)
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

        for rule in ignore_rules:
            upsert_ignore_rule(session, rule, execute, report)

    logger.info("Phase 1 complete. Surface forms: %d, Ignore rules: %d",
                len(report.surface_forms_added), len(report.ignore_rules_added))


def run_phase2(driver, execute: bool, report: Report):
    """Bulk-accept observable_entity->procedure lab test mappings."""
    with driver.session() as session:
        lab_tests = list(session.run(GET_LAB_TEST_REVIEWS))

    logger.info("Phase 2: %d unique lab test texts (observable_entity->procedure) to process", len(lab_tests))

    if not lab_tests:
        logger.info("Phase 2: nothing to do (no observable_entity->procedure mismatches found)")
        return

    with driver.session() as session:
        for idx, row in enumerate(lab_tests):
            text = row["text"]
            concept_id = row["concept_id"]
            snomed_term = row["snomed_term"]

            if idx % 10 == 0:
                logger.info("  Phase 2 progress: %d/%d", idx, len(lab_tests))

            if not concept_id:
                logger.debug("  Skipping %r — no concept_id in CodingReview", text)
                continue

            # 1. Add surface form (procedure label)
            sf_entry = _sf(text, concept_id, snomed_term or text, "procedure")
            upsert_surface_form(session, sf_entry, execute, report)

            # 2. Update entities_json BEFORE resolving reviews (review query filters on entity_label,
            #    which becomes inaccessible after batch_resolve changes resolved=true)
            update_entities_json_for_text(
                session,
                entity_text=text,
                old_label="observable_entity",
                new_label="procedure",
                execute=execute,
                report=report,
            )

            # 3. Batch-resolve the CodingReviews (after entities_json update)
            batch_resolve(
                session,
                entity_text=text,
                concept_id=concept_id,
                concept_fsn=snomed_term or text,
                assertion="present",
                execute=execute,
                report=report,
            )

    logger.info("Phase 2 complete.")


def run_phase3(driver, execute: bool, report: Report):
    """Fix bad SNOMED matches with corrected codes."""
    fixes = build_phase3_fixes()
    logger.info("Phase 3: %d bad-match fixes to apply", len(fixes))

    with driver.session() as session:
        for fix in fixes:
            logger.info("  Fix: %r -> %s | %s (assertion=%s)",
                        fix.entity_text, fix.new_concept_id, fix.new_concept_fsn, fix.assertion)

            # 1. Add correct surface form
            sf_entry = _sf(fix.entity_text, fix.new_concept_id, fix.new_concept_fsn,
                           fix.new_entity_label, assertion=fix.assertion)
            upsert_surface_form(session, sf_entry, execute, report)

            # 2. Batch-resolve reviews with corrected concept
            batch_resolve(
                session,
                entity_text=fix.entity_text,
                concept_id=fix.new_concept_id,
                concept_fsn=fix.new_concept_fsn,
                assertion=fix.assertion,
                execute=execute,
                report=report,
            )

            # 3. Update entities_json if label changed
            if fix.old_concept_id is not None or fix.new_entity_label:
                # We update all matching entity_text regardless of old_label
                # since we may have multiple labels in the queue for the same text
                for from_label in ["finding", "disorder", "situation", "observable_entity", "procedure"]:
                    if from_label != fix.new_entity_label:
                        update_entities_json_for_text(
                            session,
                            entity_text=fix.entity_text,
                            old_label=from_label,
                            new_label=fix.new_entity_label,
                            execute=execute,
                            report=report,
                        )

    logger.info("Phase 3 complete.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="HITL Queue Remediation")
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually write to Neo4j (default: dry-run)",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Run only a specific phase (default: all)",
    )
    args = parser.parse_args()

    execute = args.execute
    mode = "EXECUTE" if execute else "DRY-RUN"
    logger.info("=== HITL Queue Remediation — %s ===", mode)

    driver = get_neo4j_driver()
    logger.info("Connected to Neo4j")

    report = Report(dry_run=not execute)

    try:
        if args.phase is None or args.phase == 1:
            logger.info("--- Phase 1: Surface forms + ignore rules ---")
            run_phase1(driver, execute, report)

        if args.phase is None or args.phase == 2:
            logger.info("--- Phase 2: Lab test observable_entity->procedure ---")
            run_phase2(driver, execute, report)

        if args.phase is None or args.phase == 3:
            logger.info("--- Phase 3: Bad SNOMED match fixes ---")
            run_phase3(driver, execute, report)

    finally:
        driver.close()

    # Write report
    report_dict = report.to_dict()
    output_path = ROOT / "scripts" / "hitl_remediation_report.json"
    output_path.write_text(json.dumps(report_dict, indent=2, default=str))
    logger.info("Report written to %s", output_path)

    # Summary
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
