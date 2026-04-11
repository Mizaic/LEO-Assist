"""Smart HITL Terminology Lookup — 3-pass search with clinical knowledge + graph disambiguation.

Pass 1: Raw search (same as hitl_remaining_lookup, top-1 for comparison)
Pass 2: Label-filtered search (semantic_tag=entity_label, top-1)
Pass 3: Smart search using corrected/expanded term from clinical knowledge dict
Pass 4: Multi-tag graph traversal — searches procedure / observable_entity / finding,
        calls /concepts/{id}/related to cross-validate via SNOMED ontology edges
        (INTERPRETS, HAS_COMPONENT), and selects the best concept deterministically.
        Only runs for items in the observable_entity / procedure / finding triangle
        where there is genuine tag ambiguity.

Auto-recommendation logic:
  ACCEPT_FILTERED  — label-filtered top-1 score >= threshold AND tag matches
  ACCEPT_SMART     — smart search produced a confident match
  ACCEPT_RAW       — raw top-1 tag matches entity label and score >= threshold
  IGNORE           — entity text is non-clinical noise
  GRAPH_PICK       — deterministic graph traversal resolved the best concept
  MANUAL_REVIEW    — none of the above

Usage:
    .venv\\Scripts\\python scripts\\_smart_hitl_lookup.py
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from neo4j import GraphDatabase

TERM_API = "http://localhost:8001"
SCORE_THRESHOLD = 5.0  # minimum score to accept a match

# Semantic tags where procedure/observable_entity/finding can legitimately be
# confused — trigger multi-tag graph disambiguation for these.
LAB_AMBIGUOUS_TAGS = {"observable_entity", "procedure", "finding"}

# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------


def get_driver():
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    driver.verify_connectivity()
    return driver


GET_PENDING = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false AND t.include = true
WITH cr.entity_text        AS entity_text,
     cr.entity_label       AS entity_label,
     cr.assertion          AS assertion,
     cr.snomed_concept_id  AS snomed_concept_id,
     cr.snomed_term        AS snomed_term,
     cr.decision_tier      AS tier,
     cr.suggested_label    AS suggested_label,
     count(cr)             AS occurrences,
     head(collect(t.text))          AS sample_text,
     head(collect(t.entities_json)) AS sample_entities
RETURN entity_text, entity_label, assertion,
       snomed_concept_id, snomed_term, tier, suggested_label,
       occurrences, sample_text, sample_entities
ORDER BY occurrences DESC, entity_text
"""

# ---------------------------------------------------------------------------
# Clinical knowledge dictionary
# Maps entity_text (lower-stripped) -> (smart_search_term, hint_snomed_id, hint_fsn, hint_label, ignore)
# hint_snomed_id may be None if we just want a better search term
# ignore=True means this is non-clinical noise
# ---------------------------------------------------------------------------

KNOWLEDGE: dict[str, tuple[str, str | None, str | None, str | None, bool]] = {
    # -----------------------------------------------------------------------
    # Misspellings
    # -----------------------------------------------------------------------
    "asthmna": ("asthma", "195967001", "Asthma (disorder)", "disorder", False),
    "iburofen": ("ibuprofen", "387207008", "Ibuprofen (substance)", "substance", False),
    "paracetomol": (
        "paracetamol",
        "387517004",
        "Paracetamol (substance)",
        "substance",
        False,
    ),
    "morpine": ("morphine", "373529000", "Morphine (substance)", "substance", False),
    "oramorph": (
        "oral morphine",
        "373529000",
        "Morphine (substance)",
        "substance",
        False,
    ),
    "follicultitis type infection": (
        "folliculitis",
        "13600006",
        "Folliculitis (disorder)",
        "disorder",
        False,
    ),
    "vasculopath": (
        "vasculopathy",
        "27550009",
        "Vasculopathy (disorder)",
        "disorder",
        False,
    ),
    "vasculopath,low mood, predm hx": (
        "vasculopathy",
        "27550009",
        "Vasculopathy (disorder)",
        "disorder",
        False,
    ),
    "mild neurtophilia": (
        "neutrophilia",
        "165518003",
        "Neutrophilia (finding)",
        "finding",
        False,
    ),
    "mild sorethroat": (
        "sore throat",
        "162397003",
        "Sore throat symptom (finding)",
        "finding",
        False,
    ),
    "tight cxhest": (
        "tight chest",
        "23924001",
        "Tight chest (finding)",
        "finding",
        False,
    ),
    "sangury": ("strangury", "49650001", "Strangury (finding)", "finding", False),
    "duiretics": ("diuretics", "372695000", "Diuretic (substance)", "substance", False),
    "lemsip": ("Lemsip", None, None, "medicinal_product", False),
    "dianette": ("co-cyprindiol", None, None, "medicinal_product", False),
    "inadine": ("povidone-iodine dressing", None, None, "medicinal_product", False),
    "capcity": (
        "mental capacity",
        "413292003",
        "Mental capacity (observable entity)",
        "observable_entity",
        False,
    ),
    "disharged": ("discharged", None, None, "situation", False),
    "redressed": ("wound redressing", None, None, "procedure", False),
    "subarticular": ("subchondral", None, None, "qualifier_value", False),
    "haematemisis": (
        "haematemesis",
        "8765009",
        "Hematemesis (disorder)",
        "disorder",
        False,
    ),
    "haematuria": (
        "haematuria",
        "34436003",
        "Blood in urine (finding)",
        "finding",
        False,
    ),
    "Haematuria": (
        "haematuria",
        "34436003",
        "Blood in urine (finding)",
        "finding",
        False,
    ),
    "mild sorethroat": (
        "sore throat",
        "162397003",
        "Sore throat symptom (finding)",
        "finding",
        False,
    ),
    "3w hx of diarrhoae": (
        "diarrhoea",
        "62315008",
        "Diarrhea (finding)",
        "finding",
        False,
    ),
    "hx of diarrhoea, improved": (
        "diarrhoea",
        "62315008",
        "Diarrhea (finding)",
        "finding",
        False,
    ),
    "abdominal cramps": (
        "abdominal cramp",
        "55300003",
        "Cramp (finding)",
        "finding",
        False,
    ),
    "chesty cough": (
        "productive cough",
        "28743005",
        "Productive cough (finding)",
        "finding",
        False,
    ),
    "tickly cough": (
        "tickly cough",
        "901000172101",
        "Dry tickly cough (finding)",
        "finding",
        False,
    ),
    "non prod cough": (
        "non-productive cough",
        "274034003",
        "Non-productive cough (finding)",
        "finding",
        False,
    ),
    "Non prod cough": (
        "non-productive cough",
        "274034003",
        "Non-productive cough (finding)",
        "finding",
        False,
    ),
    "looser stools": (
        "loose stools",
        "27731006",
        "Soft stool (finding)",
        "finding",
        False,
    ),
    "fevers": ("fever", "386661006", "Fever (finding)", "finding", False),
    "polyps": (
        "intestinal polyp",
        "444408007",
        "Polyp of colon (disorder)",
        "disorder",
        False,
    ),
    "8-day migraine": (
        "migraine",
        "37796009",
        "Migraine (disorder)",
        "disorder",
        False,
    ),
    "viral lrti": (
        "viral lower respiratory infection",
        "312134000",
        "Viral lower respiratory infection (disorder)",
        "disorder",
        False,
    ),
    "viral LRTI": (
        "viral lower respiratory infection",
        "312134000",
        "Viral lower respiratory infection (disorder)",
        "disorder",
        False,
    ),
    # -----------------------------------------------------------------------
    # Abbreviations / acronyms
    # -----------------------------------------------------------------------
    "gca": (
        "giant cell arteritis",
        "414341000",
        "Giant cell arteritis (disorder)",
        "disorder",
        False,
    ),
    "GCA": (
        "giant cell arteritis",
        "414341000",
        "Giant cell arteritis (disorder)",
        "disorder",
        False,
    ),
    "sob": (
        "dyspnoea shortness of breath",
        "267036007",
        "Dyspnea (finding)",
        "finding",
        False,
    ),
    "SOB": (
        "dyspnoea shortness of breath",
        "267036007",
        "Dyspnea (finding)",
        "finding",
        False,
    ),
    "dvt": (
        "deep vein thrombosis",
        "128053003",
        "Deep venous thrombosis (disorder)",
        "disorder",
        False,
    ),
    "DVT": (
        "deep vein thrombosis",
        "128053003",
        "Deep venous thrombosis (disorder)",
        "disorder",
        False,
    ),
    "tfts": (
        "thyroid function test",
        "61153008",
        "Thyroid function tests (procedure)",
        "procedure",
        False,
    ),
    "TFTs": (
        "thyroid function tests",
        "61153008",
        "Thyroid function tests (procedure)",
        "procedure",
        False,
    ),
    "nash": (
        "non-alcoholic steatohepatitis",
        "442685003",
        "Metabolic dysfunction-associated steatohepatitis (disorder)",
        "disorder",
        False,
    ),
    "NASH": (
        "non-alcoholic steatohepatitis",
        "442685003",
        "Metabolic dysfunction-associated steatohepatitis (disorder)",
        "disorder",
        False,
    ),
    "turbt": (
        "transurethral resection bladder tumour",
        "386792000",
        "Transurethral excision of neoplasm of urinary bladder (procedure)",
        "procedure",
        False,
    ),
    "TURBT": (
        "transurethral resection bladder tumour",
        "386792000",
        "Transurethral excision of neoplasm of urinary bladder (procedure)",
        "procedure",
        False,
    ),
    "ht": (
        "hypertension",
        "38458008",
        "Hypertensive disorder, systemic arterial (disorder)",
        "disorder",
        False,
    ),
    "HT": (
        "hypertension",
        "38458008",
        "Hypertensive disorder, systemic arterial (disorder)",
        "disorder",
        False,
    ),
    "uti": (
        "urinary tract infection",
        "68566005",
        "Urinary tract infectious disease (disorder)",
        "disorder",
        False,
    ),
    "UTI": (
        "urinary tract infection",
        "68566005",
        "Urinary tract infectious disease (disorder)",
        "disorder",
        False,
    ),
    "?UTI": (
        "urinary tract infection",
        "68566005",
        "Urinary tract infectious disease (disorder)",
        "disorder",
        False,
    ),
    "iapt": (
        "improving access to psychological therapies",
        "1026111000000108",
        "Improving Access to Psychological Therapies low intensity therapy (regime/therapy)",
        "regime_therapy",
        False,
    ),
    "IAPT": (
        "improving access to psychological therapies",
        "1026111000000108",
        "Improving Access to Psychological Therapies low intensity therapy (regime/therapy)",
        "regime_therapy",
        False,
    ),
    "referred via IAPT": (
        "improving access to psychological therapies referral",
        "380201000000109",
        "Referral to improving access to psychological therapies programme (procedure)",
        "procedure",
        False,
    ),
    # FIT test (the procedure/request — observable entity, no result implied)
    "fit test": (
        "faecal immunochemical test",
        "1049361000000101",
        "Quantitative faecal immunochemical test (observable entity)",
        "observable_entity",
        False,
    ),
    "FIT test": (
        "faecal immunochemical test",
        "1049361000000101",
        "Quantitative faecal immunochemical test (observable entity)",
        "observable_entity",
        False,
    ),
    # FIT negative / normal RESULT — the test came back negative (blood not detected).
    # These are FINDINGS, not the observable test entity.
    "FIT neg": (
        "faecal immunochemical test result negative",
        "168360006",
        "Feces occult blood test negative (finding)",
        "finding",
        False,
    ),
    "FIT neg.": (
        "faecal immunochemical test result negative",
        "168360006",
        "Feces occult blood test negative (finding)",
        "finding",
        False,
    ),
    "FIT negative": (
        "faecal immunochemical test result negative",
        "168360006",
        "Feces occult blood test negative (finding)",
        "finding",
        False,
    ),
    "NEGATIVE FIT": (
        "faecal immunochemical test result negative",
        "168360006",
        "Feces occult blood test negative (finding)",
        "finding",
        False,
    ),
    "negative FIT": (
        "faecal immunochemical test result negative",
        "168360006",
        "Feces occult blood test negative (finding)",
        "finding",
        False,
    ),
    "negative FIT test": (
        "faecal immunochemical test result negative",
        "168360006",
        "Feces occult blood test negative (finding)",
        "finding",
        False,
    ),
    "FIT normal": (
        "faecal immunochemical test result normal",
        "168360006",
        "Feces occult blood test negative (finding)",
        "finding",
        False,
    ),
    "Normal FIT": (
        "faecal immunochemical test result normal",
        "168360006",
        "Feces occult blood test negative (finding)",
        "finding",
        False,
    ),
    "normal FIT": (
        "faecal immunochemical test result normal",
        "168360006",
        "Feces occult blood test negative (finding)",
        "finding",
        False,
    ),
    # FIT positive / high RESULT — blood detected above threshold.
    # These are FINDINGS (occult blood detected by immunoassay).
    "FIT pos": (
        "faecal immunochemical test positive",
        "71711000112103",
        "Occult blood detected in feces by immunoassay (finding)",
        "finding",
        False,
    ),
    "FIT pos.": (
        "faecal immunochemical test positive",
        "71711000112103",
        "Occult blood detected in feces by immunoassay (finding)",
        "finding",
        False,
    ),
    "FIT positive": (
        "faecal immunochemical test positive",
        "71711000112103",
        "Occult blood detected in feces by immunoassay (finding)",
        "finding",
        False,
    ),
    "POSITIVE FIT": (
        "faecal immunochemical test positive",
        "71711000112103",
        "Occult blood detected in feces by immunoassay (finding)",
        "finding",
        False,
    ),
    "positive FIT": (
        "faecal immunochemical test positive",
        "71711000112103",
        "Occult blood detected in feces by immunoassay (finding)",
        "finding",
        False,
    ),
    "positive FIT test": (
        "faecal immunochemical test positive",
        "71711000112103",
        "Occult blood detected in feces by immunoassay (finding)",
        "finding",
        False,
    ),
    "FIT >200": (
        "faecal immunochemical test result high",
        "71711000112103",
        "Occult blood detected in feces by immunoassay (finding)",
        "finding",
        False,
    ),
    "dm": (
        "diabetes mellitus",
        "73211009",
        "Diabetes mellitus (disorder)",
        "disorder",
        False,
    ),
    "knwon DM": (
        "diabetes mellitus",
        "73211009",
        "Diabetes mellitus (disorder)",
        "disorder",
        False,
    ),
    "known dm": (
        "diabetes mellitus",
        "73211009",
        "Diabetes mellitus (disorder)",
        "disorder",
        False,
    ),
    "ild mdt": (
        "interstitial lung disease",
        "233703007",
        "Interstitial lung disease (disorder)",
        "disorder",
        False,
    ),
    "ILD mdt": (
        "interstitial lung disease",
        "233703007",
        "Interstitial lung disease (disorder)",
        "disorder",
        False,
    ),
    "2ww": (
        "fast track cancer referral",
        "199251000000107",
        "Fast track cancer referral (procedure)",
        "procedure",
        False,
    ),
    "2WW": (
        "fast track cancer referral",
        "199251000000107",
        "Fast track cancer referral (procedure)",
        "procedure",
        False,
    ),
    "2WW Referral": (
        "fast track cancer referral",
        "199251000000107",
        "Fast track cancer referral (procedure)",
        "procedure",
        False,
    ),
    "2ww referral": (
        "fast track cancer referral",
        "199251000000107",
        "Fast track cancer referral (procedure)",
        "procedure",
        False,
    ),
    "2WW colorectal": (
        "fast track colorectal cancer referral",
        "199251000000107",
        "Fast track cancer referral (procedure)",
        "procedure",
        False,
    ),
    "2ww and it's outcome where pt did not want any invasive investigations": (
        "declined cancer investigations",
        None,
        None,
        "situation",
        False,
    ),
    "referred on 2ww": (
        "fast track cancer referral",
        "199251000000107",
        "Fast track cancer referral (procedure)",
        "procedure",
        False,
    ),
    "Chol": (
        "cholesterol level",
        "850981000000101",
        "Cholesterol level (observable entity)",
        "observable_entity",
        False,
    ),
    "chol": (
        "cholesterol level",
        "850981000000101",
        "Cholesterol level (observable entity)",
        "observable_entity",
        False,
    ),
    "Chol 6.4": (
        "cholesterol level",
        "850981000000101",
        "Cholesterol level (observable entity)",
        "observable_entity",
        False,
    ),
    "LDL Chol": (
        "LDL cholesterol level",
        "850981000000101",
        "Cholesterol level (observable entity)",
        "observable_entity",
        False,
    ),
    "Serum Chol": (
        "serum cholesterol level",
        "850981000000101",
        "Cholesterol level (observable entity)",
        "observable_entity",
        False,
    ),
    "ALP": (
        "alkaline phosphatase level",
        "1000621000000104",
        "Serum alkaline phosphatase level (observable entity)",
        "observable_entity",
        False,
    ),
    "ALP 400": (
        "alkaline phosphatase level raised",
        "1000621000000104",
        "Serum alkaline phosphatase level (observable entity)",
        "observable_entity",
        False,
    ),
    "ALP remains raised": (
        "alkaline phosphatase raised",
        "166717003",
        "Serum alkaline phosphatase raised (finding)",
        "finding",
        False,
    ),
    "ALP rising": (
        "alkaline phosphatase rising",
        "166717003",
        "Serum alkaline phosphatase raised (finding)",
        "finding",
        False,
    ),
    "CREATININE": (
        "creatinine level",
        "1000731000000107",
        "Serum creatinine level (observable entity)",
        "observable_entity",
        False,
    ),
    "Creatinine": (
        "creatinine level",
        "1000731000000107",
        "Serum creatinine level (observable entity)",
        "observable_entity",
        False,
    ),
    "creatinine": (
        "creatinine level",
        "1000731000000107",
        "Serum creatinine level (observable entity)",
        "observable_entity",
        False,
    ),
    "repeat U&E": (
        "urea and electrolytes",
        "252167001",
        "Measurement of urea and electrolytes (procedure)",
        "procedure",
        False,
    ),
    "GFR calculated abbreviated MDRD": (
        "glomerular filtration rate MDRD",
        "1020291000000106",
        "Glomerular filtration rate calculated by abbreviated MDRD (observable entity)",
        "observable_entity",
        False,
    ),
    "EGFR BY MDRD (F) / 1.73M2": (
        "estimated glomerular filtration rate",
        "1020291000000106",
        "Glomerular filtration rate calculated by abbreviated MDRD (observable entity)",
        "observable_entity",
        False,
    ),
    "GFR calculated abbreviated MDRD - GFR calculated abbreviated MDRD": (
        "glomerular filtration rate MDRD",
        "1020291000000106",
        "Glomerular filtration rate calculated by abbreviated MDRD (observable entity)",
        "observable_entity",
        False,
    ),
    "pr bleeding": (
        "rectal bleeding",
        "12063002",
        "Rectal hemorrhage (disorder)",
        "disorder",
        False,
    ),
    "PR bleeding": (
        "rectal bleeding",
        "12063002",
        "Rectal hemorrhage (disorder)",
        "disorder",
        False,
    ),
    "drop in egr": (
        "drop in eGFR",
        "431314004",
        "Decrease in glomerular filtration rate (finding)",
        "finding",
        False,
    ),
    "raised gamma GT": (
        "gamma GT raised",
        "166787006",
        "Serum gamma glutamyl transferase raised (finding)",
        "finding",
        False,
    ),
    "GGT has gotten worse": (
        "gamma GT raised",
        "166787006",
        "Serum gamma glutamyl transferase raised (finding)",
        "finding",
        False,
    ),
    "hb1ac stable": (
        "HbA1c stable",
        "413144006",
        "Target blood glucose level achieved (finding)",
        "finding",
        False,
    ),
    "high TGs": (
        "hypertriglyceridaemia",
        "302870006",
        "Hypertriglyceridemia (disorder)",
        "disorder",
        False,
    ),
    "NV intact": (
        "neurovascular intact",
        "428119001",
        "Procedure on extremity (procedure)",
        "finding",
        False,
    ),
    "SLR normal": (
        "straight leg raise normal",
        "271773007",
        "Straight leg raise test response (observable entity)",
        "observable_entity",
        False,
    ),
    "Calves SNT": (
        "calves soft non-tender",
        "300848003",
        "Soft calves (finding)",
        "finding",
        False,
    ),
    "Asthma control test 12": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "Asthma control test 16": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "Asthma control test 17": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "Asthma control test 19": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "Asthma control test 20": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "Asthma control test 21": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "Asthma control test 23": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "Asthma control test 24": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "Asthma control test: 17": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "Asthma control test: 19": (
        "asthma control test",
        "443450003",
        "Asthma control test (assessment scale)",
        "assessment_scale",
        False,
    ),
    "ADHD Questionnaire": (
        "ADHD questionnaire assessment",
        "769390009",
        "World Health Organization Adult ADHD Self-Report Scale (assessment scale)",
        "assessment_scale",
        False,
    ),
    "level of shortness of breath": (
        "shortness of breath assessment scale",
        "135833008",
        "Cardiovascular Limitations and Symptoms Profile shortness of breath score (assessment scale)",
        "assessment_scale",
        False,
    ),
    "physical limitations": (
        "functional limitations assessment",
        "273728006",
        "Rand functional limitations battery (assessment scale)",
        "assessment_scale",
        False,
    ),
    # -----------------------------------------------------------------------
    # Context stripping / clinical rephrasing
    # -----------------------------------------------------------------------
    "2019 smear HPV positive": (
        "HPV positive cervical smear",
        "441667007",
        "Abnormal cervical Papanicolaou smear with human papillomavirus detected (finding)",
        "finding",
        False,
    ),
    "anemia of chronic dx": (
        "anaemia of chronic disease",
        "234347009",
        "Anemia of chronic disease (disorder)",
        "disorder",
        False,
    ),
    "Anemia of Chronic Dx": (
        "anaemia of chronic disease",
        "234347009",
        "Anemia of chronic disease (disorder)",
        "disorder",
        False,
    ),
    "bony mets r humerus": (
        "bone metastasis humerus",
        "94222008",
        "Secondary malignant neoplasm of bone (disorder)",
        "disorder",
        False,
    ),
    "bony mets R humerus": (
        "bone metastasis humerus",
        "94222008",
        "Secondary malignant neoplasm of bone (disorder)",
        "disorder",
        False,
    ),
    "bony mets pelvic girdle": (
        "bone metastasis pelvis",
        "94222008",
        "Secondary malignant neoplasm of bone (disorder)",
        "disorder",
        False,
    ),
    "post op fistula wound": (
        "postoperative fistula",
        "312413001",
        "Wound fistula (disorder)",
        "disorder",
        False,
    ),
    "severe OA in Lx": (
        "osteoarthritis lumbar spine",
        "73761001",
        "Lumbar spondylosis (disorder)",
        "disorder",
        False,
    ),
    "# to R ankle": (
        "fracture right ankle",
        "16114001",
        "Fracture of ankle (disorder)",
        "disorder",
        False,
    ),
    "broken ankle": (
        "fracture ankle",
        "16114001",
        "Fracture of ankle (disorder)",
        "disorder",
        False,
    ),
    "Broken ankle": (
        "fracture ankle",
        "16114001",
        "Fracture of ankle (disorder)",
        "disorder",
        False,
    ),
    "cold": ("common cold", "82272006", "Common cold (disorder)", "disorder", False),
    "Cold": ("common cold", "82272006", "Common cold (disorder)", "disorder", False),
    "resp infection": (
        "respiratory tract infection",
        "275498002",
        "Respiratory tract infection (disorder)",
        "disorder",
        False,
    ),
    "chest infection": (
        "lower respiratory tract infection",
        "50417007",
        "Lower respiratory tract infection (disorder)",
        "disorder",
        False,
    ),
    "h. pylori positive": (
        "Helicobacter pylori infection positive",
        "513161000000105",
        "Helicobacter pylori test positive (finding)",
        "finding",
        False,
    ),
    "H. pylori positive": (
        "Helicobacter pylori infection positive",
        "513161000000105",
        "Helicobacter pylori test positive (finding)",
        "finding",
        False,
    ),
    "H. pylori infection": (
        "Helicobacter pylori infection",
        "721730009",
        "Infection caused by Helicobacter pylori (disorder)",
        "disorder",
        False,
    ),
    "new pre-diabetic": (
        "prediabetes",
        "714628002",
        "Prediabetes (finding)",
        "finding",
        False,
    ),
    "New pre-diabetic": (
        "prediabetes",
        "714628002",
        "Prediabetes (finding)",
        "finding",
        False,
    ),
    "pre-diabetic": (
        "prediabetes",
        "714628002",
        "Prediabetes (finding)",
        "finding",
        False,
    ),
    "new prediabetes": (
        "prediabetes",
        "714628002",
        "Prediabetes (finding)",
        "finding",
        False,
    ),
    "cobalamin def": (
        "cobalamin deficiency",
        "190634004",
        "Cobalamin deficiency (disorder)",
        "disorder",
        False,
    ),
    "Cobalamin def": (
        "cobalamin deficiency",
        "190634004",
        "Cobalamin deficiency (disorder)",
        "disorder",
        False,
    ),
    "levo dosing": ("levothyroxine dosing", None, None, "procedure", False),
    "levo": ("levothyroxine", None, None, "substance", False),
    "Endocrine therapy": (
        "endocrine treatment",
        "170814007",
        "Endocrine treatment change (regime/therapy)",
        "regime_therapy",
        False,
    ),
    "Asthma annual review": (
        "asthma annual review",
        "394700004",
        "Asthma annual review (regime/therapy)",
        "regime_therapy",
        False,
    ),
    "Asthma resolved": (
        "asthma resolved",
        "162660004",
        "Asthma resolved (finding)",
        "finding",
        False,
    ),
    "Injured left knee": (
        "knee injury",
        "444798002",
        "Injury of knee (disorder)",
        "disorder",
        False,
    ),
    "Left shoulder contussion": (
        "left shoulder contusion",
        "284369006",
        "Contusion of left shoulder (disorder)",
        "disorder",
        False,
    ),
    "Stroke and cerebrovascular accident unspecified": (
        "cerebrovascular accident",
        "230690007",
        "Cerebrovascular accident (disorder)",
        "disorder",
        False,
    ),
    "arthritis": ("arthritis", "3723001", "Arthritis (disorder)", "disorder", False),
    "Osteoarthritis": (
        "osteoarthritis",
        "396275006",
        "Osteoarthritis (disorder)",
        "disorder",
        False,
    ),
    "Type 2 diabetes": (
        "type 2 diabetes mellitus",
        "44054006",
        "Diabetes mellitus type 2 (disorder)",
        "disorder",
        False,
    ),
    "type 2 diabetes": (
        "type 2 diabetes mellitus",
        "44054006",
        "Diabetes mellitus type 2 (disorder)",
        "disorder",
        False,
    ),
    "Moderate depressive episode": (
        "moderate depressive episode",
        "6602009",
        "Moderate depressive disorder (disorder)",
        "disorder",
        False,
    ),
    "Dyspepsia": (
        "dyspepsia",
        "3696007",
        "Nonulcer dyspepsia (disorder)",
        "disorder",
        False,
    ),
    "dyspepsia": (
        "dyspepsia",
        "3696007",
        "Nonulcer dyspepsia (disorder)",
        "disorder",
        False,
    ),
    "Persistent dyspepsia": (
        "dyspepsia persistent",
        "3696007",
        "Nonulcer dyspepsia (disorder)",
        "disorder",
        False,
    ),
    "Chronic anxiety": (
        "chronic anxiety disorder",
        "191708009",
        "Chronic anxiety (finding)",
        "finding",
        False,
    ),
    "Anxiety state NOS": (
        "anxiety state",
        "197480006",
        "Anxiety disorder (disorder)",
        "disorder",
        False,
    ),
    "Antisocial personality traits": (
        "antisocial personality disorder",
        "26665006",
        "Antisocial personality disorder (disorder)",
        "disorder",
        False,
    ),
    "hyponatraemia": (
        "hyponatraemia",
        "89627008",
        "Hyponatremia (finding)",
        "finding",
        False,
    ),
    "metatarsalgia": (
        "metatarsalgia",
        "10085004",
        "Metatarsalgia (finding)",
        "finding",
        False,
    ),
    "neutropenia": (
        "neutropenia",
        "165517008",
        "Neutropenia (finding)",
        "finding",
        False,
    ),
    "Emphysema": (
        "pulmonary emphysema",
        "87433001",
        "Pulmonary emphysema (disorder)",
        "disorder",
        False,
    ),
    "emphysema": (
        "pulmonary emphysema",
        "87433001",
        "Pulmonary emphysema (disorder)",
        "disorder",
        False,
    ),
    "Grade 2 invasive ductal carcinoma": (
        "invasive ductal carcinoma breast",
        "408643008",
        "Infiltrating duct carcinoma of breast (disorder)",
        "disorder",
        False,
    ),
    "L invasive ductal carcinoma": (
        "invasive ductal carcinoma breast left",
        "408643008",
        "Infiltrating duct carcinoma of breast (disorder)",
        "disorder",
        False,
    ),
    "invasive ductal carcinoma": (
        "invasive ductal carcinoma breast",
        "408643008",
        "Infiltrating duct carcinoma of breast (disorder)",
        "disorder",
        False,
    ),
    "oesophageal adenocarcinoma at gastro-oesophageal junction": (
        "oesophageal adenocarcinoma",
        "310219009",
        "Adenocarcinoma of esophagus (disorder)",
        "disorder",
        False,
    ),
    "Biopsy shows iron pill gastritis": (
        "iron pill gastritis",
        "4556007",
        "Gastritis (disorder)",
        "disorder",
        False,
    ),
    "Emphysema": (
        "pulmonary emphysema",
        "87433001",
        "Pulmonary emphysema (disorder)",
        "disorder",
        False,
    ),
    # -----------------------------------------------------------------------
    # Mismatch corrections — entity label wrong, cross-validates clearly
    # -----------------------------------------------------------------------
    "vomiting": (
        "vomiting",
        "422587007",
        "Nausea and vomiting (finding)",
        "finding",
        False,
    ),
    "Vomiting": (
        "vomiting",
        "422587007",
        "Nausea and vomiting (finding)",
        "finding",
        False,
    ),
    "forceful vomiting": (
        "projectile vomiting",
        "28263003",
        "Projectile vomiting (finding)",
        "finding",
        False,
    ),
    "Bleeding per rectum": (
        "rectal bleeding",
        "12063002",
        "Rectal hemorrhage (disorder)",
        "disorder",
        False,
    ),
    "Non-healing pigmented skin lesion": (
        "non-healing pigmented lesion",
        "315259006",
        "Non-healing pigmented skin lesion (disorder)",
        "disorder",
        False,
    ),
    "hot flushes": (
        "menopausal hot flushes",
        "198436008",
        "Menopausal flushing (disorder)",
        "disorder",
        False,
    ),
    "Acute diarrhoea": (
        "acute diarrhoea",
        "409966000",
        "Acute diarrhea (disorder)",
        "disorder",
        False,
    ),
    "Blood in urine - haematuria": (
        "haematuria blood in urine",
        "34436003",
        "Blood in urine (finding)",
        "finding",
        False,
    ),
    "vaginal/ vulval itching": (
        "vulval pruritus",
        "67882000",
        "Pruritus of vulva (disorder)",
        "disorder",
        False,
    ),
    "work related stress": (
        "work related stress",
        "276074009",
        "Stress at work (finding)",
        "finding",
        False,
    ),
    "small lump visible when standing, easily reducible": (
        "reducible hernia",
        "414403008",
        "Inguinal hernia (disorder)",
        "disorder",
        False,
    ),
    "slight sunburn": (
        "sunburn",
        "403194002",
        "Solar erythema (disorder)",
        "disorder",
        False,
    ),
    "increased itchy sensation of skin": (
        "pruritus",
        "418290006",
        "Itching (finding)",
        "finding",
        False,
    ),
    "lesions on the wrist": (
        "skin lesions wrist",
        "402234004",
        "Skin lesion (disorder)",
        "disorder",
        False,
    ),
    "changes in hair": (
        "hair changes alopecia",
        "56317004",
        "Alopecia (disorder)",
        "disorder",
        False,
    ),
    "changes to skin / physical health": (
        "skin changes",
        "274672009",
        "Changes in skin texture (finding)",
        "finding",
        False,
    ),
    "resolving symptoms": (
        "symptoms resolving",
        "415684004",
        "Suspected (qualifier value)",
        None,
        True,
    ),  # ignore - context phrase
    "Low in mood": (
        "low mood depressed",
        "366979004",
        "Depressed mood (finding)",
        "finding",
        False,
    ),
    "Coughing phlegm": (
        "productive cough with sputum",
        "28743005",
        "Productive cough (finding)",
        "finding",
        False,
    ),
    "phlegm": ("sputum", "248595008", "Sputum finding (finding)", "finding", False),
    "white phlegm": (
        "white sputum",
        "248595008",
        "Sputum finding (finding)",
        "finding",
        False,
    ),
    "little phlegm": (
        "minimal sputum",
        "248595008",
        "Sputum finding (finding)",
        "finding",
        False,
    ),
    "coughed up phlegm with small flecks of red": (
        "haemoptysis",
        "66857006",
        "Hemoptysis (finding)",
        "finding",
        False,
    ),
    "occasional whitish phlegm": (
        "sputum occasional",
        "248595008",
        "Sputum finding (finding)",
        "finding",
        False,
    ),
    "lower back pain": (
        "low back pain",
        "279039007",
        "Low back pain (finding)",
        "finding",
        False,
    ),
    "Lower back pain": (
        "low back pain",
        "279039007",
        "Low back pain (finding)",
        "finding",
        False,
    ),
    "low back pain": (
        "low back pain",
        "279039007",
        "Low back pain (finding)",
        "finding",
        False,
    ),
    "Right lower back pain": (
        "right sided low back pain",
        "299001000000101",
        "Right-sided low back pain (finding)",
        "finding",
        False,
    ),
    "Left lower back pain": (
        "left sided low back pain",
        "298991000000106",
        "Left-sided low back pain (finding)",
        "finding",
        False,
    ),
    "Lower L back pain": (
        "low back pain",
        "279039007",
        "Low back pain (finding)",
        "finding",
        False,
    ),
    "ongoing lower back/ pelvic pain": (
        "low back pain pelvic pain",
        "279039007",
        "Low back pain (finding)",
        "finding",
        False,
    ),
    "worsening back pain": (
        "worsening back pain",
        "161891005",
        "Backache (finding)",
        "finding",
        False,
    ),
    "bad back": ("back pain", "161891005", "Backache (finding)", "finding", False),
    "cannot flex knee fully": (
        "reduced knee flexion",
        "299377003",
        "Knee flexion reduced (finding)",
        "finding",
        False,
    ),
    "breast lump": (
        "breast lump",
        "89164003",
        "Breast lump (finding)",
        "finding",
        False,
    ),
    "Breast lump": (
        "breast lump",
        "89164003",
        "Breast lump (finding)",
        "finding",
        False,
    ),
    "1 lump behind the nipple": (
        "breast lump retroareolar",
        "89164003",
        "Breast lump (finding)",
        "finding",
        False,
    ),
    "acid reflux": (
        "acid reflux",
        "698065002",
        "Acid reflux (finding)",
        "finding",
        False,
    ),
    "ankle swelling": (
        "swollen ankle",
        "267039000",
        "Swollen ankle (finding)",
        "finding",
        False,
    ),
    "does vape": (
        "vaping electronic cigarette",
        "35341000087101",
        "Uses electronic cigarette daily (finding)",
        "finding",
        False,
    ),
    "wears slippers in home": (
        "wears footwear adaptations",
        "228235002",
        "Slippers (physical object)",
        "physical_object",
        False,
    ),
    "pain going down to shoulder and arm to elbow": (
        "pain radiating to arm",
        "425677008",
        "Pain radiating to left arm (finding)",
        "finding",
        False,
    ),
    "IUCD identified and appears to be correctly sited within the endometrial cavity": (
        "IUCD correctly sited",
        "449038007",
        "Uses hormone releasing intrauterine device contraception (finding)",
        "finding",
        False,
    ),
    "the nipple": (
        "nipple",
        "24142002",
        "Nipple structure (body structure)",
        "body_structure",
        False,
    ),
    "moist mucous membranes": (
        "moist mucous membranes",
        "248153006",
        "Skin turgor normal (finding)",
        "finding",
        False,
    ),
    "fibroglandular tissue": (
        "fibroglandular breast tissue",
        "129717001",
        "Mammographic breast composition showing scattered fibroglandular densities (finding)",
        "finding",
        False,
    ),
    "abd pain": (
        "abdominal pain",
        "21522001",
        "Abdominal pain (finding)",
        "finding",
        False,
    ),
    "b/l subclavicular LN": (
        "bilateral subclavicular lymph nodes",
        "20253009",
        "Infraclavicular region structure (body structure)",
        "body_structure",
        False,
    ),
    "mid back": ("mid back pain", "57676002", "Joint pain (finding)", "finding", False),
    "ankle": ("ankle pain", "57676002", "Joint pain (finding)", "finding", False),
    "Ankle": ("ankle pain", "57676002", "Joint pain (finding)", "finding", False),
    "Shoulder": ("shoulder pain", "57676002", "Joint pain (finding)", "finding", False),
    "shoulder": ("shoulder pain", "57676002", "Joint pain (finding)", "finding", False),
    "Wrist": ("wrist pain", "299377003", "Wrist pain (finding)", "finding", False),
    "passed wind": (
        "passing flatus",
        "249504006",
        "Passing flatus (finding)",
        "finding",
        False,
    ),
    "did strain a lot": ("straining", None, None, None, True),  # ignore - too vague
    "pretty fit": ("physically fit", "102499006", "Fit (finding)", "finding", False),
    "active job": (
        "physically active occupation",
        "14679004",
        "Occupation (occupation)",
        "occupation",
        False,
    ),
    "want to lay down in dark room": (
        "photophobia lying down dark",
        None,
        None,
        None,
        True,
    ),  # ignore - contextual
    "language barrier": (
        "language barrier",
        "422693009",
        "Language barrier (observable entity)",
        "observable_entity",
        False,
    ),
    "Language barrier": (
        "language barrier",
        "422693009",
        "Language barrier (observable entity)",
        "observable_entity",
        False,
    ),
    "coughing": ("cough", "49727002", "Cough (finding)", "finding", False),
    "mood + affect": (
        "mood and affect",
        "1155968006",
        "Mood (observable entity)",
        "observable_entity",
        False,
    ),
    "alcohol habits": (
        "alcohol habits",
        "228282009",
        "Drinking habits (observable entity)",
        "observable_entity",
        False,
    ),
    "no regular exercise": (
        "no exercise",
        "228445002",
        "Gets no exercise (finding)",
        "finding",
        False,
    ),
    "regular menses": (
        "regular menstrual cycle",
        "248965005",
        "Regular periods (finding)",
        "finding",
        False,
    ),
    "irreg periods": (
        "irregular periods",
        "80182007",
        "Irregular periods (finding)",
        "finding",
        False,
    ),
    "Periods are painful": (
        "dysmenorrhoea painful periods",
        "266599000",
        "Dysmenorrhea (disorder)",
        "disorder",
        False,
    ),
    "Normal bowel movements": (
        "normal bowel habit",
        "55019002",
        "Normal bowel habits (finding)",
        "finding",
        False,
    ),
    "no confidence": (
        "lack of confidence",
        "225482007",
        "Lacks confidence (finding)",
        "finding",
        False,
    ),
    "no motivation": (
        "lack of motivation",
        "79351000119104",
        "Lack of motivation (finding)",
        "finding",
        False,
    ),
    "poor motivation": (
        "lack of motivation",
        "79351000119104",
        "Lack of motivation (finding)",
        "finding",
        False,
    ),
    "appetite good": (
        "good appetite",
        "300929008",
        "Appetite good (finding)",
        "finding",
        False,
    ),
    "appetite": (
        "appetite",
        "289163007",
        "Finding of appetite (finding)",
        "finding",
        False,
    ),
    "current weight": (
        "current body weight",
        "735395000",
        "Current body weight (observable entity)",
        "observable_entity",
        False,
    ),
    "swallowing issue": (
        "dysphagia swallowing difficulty",
        "40739000",
        "Dysphagia (finding)",
        "finding",
        False,
    ),
    "pain waking her": (
        "pain waking from sleep",
        "55442009",
        "Pain in limb (finding)",
        "finding",
        False,
    ),
    "urgency": (
        "urinary urgency or bowel urgency",
        "75088002",
        "Urgent desire to urinate (finding)",
        "finding",
        False,
    ),
    "Urinary incontinence": (
        "urinary incontinence",
        "165232002",
        "Urinary incontinence (finding)",
        "finding",
        False,
    ),
    "Urinary symptoms": (
        "lower urinary tract symptoms",
        "307541003",
        "Lower urinary tract symptoms (finding)",
        "finding",
        False,
    ),
    "Ex-Smoker": ("ex-smoker", "8517006", "Ex-smoker (finding)", "finding", False),
    "non smoker": ("non-smoker", "8392000", "Non-smoker (finding)", "finding", False),
    "Current Smoker": (
        "current smoker",
        "77176002",
        "Smoker (finding)",
        "finding",
        False,
    ),
    "Smoking History": (
        "history of smoking",
        "160603005",
        "Light cigarette smoker (finding)",
        "finding",
        False,
    ),
    "history of smoking": (
        "smoking history",
        "160603005",
        "Light cigarette smoker (finding)",
        "finding",
        False,
    ),
    "Refusal to give smoking status": (
        "declined to give smoking status",
        "1098881000000103",
        "Declined to give smoking status (situation)",
        "situation",
        False,
    ),
    "suicidal ideation": (
        "suicidal thoughts",
        "6471006",
        "Suicidal thoughts (finding)",
        "finding",
        False,
    ),
    "auditory hallucinations": (
        "auditory hallucinations",
        "45150006",
        "Auditory hallucinations (finding)",
        "finding",
        False,
    ),
    "psychotic symptoms": (
        "psychosis symptoms",
        "280428001",
        "Psychotic symptoms (finding)",
        "finding",
        False,
    ),
    "dyslexia": ("dyslexia", "59770006", "Dyslexia (finding)", "finding", False),
    "bullied": (
        "bullying victim",
        "248006009",
        "Victim of bullying (finding)",
        "finding",
        False,
    ),
    "bony lesion": (
        "bone lesion",
        "80917008",
        "Lesion of bone (disorder)",
        "disorder",
        False,
    ),
    "bowel cancer": (
        "malignant neoplasm of bowel suspected",
        "762999001",
        "Malignant neoplasm of intestine suspected (situation)",
        "situation",
        False,
    ),
    "cancer": (
        "malignant neoplastic disease",
        "363346000",
        "Malignant neoplastic disease (disorder)",
        "disorder",
        False,
    ),
    "Family history of cancer": (
        "family history of malignant neoplasm",
        "275937001",
        "Family history of malignant neoplasm (situation)",
        "situation",
        False,
    ),
    "family history of breast cancer": (
        "family history breast cancer",
        "429740004",
        "Family history of malignant neoplasm of breast (situation)",
        "situation",
        False,
    ),
    "Cardiovascular disease": (
        "family history cardiovascular disease",
        "266894000",
        "Family history: Cardiovascular disease (situation)",
        "situation",
        False,
    ),
    "Diabetes mellitus": (
        "diabetes mellitus family history",
        "160303001",
        "Family history of diabetes mellitus (situation)",
        "situation",
        False,
    ),
    "carcinoma of prostate": (
        "prostate carcinoma",
        "254900004",
        "Carcinoma of prostate (disorder)",
        "disorder",
        False,
    ),
    "prostate cancer": (
        "prostate cancer",
        "399068003",
        "Malignant neoplasm of prostate (disorder)",
        "disorder",
        False,
    ),
    "bowel ca": (
        "bowel cancer suspected",
        "762999001",
        "Malignant neoplasm of intestine suspected (situation)",
        "situation",
        False,
    ),
    "bowel related cancer": (
        "bowel cancer",
        "363508008",
        "Malignant neoplasm of intestine (disorder)",
        "disorder",
        False,
    ),
    "suspected haematology malignancy": (
        "haematological malignancy suspected",
        "315275009",
        "Hematological malignancy suspected (situation)",
        "situation",
        False,
    ),
    "NASH": (
        "non-alcoholic steatohepatitis",
        "442685003",
        "Metabolic dysfunction-associated steatohepatitis (disorder)",
        "disorder",
        False,
    ),
    "folate deficiency": (
        "folate deficiency",
        "190633005",
        "Folic acid deficiency (disorder)",
        "disorder",
        False,
    ),
    "inflammatory bowel disease": (
        "inflammatory bowel disease",
        "24526004",
        "Inflammatory bowel disease (disorder)",
        "disorder",
        False,
    ),
    "Suspected asthma": (
        "asthma suspected",
        "394967008",
        "Asthma suspected (situation)",
        "situation",
        False,
    ),
    "No Further Action": (
        "no further action",
        "397807004",
        "No further medical care needed (finding)",
        "finding",
        False,
    ),
    "Patient pregnant": (
        "pregnancy",
        "77386006",
        "Pregnancy (finding)",
        "finding",
        False,
    ),
    "Pregnant 28 wks": (
        "pregnancy 28 weeks",
        "77386006",
        "Pregnancy (finding)",
        "finding",
        False,
    ),
    "No evidence of malignancy": (
        "no evidence of malignancy",
        "110396000",
        "No evidence of malignant neoplasm (finding)",
        "finding",
        False,
    ),
    "no evidence of colorectal malignancy": (
        "no evidence of colorectal malignancy",
        "110396000",
        "No evidence of malignant neoplasm (finding)",
        "finding",
        False,
    ),
    "citalopram": (
        "citalopram",
        "372596005",
        "Citalopram (substance)",
        "substance",
        False,
    ),
    "colonoscopy": (
        "colonoscopy",
        "73761001",
        "Colonoscopy (procedure)",
        "procedure",
        False,
    ),
    "covid": (
        "COVID-19",
        "840539006",
        "Disease caused by SARS-CoV-2 (disorder)",
        "disorder",
        False,
    ),
    "radiotherapy": (
        "radiotherapy",
        "1287742003",
        "Radiotherapy (procedure)",
        "procedure",
        False,
    ),
    "thyroidectomy": (
        "thyroidectomy",
        "13619001",
        "Thyroidectomy (procedure)",
        "procedure",
        False,
    ),
    "endoscopy": (
        "endoscopy",
        "423827005",
        "Endoscopy (procedure)",
        "procedure",
        False,
    ),
    "x-ray": (
        "x-ray plain",
        "168537006",
        "Plain X-ray (procedure)",
        "procedure",
        False,
    ),
    "xray": ("x-ray", "168537006", "Plain X-ray (procedure)", "procedure", False),
    "dihydrocodeine": (
        "dihydrocodeine",
        "387322000",
        "Dihydrocodeine (substance)",
        "substance",
        False,
    ),
    "nausea": ("nausea", "422587007", "Nausea (finding)", "finding", False),
    "stress": ("stress", "73595000", "Stress (finding)", "finding", False),
    "pain": ("pain", "22253000", "Pain (finding)", "finding", False),
    "anxiety": (
        "anxiety",
        "197480006",
        "Anxiety disorder (disorder)",
        "disorder",
        False,
    ),
    "housebound": ("housebound", "160689007", "Housebound (finding)", "finding", False),
    "No longer housebound": (
        "no longer housebound",
        "760661000000106",
        "No longer housebound (finding)",
        "finding",
        False,
    ),
    "SOB which was worse on lying down": (
        "orthopnoea",
        "62744007",
        "Orthopnea (finding)",
        "finding",
        False,
    ),
    "progression": (
        "disease progression",
        "419835002",
        "Tumor progression (finding)",
        "finding",
        False,
    ),
    "Mammography normal": (
        "mammography normal",
        "168749009",
        "Mammography normal (finding)",
        "finding",
        False,
    ),
    "Faecal Immunochemical Test (FIT)": (
        "faecal immunochemical test",
        "1049361000000101",
        "Quantitative faecal immunochemical test (observable entity)",
        "observable_entity",
        False,
    ),
    "Faecal Immunochemical Test (FIT) is positive": (
        "faecal immunochemical test positive",
        "71711000112103",
        "Occult blood detected in feces by immunoassay (finding)",
        "finding",
        False,
    ),
    "Breast neoplasm screening normal": (
        "breast neoplasm screening normal",
        "171175005",
        "Breast neoplasm screening normal (finding)",
        "finding",
        False,
    ),
    "fast track suspected skin cancer clinic": (
        "fast track suspected skin cancer",
        "382711000000103",
        "Seen in fast track suspected skin cancer clinic (finding)",
        "finding",
        False,
    ),
    "Seen by nephrologist": (
        "seen by nephrologist",
        "305683000",
        "Seen by nephrologist (finding)",
        "finding",
        False,
    ),
    "Gastroscopy normal": (
        "gastroscopy normal",
        "165141001",
        "Gastroscopy normal (finding)",
        "finding",
        False,
    ),
    "Cervical smear screening administration": (
        "cervical smear screening",
        "714971000000104",
        "Cervical smear screening administration (record artifact)",
        "record_artifact",
        False,
    ),
    "Cervical cytology screening test": (
        "cervical cytology test",
        "996261000000103",
        "Cervical cytology screening test (observable entity)",
        "observable_entity",
        False,
    ),
    "chemotherapy completed": (
        "chemotherapy completed",
        "413943001",
        "Date chemotherapy completed (observable entity)",
        "observable_entity",
        False,
    ),
    "regular analgesia": (
        "regular analgesia",
        "182970005",
        "Pain relief (procedure)",
        "procedure",
        False,
    ),
    "transplant": (
        "organ transplant",
        "70536003",
        "Transplant of kidney (procedure)",
        "procedure",
        False,
    ),
    "pain relief": (
        "pain relief",
        "182970005",
        "Pain relief (procedure)",
        "procedure",
        False,
    ),
    "patient is not housebound": (
        "not housebound",
        "760661000000106",
        "No longer housebound (finding)",
        "finding",
        False,
    ),
    "exercises": (
        "exercises therapy",
        "226029000",
        "Exercises (regime/therapy)",
        "regime_therapy",
        False,
    ),
    "itching sensation down the throat": (
        "throat itch",
        "162406009",
        "Itch (finding)",
        "finding",
        False,
    ),
    "mental health has deteriorated": (
        "mental health deteriorating",
        "247812009",
        "Deterioration of mental state (finding)",
        "finding",
        False,
    ),
    "pt happy with plan": (
        "patient satisfied",
        "416940007",
        "Past history of procedure (situation)",
        None,
        True,
    ),  # ignore
    "no concerns re diet": ("no dietary concerns", None, None, None, True),  # ignore
    "Smoking history": (
        "history of smoking",
        "160603005",
        "Light cigarette smoker (finding)",
        "finding",
        False,
    ),
    "smoking history": (
        "history of smoking",
        "160603005",
        "Light cigarette smoker (finding)",
        "finding",
        False,
    ),
    "smoking cigarettes 4/day": (
        "light cigarette smoker",
        "160606002",
        "Very light cigarette smoker (finding)",
        "finding",
        False,
    ),
    "on a cruise": (
        "recent cruise travel",
        "473085002",
        "Recent cruise travel (event)",
        "event",
        False,
    ),
    "risk of endstage kidney disease": (
        "risk of end stage renal disease",
        "698463001",
        "At increased risk of chronic kidney disease (finding)",
        "finding",
        False,
    ),
    "Requested": (
        "requested",
        "385644000",
        "Requested (qualifier value)",
        "qualifier_value",
        False,
    ),
    "(Requested)": (
        "requested",
        "385644000",
        "Requested (qualifier value)",
        "qualifier_value",
        False,
    ),
    "unsuccessful": (
        "treatment unsuccessful",
        "385671000",
        "Unsuccessful (qualifier value)",
        "qualifier_value",
        False,
    ),
    "exclude fracture": (
        "exclude fracture",
        "125605004",
        "Fracture of bone (disorder)",
        "disorder",
        False,
    ),
    "diagnosis confirmed by biopsy": (
        "diagnosis confirmed biopsy",
        "59156000",
        "Confirmed by (contextual qualifier)",
        "qualifier_value",
        False,
    ),
    "Clarithromycin 500mg tablets": (
        "clarithromycin 500mg",
        "387487009",
        "Clarithromycin (substance)",
        "substance",
        False,
    ),
    "dietary iron": ("dietary iron", "3829006", "Iron (substance)", "substance", False),
    "normal saline": (
        "sodium chloride solution",
        "373757009",
        "Sodium chloride solution (substance)",
        "substance",
        False,
    ),
    "fibrate": (
        "fibrate lipid lowering",
        "768990001",
        "Lipid-lowering therapy (regime/therapy)",
        "regime_therapy",
        False,
    ),
    "AAA Screening": (
        "abdominal aortic aneurysm screening",
        "171401004",
        "Screening for abdominal aortic aneurysm (procedure)",
        "procedure",
        False,
    ),
    "dressing wound daily": (
        "wound dressing",
        "182531007",
        "Dressing of wound (procedure)",
        "procedure",
        False,
    ),
    "faecal calprotectin": (
        "faecal calprotectin",
        "1002571000000102",
        "Faecal calprotectin content (observable entity)",
        "observable_entity",
        False,
    ),
    "mild elevation of ALT": (
        "ALT raised mildly",
        "166717003",
        "Serum alkaline phosphatase raised (finding)",
        "finding",
        False,
    ),
    "calprotectin borderline raised": (
        "calprotectin raised",
        "1031581000000104",
        "Calprotectin level (observable entity)",
        "observable_entity",
        False,
    ),
    "calprotectin": (
        "calprotectin level",
        "1031581000000104",
        "Calprotectin level (observable entity)",
        "observable_entity",
        False,
    ),
    "lymphocytes": (
        "lymphocyte count",
        "1017571000000105",
        "Lymphocyte count (observable entity)",
        "observable_entity",
        False,
    ),
    "Lipid / Cholesterol": (
        "lipid cholesterol",
        "850981000000101",
        "Cholesterol level (observable entity)",
        "observable_entity",
        False,
    ),
    "Globulin levels": (
        "globulin level",
        "365758001",
        "Finding of electrolyte levels (finding)",
        "finding",
        False,
    ),
    "Sodium levels": (
        "sodium level",
        "1000671000000102",
        "Serum sodium level (observable entity)",
        "observable_entity",
        False,
    ),
    "Haematocrit - low 0.340": (
        "haematocrit low",
        "165414004",
        "Hematocrit below reference range (finding)",
        "finding",
        False,
    ),
    "Hba1c 7.7": (
        "HbA1c level",
        "43396009",
        "Hemoglobin A1c measurement (procedure)",
        "procedure",
        False,
    ),
    "International normalised ratio Normal": (
        "INR normal",
        "165582006",
        "International normalized ratio within reference range (finding)",
        "finding",
        False,
    ),
    "Smoking status": (
        "smoking status",
        "308512009",
        "Smoking monitoring status (finding)",
        "finding",
        False,
    ),
    "level of poor appetite": (
        "poor appetite",
        "64379006",
        "Decrease in appetite (finding)",
        "finding",
        False,
    ),
    "BMI: Body mass index 20-24 - normal": (
        "BMI normal",
        "412768003",
        "Body mass index 20-24 - normal (finding)",
        "finding",
        False,
    ),
    "BMI: Body mass index index 25-29 - overweight": (
        "BMI overweight",
        "162863004",
        "Body mass index 25-29 - overweight (finding)",
        "finding",
        False,
    ),
    "Body mass index 30+": (
        "BMI obese",
        "162864005",
        "Body mass index 30+ - obesity (finding)",
        "finding",
        False,
    ),
    "Body mass index 20-24": (
        "BMI normal",
        "412768003",
        "Body mass index 20-24 - normal (finding)",
        "finding",
        False,
    ),
    "Body mass index index 25-29": (
        "BMI overweight",
        "162863004",
        "Body mass index 25-29 - overweight (finding)",
        "finding",
        False,
    ),
    "Body mass index normal K/M2": (
        "BMI normal",
        "35425004",
        "Normal body mass index (finding)",
        "finding",
        False,
    ),
    "Mean cell haemoglobin level": (
        "mean corpuscular haemoglobin",
        "1022471000000107",
        "Mean corpuscular haemoglobin (observable entity)",
        "observable_entity",
        False,
    ),
    "Diabetes": (
        "diabetes mellitus suspected",
        "73211009",
        "Diabetes mellitus (disorder)",
        "disorder",
        False,
    ),
    "balloon would be in the urethra": (
        "balloon catheter urethra",
        None,
        None,
        None,
        True,
    ),  # contextual
    "symptoms have been resolved": (
        "resolved symptoms",
        "413322009",
        "Problem resolved (finding)",
        "finding",
        False,
    ),
    "current illness": (
        "current illness",
        "39104002",
        "Illness (finding)",
        "finding",
        False,
    ),
    "has made changes to diet and activity": (
        "lifestyle changes",
        "229070002",
        "Lifestyle advice (procedure)",
        "procedure",
        False,
    ),
    "Non-response, FOBT Non-Response": (
        "faecal occult blood non-response",
        None,
        None,
        "situation",
        False,
    ),
    "increase exercise level and confidence in class/ group setting": (
        "exercise class",
        "229095001",
        "Exercise class (regime/therapy)",
        "regime_therapy",
        False,
    ),
    "stroke clinic letter": (
        "stroke clinic referral",
        "412773009",
        "Referral to stroke clinic (procedure)",
        "procedure",
        False,
    ),
    "counselling appt": (
        "counselling appointment",
        "409063005",
        "Counseling (procedure)",
        "procedure",
        False,
    ),
    "referred herself for counselling": (
        "self-referral counselling",
        "409063005",
        "Counseling (procedure)",
        "procedure",
        False,
    ),
    "echo in august": (
        "echocardiogram",
        "40701008",
        "Echocardiography (procedure)",
        "procedure",
        False,
    ),
    "review": (
        "review",
        "182836005",
        "Review of medication (procedure)",
        "procedure",
        False,
    ),
    "Review": (
        "review appointment",
        "182836005",
        "Review of medication (procedure)",
        "procedure",
        False,
    ),
    "lifestyle modifications": (
        "lifestyle modification",
        "229070002",
        "Lifestyle advice (procedure)",
        "procedure",
        False,
    ),
    "Macmillan nurse support arranged": (
        "Macmillan nurse support",
        "224553003",
        "Macmillan nurse (occupation)",
        "occupation",
        False,
    ),
    "1st Trimester Downs Screening": (
        "first trimester Down syndrome screening",
        "315115008",
        "Downs screening test (procedure)",
        "procedure",
        False,
    ),
    "right salpingoopherectomy": (
        "right salpingo-oophorectomy",
        "43825003",
        "Right salpingo-oophorectomy (procedure)",
        "procedure",
        False,
    ),
    "NHS Diabetes Prevention Programme started": (
        "NHS Diabetes Prevention Programme started",
        "1025271000000103",
        "NHS Diabetes Prevention Programme started (situation)",
        "situation",
        False,
    ),
    "NHS Diabetes Prevention Programme invitation": (
        "NHS Diabetes Prevention Programme invitation",
        "1090701000000104",
        "NHS Diabetes Prevention Programme invitation (procedure)",
        "procedure",
        False,
    ),
    "New patient screening done": (
        "new patient screening done",
        "713019007",
        "New patient screening done (situation)",
        "situation",
        False,
    ),
    "Antenatal blood group screening done": (
        "antenatal blood group screening done",
        "169705004",
        "Antenatal blood group screening done (situation)",
        "situation",
        False,
    ),
    "Specimen sent for histology": (
        "specimen sent for histology",
        "144291000000105",
        "Placenta sent for histology (situation)",
        "situation",
        False,
    ),
    "microlax enema administered": (
        "enema administered",
        "266684008",
        "Simple enema administered (situation)",
        "situation",
        False,
    ),
    "Awaiting chemoradiotherapy": (
        "awaiting chemoradiotherapy",
        "703423002",
        "Combined chemotherapy and radiation therapy (procedure)",
        "procedure",
        False,
    ),
    "poor response to medications": (
        "poor response to treatment",
        "405786003",
        "Poor response to treatment (situation)",
        "situation",
        False,
    ),
    "referred on 2ww": (
        "fast track cancer referral",
        "199251000000107",
        "Fast track cancer referral (procedure)",
        "procedure",
        False,
    ),
    "primary hpv screening programme": (
        "HPV screening programme",
        "700152009",
        "Human papillomavirus screening (procedure)",
        "procedure",
        False,
    ),
    "Oncology referral made": (
        "oncology referral",
        "439980006",
        "Referral placed (situation)",
        "situation",
        False,
    ),
    "Make an appointment to see nurse": ("nursing appointment", None, None, None, True),
    "Advice about weight": (
        "weight management advice",
        "698471002",
        "Patient advised about weight management (situation)",
        "situation",
        False,
    ),
    "Referral for smoking cessation service offered": (
        "smoking cessation referral offered",
        "767641000000109",
        "Referral for smoking cessation service offered (finding)",
        "finding",
        False,
    ),
    "informed pt of x-ray results": (
        "informed patient of test results",
        "135866007",
        "Partially informed of test results (situation)",
        "situation",
        False,
    ),
    "Urgent suspected cancer pathway referral": (
        "urgent cancer referral",
        "199251000000107",
        "Fast track cancer referral (procedure)",
        "procedure",
        False,
    ),
    "NHS Health Check raise awareness about dementia": (
        "NHS health check dementia awareness",
        "870991000000101",
        "NHS Health Check raising awareness about dementia (procedure)",
        "procedure",
        False,
    ),
    "Referral to older age community mental health team": (
        "older adult mental health team referral",
        "199091000000105",
        "Referral to older age community mental health team (procedure)",
        "procedure",
        False,
    ),
    "LLR Integrated Community Specialist Palliative Care": (
        "community specialist palliative care",
        "395086005",
        "Community specialist palliative care (qualifier value)",
        "qualifier_value",
        False,
    ),
    "at endoscopy": (
        "endoscopy",
        "423827005",
        "Endoscopy (procedure)",
        "procedure",
        False,
    ),
    "chest x-ray": (
        "chest x-ray",
        "399208008",
        "Plain X-ray of chest (procedure)",
        "procedure",
        False,
    ),
    "Xray c spine": (
        "cervical spine x-ray",
        "1286742007",
        "Plain X-ray of cervical spine (procedure)",
        "procedure",
        False,
    ),
    "chest xray requested": (
        "chest x-ray requested",
        "1295419007",
        "Plain X-ray of chest requested (situation)",
        "situation",
        False,
    ),
    "Quantitative faecal immunochemical test result received": (
        "faecal immunochemical test result",
        "1049361000000101",
        "Quantitative faecal immunochemical test (observable entity)",
        "observable_entity",
        False,
    ),
    "repeat U&E": (
        "urea and electrolytes",
        "252167001",
        "Measurement of urea and electrolytes (procedure)",
        "procedure",
        False,
    ),
    "xray ok": (
        "x-ray normal",
        "2071000000108",
        "X-ray report received (finding)",
        "finding",
        False,
    ),
    "Normal FBC": (
        "full blood count normal",
        "165406005",
        "Full blood count within reference range (finding)",
        "finding",
        False,
    ),
    "Renal ultrasound": (
        "renal ultrasound",
        "709640007",
        "Doppler ultrasonography of renal vein (procedure)",
        "procedure",
        False,
    ),
    "Ultrasound referral sent": (
        "ultrasound referral",
        "183831007",
        "Referral for diagnostic ultrasonography (procedure)",
        "procedure",
        False,
    ),
    "if any concerns re Lymph nodes/ swelling / signs of infection needs GP review": (
        "lymphadenopathy concern",
        "30746006",
        "Lymphadenopathy (disorder)",
        "disorder",
        False,
    ),
    "referred via IAPT": (
        "IAPT referral",
        "380201000000109",
        "Referral to IAPT programme (procedure)",
        "procedure",
        False,
    ),
    "Colonoscopy performed today under sedation": (
        "colonoscopy under sedation",
        "73761001",
        "Colonoscopy (procedure)",
        "procedure",
        False,
    ),
    "sentinal node Bx": (
        "sentinel node biopsy",
        "396487001",
        "Sentinel lymph node biopsy (procedure)",
        "procedure",
        False,
    ),
    "excision mapping biopsy": (
        "excision biopsy",
        "65801008",
        "Excision (procedure)",
        "procedure",
        False,
    ),
    "Excision mapping biopsy": (
        "excision biopsy",
        "65801008",
        "Excision (procedure)",
        "procedure",
        False,
    ),
    "3 cycles of chemo": (
        "chemotherapy cycles",
        "367336001",
        "Chemotherapy (procedure)",
        "procedure",
        False,
    ),
    "4 cycles of chemotherapy": (
        "chemotherapy cycles",
        "367336001",
        "Chemotherapy (procedure)",
        "procedure",
        False,
    ),
    "Radiotherapy 40Gy in 15 fractions": (
        "radiotherapy",
        "1287742003",
        "Radiotherapy (procedure)",
        "procedure",
        False,
    ),
    "drt screening": (
        "screening",
        "20135006",
        "Screening procedure (procedure)",
        "procedure",
        False,
    ),
    "screening FOBT": (
        "faecal occult blood screening",
        "315058008",
        "Fecal occult blood test (procedure)",
        "procedure",
        False,
    ),
    "Anastomosis formed": (
        "anastomosis",
        "41796003",
        "Anastomosis (morphologic abnormality)",
        "morphologic_abnormality",
        False,
    ),
    "increasing fluids": ("increasing fluid intake", None, None, "procedure", False),
    "supervision with Ian Overton": (
        "clinical supervision",
        "225313009",
        "Supervision (regime/therapy)",
        "regime_therapy",
        False,
    ),
    "3w hx of mix of symptoms": (
        "multiple symptoms",
        None,
        None,
        None,
        True,
    ),  # too vague
    "vapes": (
        "electronic cigarette use",
        "35341000087101",
        "Uses electronic cigarette daily (finding)",
        "finding",
        False,
    ),
    "fibrate": (
        "fibrate lipid lowering",
        "768990001",
        "Lipid-lowering therapy (regime/therapy)",
        "regime_therapy",
        False,
    ),
    "Ekomove": (
        "pressure ulcer prevention mattress",
        None,
        None,
        "physical_object",
        False,
    ),
    "oramorph": (
        "oral morphine",
        "373529000",
        "Morphine (substance)",
        "substance",
        False,
    ),
    "lemsip": ("Lemsip cold remedy", None, None, "medicinal_product", False),
    # -----------------------------------------------------------------------
    # Noise / ignore rules
    # -----------------------------------------------------------------------
    "eating a pub meal (mixed grill) last wednesday,": (None, None, None, None, True),
    "eating a pub meal": (None, None, None, None, True),
    "surpress sxs": (None, None, None, None, True),
    "dropped and smashed a few plates": (None, None, None, None, True),
    "given up being vegan, now eating fish and has more energy": (
        None,
        None,
        None,
        None,
        True,
    ),
    "brain was relaxed": (None, None, None, None, True),
    "weak decafinated coffee": (None, None, None, None, True),
    "recently fall i nthe street": (
        "recent fall",
        "161898004",
        "Falls (finding)",
        "finding",
        False,
    ),
    "admits eats sweet treats": (
        "high sugar diet",
        None,
        None,
        None,
        True,
    ),  # too contextual
    "bowels opening as normal once a day": (
        "normal bowel habit",
        "55019002",
        "Normal bowel habits (finding)",
        "finding",
        False,
    ),
}

# ---------------------------------------------------------------------------
# Terminology API
# ---------------------------------------------------------------------------


def search(
    client: httpx.Client, q: str, semantic_tag: str | None = None, limit: int = 3
) -> list[dict]:
    """Search the Terminology API. Returns top N results."""
    try:
        params: dict = {"q": q, "limit": limit}
        if semantic_tag:
            params["semantic_tag"] = semantic_tag
        resp = client.get(f"{TERM_API}/terminology/search", params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
        return []
    except Exception:
        return []


def fmt(r: dict) -> str:
    if not r:
        return ""
    cid = r.get("snomed_concept_id") or "?"
    term = r.get("term") or "?"
    tag = r.get("semantic_tag") or ""
    score = r.get("score")
    s = f"{cid} {term}"
    if tag:
        s += f" ({tag})"
    if score is not None:
        s += f" score={score:.2f}"
    return s


def extract_span_context(
    entity_text: str,
    sample_text: str | None,
    sample_entities_raw: str | list | None,
    window: int | None = 55,
) -> str:
    """Return a short encounter snippet with the entity highlighted in **bold**.

    If window is None, returns the FULL text with highlighting.
    """
    if not sample_text:
        return ""

    start: int | None = None
    end: int | None = None

    # --- entities_json lookup ---
    if sample_entities_raw:
        try:
            entities = (
                json.loads(sample_entities_raw)
                if isinstance(sample_entities_raw, str)
                else sample_entities_raw
            )
            et_lower = entity_text.strip().lower()
            for ent in (entities if isinstance(entities, list) else []):
                if (ent.get("text") or "").strip().lower() == et_lower:
                    start = ent.get("start")
                    end = ent.get("end")
                    break
        except Exception:
            pass

    # --- plain-text fallback ---
    if start is None:
        idx = sample_text.lower().find(entity_text.strip().lower())
        if idx >= 0:
            start = idx
            end = idx + len(entity_text)

    # If still not found, return full text or truncated start
    if start is None:
        if window is None:
            return sample_text
        return sample_text[: window * 2]

    end = end or (start + len(entity_text))

    if window is None:
        # Highlight in full text
        return (
            sample_text[:start]
            + "**"
            + sample_text[start:end]
            + "**"
            + sample_text[end:]
        )

    ctx_start = max(0, start - window)
    ctx_end = min(len(sample_text), end + window)
    snippet = sample_text[ctx_start:ctx_end]
    rel_s = start - ctx_start
    rel_e = end - ctx_start
    marked = snippet[:rel_s] + "**" + snippet[rel_s:rel_e] + "**" + snippet[rel_e:]
    prefix = "…" if ctx_start > 0 else ""
    suffix = "…" if ctx_end < len(sample_text) else ""
    return prefix + marked.strip() + suffix


# ---------------------------------------------------------------------------
# Graph-based disambiguation — deterministic via SNOMED ontology relationships
# ---------------------------------------------------------------------------
# Uses the /concepts/{id}/related endpoint (materialised by the phase-3 loader:
# HAS_COMPONENT 246093002, INTERPRETS 363713009, HAS_ASSOCIATED_FINDING 246090004)
# to cross-validate candidates across the procedure / observable_entity / finding
# triangle without any LLM calls.

# Text-signal patterns that hint at the most likely semantic tag.
_MEASUREMENT_UNITS_RE = re.compile(
    r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*"
    r"(?:mmol|umol|nmol|pmol|mg|ug|ng|pg|g/l|g/dl|fl|iu|ml|l|%|mmhg|kpa|bpm|10\^)",
    re.IGNORECASE,
)
_INTERPRETATION_WORDS = frozenset(
    {
        "high",
        "low",
        "raised",
        "elevated",
        "reduced",
        "low",
        "normal",
        "abnormal",
        "borderline",
        "above",
        "below",
        "outside",
        "within",
    }
)
_PROCEDURE_SUBSTRINGS = frozenset(
    {
        "determination",
        "assay",
        "analysis",
        "screening",
        "request",
        "measurement",
        "ordered",
        "performed",
    }
)


def _text_signal_tag(entity_text: str) -> str | None:
    """Derive the most likely semantic tag purely from the entity text.

    Returns "finding", "observable_entity", "procedure", or None.
    """
    lower = entity_text.lower()
    words = set(re.findall(r"[a-z]+", lower))

    # Interpretation words → finding (e.g. "MCH low", "Outside reference range")
    has_interp_word = bool(words & _INTERPRETATION_WORDS)
    has_interp_phrase = bool(
        re.search(r"(outside|above|below|within)\s+reference\s+range", lower)
    )
    # A measurement value + unit → observable_entity (e.g. "MCH 22.5 pg")
    has_measurement = bool(_MEASUREMENT_UNITS_RE.search(lower))

    if (has_interp_word or has_interp_phrase) and not has_measurement:
        return "finding"
    if has_measurement:
        return "observable_entity"
    if any(sub in lower for sub in _PROCEDURE_SUBSTRINGS):
        return "procedure"
    return None


def _related_ids(data: dict) -> set[str]:
    """Collect all related concept IDs from a /related API response."""
    ids: set[str] = set()
    for key in (
        "interpreted_by_findings",
        "component_of_procedures",
        "interprets_observables",
        "has_components",
        "associated_findings",
    ):
        for item in data.get(key, []):
            if item.get("id"):
                ids.add(str(item["id"]))
    return ids


def graph_disambiguate(
    entity_text: str,
    entity_label: str,
    http_client: httpx.Client,
    span_context: str = "",
) -> tuple[str, str, str, str, str]:
    """Deterministic SNOMED-graph disambiguation for the procedure/observable/finding triangle.

    Returns ``(action, snomed_id, snomed_term, semantic_tag, reason)``.
    ``action`` is one of: ``GRAPH_PICK``, ``GRAPH_UNCERTAIN``.

    Algorithm:
    1. Derive a text-signal tag from BOTH the entity text and the full span context
       (interpretation → finding, measurement → observable, procedure keywords → procedure).
       The span context often contains the result value, unit, and interpretation suffix
       that give a much clearer signal than the short entity text alone.
    2. Search all three ambiguous tags and collect top candidates.
       If the span context differs substantially from the entity text, also search the
       span context to cast a wider net.
    3. For each tag's top concept call ``/concepts/{id}/related`` to fetch the
       SNOMED ontology family (INTERPRETS / HAS_COMPONENT edges).
    4. If the preferred concept's family contains other tag candidates → confirmed.
    5. Fall back to text-signal match without graph confirmation if no family found.
    """
    # Derive text signals from entity text AND span context — span wins if both fire.
    entity_signal = _text_signal_tag(entity_text)
    # Strip markdown bold markers from span context before analysis
    span_clean = re.sub(r"\*\*", "", span_context).strip()
    span_signal = _text_signal_tag(span_clean) if span_clean else None

    # Prefer the span signal (richer text) if it is more specific than the entity signal
    text_signal = span_signal or entity_signal

    # Step 2: multi-tag search.
    # Use the entity text as primary search term. If the entity text is very short
    # (≤ 15 chars) also search with the span context text to cast a wider net
    # (e.g. span "FIT negative <4" gives richer signal than entity "FIT neg").
    search_terms: list[str] = [entity_text]
    if (
        span_clean
        and len(entity_text) <= 15
        and span_clean.lower() != entity_text.lower()
    ):
        # Extract the portion of the span that doesn't overlap with entity_text
        # (often adds units, values, interpretation words)
        search_terms.append(span_clean[:120])  # cap at 120 chars for API safety

    candidates_by_tag: dict[str, list[dict]] = {}
    for tag in ("observable_entity", "procedure", "finding"):
        res = search(http_client, search_terms[0], semantic_tag=tag, limit=3)
        if not res and len(search_terms) > 1:
            res = search(http_client, search_terms[1], semantic_tag=tag, limit=3)
        if res:
            candidates_by_tag[tag] = res
        time.sleep(0.03)

    if not candidates_by_tag:
        return "GRAPH_UNCERTAIN", "", "", "", "no candidates found across all tags"

    # Step 3: fetch /related for each tag's top concept
    related_by_id: dict[str, dict] = {}
    for tag, cands in candidates_by_tag.items():
        top_id = (cands[0].get("snomed_concept_id") or "").strip()
        if not top_id or top_id in related_by_id:
            continue
        try:
            resp = http_client.get(
                f"{TERM_API}/terminology/concepts/{top_id}/related", timeout=10
            )
            if resp.status_code == 200:
                related_by_id[top_id] = resp.json()
        except Exception:
            pass
        time.sleep(0.02)

    all_candidate_ids: set[str] = {
        str(c.get("snomed_concept_id", ""))
        for cands in candidates_by_tag.values()
        for c in cands
        if c.get("snomed_concept_id")
    }

    # Step 4: attempt to pick a graph-confirmed concept
    # Priority order: text_signal tag → entity_label → any tag with a family hit
    priority_tags = []
    if text_signal:
        priority_tags.append(text_signal)
    if entity_label and entity_label not in priority_tags:
        priority_tags.append(entity_label)
    for tag in ("observable_entity", "procedure", "finding"):
        if tag not in priority_tags:
            priority_tags.append(tag)

    for pick_tag in priority_tags:
        cands = candidates_by_tag.get(pick_tag, [])
        if not cands:
            continue
        top = cands[0]
        top_id = (top.get("snomed_concept_id") or "").strip()
        top_term = top.get("term") or ""
        top_score = top.get("score") or 0.0
        if not top_id:
            continue

        rel_data = related_by_id.get(top_id, {})
        family_ids = _related_ids(rel_data)
        overlapping = (all_candidate_ids - {top_id}) & family_ids

        if overlapping:
            other_str = ", ".join(sorted(overlapping)[:3])
            reason = (
                f"Graph confirmed: {pick_tag} {top_id} has family members "
                f"{other_str} (score={top_score:.2f})"
            )
            if text_signal and pick_tag == text_signal:
                reason = f"[text_signal={text_signal}] " + reason
            return "GRAPH_PICK", top_id, top_term, pick_tag, reason

    # Step 5: No graph confirmation — use text signal or entity label match
    for pick_tag in [text_signal, entity_label]:
        if not pick_tag:
            continue
        cands = candidates_by_tag.get(pick_tag, [])
        if not cands:
            continue
        top = cands[0]
        top_id = (top.get("snomed_concept_id") or "").strip()
        top_term = top.get("term") or ""
        top_score = top.get("score") or 0.0
        if top_id and top_score >= SCORE_THRESHOLD:
            signal_desc = (
                f"text_signal={text_signal}"
                if text_signal == pick_tag
                else f"entity_label={pick_tag}"
            )
            reason = f"[{signal_desc}, no graph confirmation] {pick_tag} {top_id} (score={top_score:.2f})"
            return "GRAPH_PICK", top_id, top_term, pick_tag, reason

    return (
        "GRAPH_UNCERTAIN",
        "",
        "",
        "",
        "no graph-confirmed or signal-matched candidate found",
    )


# ---------------------------------------------------------------------------
# Recommendation logic
# ---------------------------------------------------------------------------


def recommend(
    entity_text: str,
    entity_label: str,
    raw_results: list[dict],
    filtered_results: list[dict],
    smart_results: list[dict],
    hint_snomed: str | None,
    hint_fsn: str | None,
    hint_label: str | None,
    ignore: bool,
) -> tuple[str, str, str]:
    """Returns (action, recommended_id, recommended_term)."""
    if ignore:
        return "IGNORE", "", ""

    def top_tag_matches(results, label):
        if not results:
            return False
        top = results[0]
        return (top.get("semantic_tag") or "").lower().replace(
            " ", "_"
        ) == label.lower().replace(" ", "_")

    def top_score(results):
        if not results:
            return 0.0
        return results[0].get("score") or 0.0

    def top_id_term(results):
        if not results:
            return "", ""
        r = results[0]
        return r.get("snomed_concept_id") or "", r.get("term") or ""

    # If smart search returned a result that matches our hint concept ID exactly
    if hint_snomed and smart_results:
        top = smart_results[0]
        if top.get("snomed_concept_id") == hint_snomed:
            cid, term = top_id_term(smart_results)
            return "ACCEPT_SMART", cid, term
        # Smart result has good score and matches the hint label tag
        if (
            hint_label
            and top_tag_matches(smart_results, hint_label)
            and top_score(smart_results) >= SCORE_THRESHOLD
        ):
            cid, term = top_id_term(smart_results)
            return "ACCEPT_SMART", cid, term

    # If filtered search returned a good result matching the entity label
    if (
        filtered_results
        and top_tag_matches(filtered_results, entity_label)
        and top_score(filtered_results) >= SCORE_THRESHOLD
    ):
        cid, term = top_id_term(filtered_results)
        return "ACCEPT_FILTERED", cid, term

    # If raw top-1 tag matches entity label and score is decent
    if (
        raw_results
        and top_tag_matches(raw_results, entity_label)
        and top_score(raw_results) >= SCORE_THRESHOLD
    ):
        cid, term = top_id_term(raw_results)
        return "ACCEPT_RAW", cid, term

    # We have a firm hint concept ID — use it with hint_fsn (not the wrong search top-1)
    if hint_snomed:
        return "ACCEPT_SMART", hint_snomed, (hint_fsn or "")

    return "MANUAL_REVIEW", "", ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def categorise(row: dict) -> str:
    if row["snomed_concept_id"] is None and row["suggested_label"] is None:
        return "Uncoded"
    if row["snomed_concept_id"] is None and row["suggested_label"] is not None:
        return "Uncoded+TagHint"
    if row["suggested_label"] and row["suggested_label"] != row["entity_label"]:
        return f"Mismatch: {row['entity_label']}→{row['suggested_label']}"
    return "Low-confidence"


def _needs_graph_disambig(
    action: str,
    entity_label: str,
    rec_tag: str,
    hint_snomed: str | None,
) -> bool:
    """Return True if this item should go through graph disambiguation.

    Only triggers for the clinically meaningful triangle:
        observable_entity ↔ procedure ↔ finding

    Mismatches to other tags (disorder, substance, situation, …) are handled
    correctly by the KNOWLEDGE dict and do not need graph arbitration.

    IMPORTANT: If the KNOWLEDGE dict already provided a firm concept ID
    (hint_snomed is set), we trust it and skip graph disambiguation entirely —
    the clinical knowledge dict is authoritative and the graph pass would risk
    overriding a known-correct answer with a spurious search result.
    """
    # Clinical knowledge dict is authoritative — never override it
    if hint_snomed:
        return False
    if entity_label not in LAB_AMBIGUOUS_TAGS:
        return False
    # Cannot resolve at all → always try graph disambiguation
    if action == "MANUAL_REVIEW":
        return True
    # Tag mismatch within the ambiguous triangle only
    # (e.g. entity_label=observable_entity but rec_tag=procedure)
    rec_normalised = (rec_tag or "").lower().replace(" ", "_")
    entity_normalised = entity_label.lower().replace(" ", "_")
    if rec_normalised != entity_normalised and rec_normalised in LAB_AMBIGUOUS_TAGS:
        return True
    return False


def _rec_tag_from_results(
    action: str, raw: list, filtered: list, smart: list, hint_label: str | None
) -> str:
    """Best guess at the semantic tag of the current recommendation."""
    if action == "ACCEPT_SMART" and hint_label:
        return hint_label
    if action == "ACCEPT_FILTERED" and filtered:
        return (filtered[0].get("semantic_tag") or "").lower().replace(" ", "_")
    if action in ("ACCEPT_RAW", "MANUAL_REVIEW") and raw:
        return (raw[0].get("semantic_tag") or "").lower().replace(" ", "_")
    return ""


def main():
    driver = get_driver()
    print("Connected to Neo4j, fetching pending items...", file=sys.stderr)
    with driver.session() as session:
        rows = list(session.run(GET_PENDING))
    driver.close()
    print(f"Found {len(rows)} pending entity groups", file=sys.stderr)

    http_client = httpx.Client()

    records = []
    graph_count = 0
    for idx, row in enumerate(rows):
        text = row["entity_text"]
        label = row["entity_label"] or ""
        assertion = row["assertion"] or "present"
        n = row["occurrences"]
        tier = row["tier"]
        category = categorise(dict(row))
        sample_text = row.get("sample_text") or ""
        sample_entities = row.get("sample_entities")

        if idx % 50 == 0:
            print(f"  Processing {idx}/{len(rows)}...", file=sys.stderr)

        # Lookup in knowledge dict
        kv = KNOWLEDGE.get(text) or KNOWLEDGE.get(text.strip())
        smart_term, hint_snomed, hint_fsn, hint_label, ignore = (
            kv if kv else (None, None, None, None, False)
        )

        # Pass 1: raw search
        raw = search(http_client, text, limit=3)
        time.sleep(0.03)

        # Pass 2: label-filtered search
        filtered = []
        if label:
            filtered = search(http_client, text, semantic_tag=label, limit=3)
            time.sleep(0.03)

        # Pass 3: smart search
        smart = []
        if smart_term:
            smart = search(http_client, smart_term, limit=3)
            time.sleep(0.03)

        # Passes 1-3 recommendation
        action, rec_id, rec_term = recommend(
            text, label, raw, filtered, smart, hint_snomed, hint_fsn, hint_label, ignore
        )

        # Compute span context FIRST — it feeds into graph disambiguation
        # Use full encounter text (window=None) to ensure we catch all context
        span_ctx = extract_span_context(text, sample_text, sample_entities, window=None)

        # ----------------------------------------------------------------
        # Pass 4: deterministic graph disambiguation
        # Only for observable_entity/procedure/finding where there is
        # tag ambiguity or we could not resolve the item.
        # Uses /concepts/{id}/related (INTERPRETS, HAS_COMPONENT edges).
        # Skipped when KNOWLEDGE dict already provides a firm hint_snomed.
        # ----------------------------------------------------------------
        graph_reason = ""
        multitag_summary = ""

        rec_tag = _rec_tag_from_results(action, raw, filtered, smart, hint_label)

        if not ignore and _needs_graph_disambig(action, label, rec_tag, hint_snomed):
            graph_action, graph_id, graph_term, graph_tag, graph_reason = (
                graph_disambiguate(text, label, http_client, span_context=span_ctx)
            )
            graph_count += 1
            if graph_action == "GRAPH_PICK" and graph_id:
                action = graph_action
                rec_id = graph_id
                rec_term = graph_term
            multitag_summary = graph_reason

        records.append(
            {
                "entity_text": text,
                "label": label,
                "assertion": assertion,
                "n": n,
                "tier": tier,
                "category": category,
                "span_context": span_ctx,
                "smart_term": smart_term or "",
                "raw_top1": fmt(raw[0]) if raw else "",
                "filtered_top1": fmt(filtered[0]) if filtered else "",
                "smart_top1": fmt(smart[0]) if smart else "",
                "graph_reason": graph_reason,
                "multitag": multitag_summary,
                "action": action,
                "rec_id": rec_id,
                "rec_term": rec_term,
                "hint_snomed": hint_snomed or "",
                "hint_fsn": hint_fsn or "",
            }
        )

    http_client.close()
    print(f"Graph disambiguation ran for {graph_count} items", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Write output markdown
    # -----------------------------------------------------------------------
    out = ROOT / "scripts" / "hitl_smart_lookup.md"

    from collections import Counter

    action_counts = Counter(r["action"] for r in records)

    def _esc(s: str) -> str:
        if not s:
            return "-"
        # Escape pipe for table
        val = s.replace("|", "\\|").replace("\n", "<br>")
        # If very long, wrap in details to keep table readable
        if len(val) > 400:
            summary = val[:100] + "..."
            return f"<details><summary>{summary}</summary>{val}</details>"
        return val

    with open(out, "w", encoding="utf-8") as f:
        f.write("# Smart HITL Terminology Lookup\n\n")
        f.write(f"**Total unique entity texts: {len(records)}**  \n")
        f.write(f"**Graph disambiguation ran for: {graph_count} items**  \n")
        f.write(
            f"**Action summary:** "
            + " | ".join(f"{k}={v}" for k, v in sorted(action_counts.items()))
            + "\n\n"
        )
        f.write(
            "> **Actions:** ACCEPT_SMART/FILTERED/RAW = auto-resolved; "
            "GRAPH_PICK = deterministic SNOMED graph traversal resolved the concept; "
            "IGNORE = non-clinical noise; "
            "MANUAL_REVIEW = needs human review\n\n"
        )

        by_action: dict[str, list] = {}
        for r in records:
            by_action.setdefault(r["action"], []).append(r)

        action_order = [
            "GRAPH_PICK",
            "ACCEPT_SMART",
            "ACCEPT_FILTERED",
            "ACCEPT_RAW",
            "IGNORE",
            "MANUAL_REVIEW",
        ]

        for action in action_order:
            items = by_action.get(action, [])
            if not items:
                continue
            total_reviews = sum(i["n"] for i in items)
            f.write(f"\n## {action} ({len(items)} texts, {total_reviews} reviews)\n\n")

            is_graph = action == "GRAPH_PICK"

            if is_graph:
                f.write(
                    "| # | Entity Text | Label | Assertion | Count | Full Context | Graph Reason | Rec SNOMED | Rec Term |\n"
                )
                f.write(
                    "|---|-------------|-------|-----------|-------|--------------|--------------|------------|----------|\n"
                )
                for i, item in enumerate(items, 1):
                    f.write(
                        f"| {i} "
                        f"| {_esc(item['entity_text'])} "
                        f"| {item['label']} "
                        f"| {item['assertion']} "
                        f"| {item['n']} "
                        f"| {_esc(item['span_context'])} "
                        f"| {_esc(item['graph_reason'])} "
                        f"| {item['rec_id']} "
                        f"| {_esc(item['rec_term'])} "
                        f"|\n"
                    )
            else:
                f.write(
                    "| # | Entity Text | Label | Assertion | Count | Full Context | Smart Term | Raw Top-1 | Filtered Top-1 | Smart Top-1 | Rec SNOMED | Rec Term |\n"
                )
                f.write(
                    "|---|-------------|-------|-----------|-------|--------------|------------|-----------|----------------|-------------|------------|----------|\n"
                )
                for i, item in enumerate(items, 1):
                    f.write(
                        f"| {i} "
                        f"| {_esc(item['entity_text'])} "
                        f"| {item['label']} "
                        f"| {item['assertion']} "
                        f"| {item['n']} "
                        f"| {_esc(item['span_context'])} "
                        f"| {_esc(item['smart_term'])} "
                        f"| {_esc(item['raw_top1'])} "
                        f"| {_esc(item['filtered_top1'])} "
                        f"| {_esc(item['smart_top1'])} "
                        f"| {item['rec_id']} "
                        f"| {_esc(item['rec_term'])} "
                        f"|\n"
                    )

    print(f"\nWritten to {out}", file=sys.stderr)
    print(f"Actions: {dict(sorted(action_counts.items()))}", file=sys.stderr)


if __name__ == "__main__":
    main()
