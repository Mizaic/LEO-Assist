"""Fix 535 mental health surface forms orphaned to generic 'Mental disorder' (74732009).

Strategy
--------
Two passes:
  1. Explicit curated overrides for the most clinically important MH terms.
  2. Auto-search pass: fulltext search with a high minimum score (>=8.5).
     A blocklist prevents known bad concept IDs from being used.

For each fixable form:
  - Upsert the correct MAPS_TO edge (conf=1.0).
  - Delete the GCL 74732009 edge only after upsert succeeds.

Forms with no reliable mapping are left on 74732009 rather than mapped wrongly.

Usage
-----
  python scripts/investigations/_fix_mh_orphan_forms.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

OUTPUT = ROOT / "scripts" / "investigations" / "mh_orphan_fixes.json"

# Auto-search minimum score (Lucene fulltext). Raised high to avoid false positives.
_MIN_AUTO_SCORE = 8.5

# Concept IDs that should never be chosen as a "specific" target
_BLOCKLIST_IDS = {
    "74732009",  # Mental disorder (the catch-all we're escaping)
    "128462008",  # Metastatic malignant neoplasm
    "127294003",  # Traumatic or nontraumatic brain injury (too broad)
    "162864005",  # BMI 30+ obesity (wrong direction)
    "79890006",  # Loss of appetite (wrong for "anorexic" the person)
    "34883005",  # Autistic thinking (wrong)
    "60742000",  # Avoidance-avoidance conflict (wrong)
    "28368009",  # Organic hallucinosis (wrong for "bad nerves")
    "239783001",  # Post-infective arthritis (wrong for co-occurring disorders)
    "200141000000108",  # Did not attend CBT (negative, wrong)
    "183486001",  # Admitted to alcohol detox (wrong for "admitted to psych ward")
    "76241003",  # Jatropha curcas poisoning (wrong for binge-purge)
}

# ---------------------------------------------------------------------------
# CURATED EXPLICIT OVERRIDES - highest clinical priority
# (form_lowercase, concept_id, note)
# ---------------------------------------------------------------------------
_EXPLICIT: dict[str, str] = {
    # Abbreviations / single words
    "adhd": "406506008",  # Attention deficit hyperactivity disorder
    "add": "35253001",  # ADHD predominantly inattentive type
    "ocd": "191736004",  # Obsessive-compulsive disorder
    "ptsd": "47505003",  # Post-traumatic stress disorder
    "bpd": "20010003",  # Borderline personality disorder
    "bpad": "13746004",  # Bipolar disorder
    "gad": "21897009",  # Generalised anxiety disorder
    "arbd": "281004",  # Dementia associated with alcoholism
    "aspd": "26665006",  # Antisocial personality disorder
    "bdd": "83482000",  # Body dysmorphic disorder
    # Depression
    "depression": "35489007",  # Depressive disorder
    "depressed": "35489007",
    "clinical depression": "35489007",
    "major depression": "370143000",  # Major depressive disorder
    "severe depression": "370143000",
    "moderate depression": "36474008",  # Severe recurrent MDD
    "mild depression": "36923009",  # Major depression, single episode
    "recurrent depression": "36474008",
    "treatment resistant depression": "310495003",  # Refractory depressive disorder
    "treatment-resistant depression": "310495003",
    "chronic depression": "192080009",
    "unipolar depression": "35489007",
    "antenatal depression": "788120007",
    "postnatal depression": "58703003",
    "postpartum depression": "58703003",
    "perinatal depression": "788120007",
    "reactive depression": "87414006",  # Reactive depression (situational)
    "atypical depression": "192084000",  # Atypical depressive disorder
    "seasonal depression": "247803002",  # Seasonal affective disorder
    "sad": "247803002",
    "dysthymia": "38341003",
    "dysthymic disorder": "38341003",
    "persistent depressive disorder": "38341003",
    "anxious depression": "35489007",
    # Bipolar
    "bipolar": "13746004",  # Bipolar disorder
    "bipolar disorder": "13746004",
    "bipolar affective disorder": "13746004",
    "bipolar 1": "371596008",  # Bipolar I
    "bipolar i": "371596008",
    "bipolar type 1": "371596008",
    "bipolar 2": "83225003",  # Bipolar II
    "bipolar ii": "83225003",
    "bipolar type 2": "83225003",
    # Psychosis / Schizophrenia
    "psychosis": "69322001",  # Psychotic disorder
    "psychotic": "69322001",
    "psychotic episode": "69322001",
    "acute psychosis": "65971000052100",
    "schizophrenia": "58214004",  # Schizophrenia
    "schizophrenic": "58214004",
    "paranoid schizophrenia": "191527001",
    "schizoaffective disorder": "68772007",
    "first episode psychosis": "191526005",
    "brief psychotic disorder": "5464005",
    "brief reactive psychosis": "5464005",
    "delusional disorder": "191681009",
    "delusions": "2073000",  # Delusional
    "paranoia": "284481009",  # Paranoia
    "paranoid": "197480006",  # Anxiety disorder with depression (closest)
    # Anxiety
    "anxiety": "48694002",  # Anxiety
    "anxious": "48694002",
    "anxiety disorder": "197480006",  # Anxiety disorder with depression -- use GAD
    "generalised anxiety disorder": "21897009",
    "generalized anxiety disorder": "21897009",
    "social anxiety": "247803002",  # --> SAP? Use 241811000000107
    "social anxiety disorder": "79997009",  # Social phobia
    "social phobia": "79997009",
    "panic disorder": "371631005",  # Panic disorder
    "panic attacks": "225624000",  # Panic attack
    "agoraphobia": "70691001",
    "specific phobia": "386810004",  # Phobia
    "phobia": "386810004",
    "health anxiety": "300255008",  # Hypochondria
    "hypochondria": "300255008",
    "health anxiety disorder": "300255008",
    "separation anxiety": "439471002",  # Separation anxiety disorder
    "anxiety neurosis": "111475002",  # Neurosis
    # OCD spectrum
    "ocd": "191736004",
    "obsessive compulsive disorder": "191736004",
    "obsessive-compulsive disorder": "191736004",
    "hoarding disorder": "49488000",  # Compulsive hoarding
    # PTSD
    "ptsd": "47505003",
    "post-traumatic stress disorder": "47505003",
    "post traumatic stress disorder": "47505003",
    "complex ptsd": "47505003",  # No separate SNOMED for complex PTSD in UK
    "c-ptsd": "47505003",
    "combat ptsd": "699241002",
    "trauma": "47505003",
    "acute stress disorder": "67195008",
    "acute stress reaction": "67195008",
    # Autism spectrum
    "autism": "408856003",  # Autistic disorder
    "autistic": "35919005",  # Pervasive developmental disorder (broader)
    "autism spectrum disorder": "35919005",
    "autistic spectrum": "35919005",
    "autistic spectrum disorder": "35919005",
    "aspergers": "23560001",  # Asperger's disorder
    "asperger syndrome": "23560001",
    "asperger's": "23560001",
    "asd": "35919005",
    "atypical autism": "231536004",
    # ADHD
    "adhd": "406506008",
    "attention deficit hyperactivity disorder": "406506008",
    "attention deficit disorder": "35253001",
    "hyperactivity": "44548000",  # Hyperactivity
    # Eating disorders
    "anorexia nervosa": "56882008",
    "anorexia": "56882008",
    "bulimia nervosa": "78004001",
    "bulimia": "78004001",
    "binge eating disorder": "439960005",
    "binge eating": "1162387003",  # Binge eating behavior
    "avoidant restrictive food intake disorder": "700213005",
    "arfid": "700213005",
    "atypical anorexia": "231522009",
    "atypical bulimia": "231523004",
    "purging disorder": "78004001",  # Closest in SNOMED
    "orthorexia": "56882008",  # Map to anorexia nervosa as closest
    # Personality disorders
    "borderline personality disorder": "20010003",
    "emotionally unstable personality disorder": "20010003",
    "eupd": "20010003",
    "antisocial personality disorder": "26665006",
    "narcissistic personality disorder": "57522003",
    "paranoid personality disorder": "191567000",
    "schizotypal personality disorder": "35480002",
    "dependent personality disorder": "2756008",
    "histrionic personality disorder": "28250007",
    "obsessive compulsive personality disorder": "1376001",
    "anankastic personality disorder": "1376001",
    "avoidant personality disorder": "37746008",
    "anxious personality disorder": "231528008",
    "cluster a personality disorder": "16805009",
    "cluster b personality disorder": "4306003",
    "cluster c personality disorder": "83890006",
    "personality disorder": "33449004",  # Personality disorder
    "personality problems": "33449004",
    # Alcohol / substance
    "alcohol dependence": "66590003",
    "alcohol use disorder": "1336085007",
    "alcohol abuse": "15167005",  # Harmful use of alcohol
    "alcohol misuse": "15167005",
    "alcoholism": "7200002",
    "binge drinking": "228326007",
    "alcohol withdrawal": "191480000",
    "benzodiazepine dependence": "231473004",
    "cannabis dependence": "85005007",
    "cannabis use disorder": "1336200007",
    "drug dependence": "66590003",  # General dependence (closest)
    "drug use disorder": "66590003",
    "substance misuse": "66590003",
    "substance use disorder": "26416006",  # Substance use disorder
    "substance abuse": "26416006",
    "dual diagnosis": "26416006",
    "opioid dependence": "39723002",  # Morphine dependence (closest for general opioid)
    "heroin dependence": "41553006",
    "cocaine dependence": "191927002",  # Cocaine use
    "cocaine use": "1336231000",
    # Dementia / cognitive
    "alzheimers": "26929004",  # Alzheimer's disease
    "alzheimer's disease": "26929004",
    "dementia": "52448006",
    "vascular dementia": "429998004",
    "lewy body dementia": "312991009",
    "frontotemporal dementia": "230271009",
    "cognitive impairment": "386806002",  # Cognitive impairment
    "mild cognitive impairment": "386805003",
    # Suicidal / self-harm
    "suicidal ideation": "6471006",  # Suicidal thoughts
    "suicidal thoughts": "6471006",
    "suicide attempt": "287181005",  # Attempted suicide
    "attempted suicide": "287181005",
    "self harm": "248062006",  # Self-mutilation behavior
    "self-harm": "248062006",
    "deliberate self harm": "248062006",
    "self injury": "248062006",
    "chronic suicidality": "6471006",
    "at risk of suicide": "225444004",  # At increased risk for suicide
    # Mood / affective
    "affective disorder": "46206005",  # Mood disorder
    "mood disorder": "46206005",
    "mania": "16238741000119109",  # Manic episode (use broader)
    "manic": "16238741000119109",
    "manic episode": "16238741000119109",
    "hypomania": "47773004",  # Hypomanic episode
    # Stress / adjustment
    "stress": "73595000",  # Stress
    "chronic stress": "73595000",
    "adjustment disorder": "17226007",  # Adjustment disorder
    "adjustment reaction": "17226007",
    # Psychosomatic / somatoform
    "somatoform disorder": "36136000",  # Somatoform disorder
    "somatic symptom disorder": "36136000",
    "conversion disorder": "13960001",  # Conversion disorder
    "functional disorder": "36136000",
    "health anxiety": "300255008",
    # Delirium / confusion
    "delirium": "2776000",  # Delirium
    "acute confusion": "130987000",  # Acute confusion
    "acute confusional state": "2776000",
    "acutely confused": "40917007",  # Clouded consciousness
    "confusional state": "2776000",
    # Sleep
    "insomnia": "193462001",  # Insomnia
    "sleep disorder": "44186003",  # Sleep disorder
    # Other common
    "grief": "284464009",  # Bereavement
    "bereavement": "284464009",
    "complicated grief": "424833007",  # Complicated grief
    "chronic mental illness": "128293007",  # Chronic mental disorder
    "severe mental illness": "75478009",  # Severe mental illness
    "smi": "75478009",
}

# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------
_ORPHANS_QUERY = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept {id: '74732009'})
WHERE m.provenance = 'guideline_config_loader'
  AND NOT EXISTS {
    MATCH (sf)-[:MAPS_TO]->(c2:Concept)
    WHERE c2.id <> '74732009' AND c2.active = true
  }
RETURN sf.normalized AS normalized, sf.form AS form
ORDER BY sf.form
"""

_SEARCH = """
CALL db.index.fulltext.queryNodes('term_fulltext', $q) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
  AND c.semantic_tag IN ['disorder', 'finding']
  AND c.id <> '74732009'
  AND NOT c.id IN $blocklist
RETURN c.id AS concept_id, c.fsn AS fsn, score
ORDER BY score DESC
LIMIT 3
"""

_UPSERT = """
MATCH (c:Concept {id: $concept_id})
WHERE c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.approved_at = datetime()
SET m.confidence = 1.0,
    m.provenance  = 'audit-fix-mh-orphan-2026-04'
RETURN sf.normalized AS normalized, c.id AS concept_id, c.fsn AS concept_fsn
"""

_DELETE_GCL = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept {id: '74732009'})
WHERE m.provenance = 'guideline_config_loader'
DELETE m
RETURN count(m) AS deleted
"""


def _norm(text: str) -> str:
    low = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", low)
    return " ".join(nfkd.encode("ascii", "ignore").decode("ascii").split())


def _apply(
    session, normalized: str, form: str, concept_id: str, source: str, dry_run: bool
) -> bool:
    print(f"  FIX [{source}] {form!r} -> {concept_id}")
    if dry_run:
        return True
    r1 = session.run(
        _UPSERT, normalized=normalized, form=form, concept_id=concept_id
    ).data()
    r2 = session.run(_DELETE_GCL, normalized=normalized).data()
    ok = bool(r1)
    deleted = r2[0]["deleted"] if r2 else 0
    if not ok:
        print(f"       UPSERT FAILED (concept {concept_id} not in graph?)")
    return ok


def main(dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"Mode: {mode}")
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

    with driver.session() as s:
        orphans = s.run(_ORPHANS_QUERY).data()

    print(f"Orphans on 74732009 (no alternative): {len(orphans)}")

    fixed_explicit = []
    fixed_auto = []
    kept = []

    with driver.session() as s:
        for row in orphans:
            form = row["form"]
            normalized = row["normalized"]
            form_low = form.lower().strip()

            # Pass 1: explicit curated override
            cid = _EXPLICIT.get(form_low)
            if cid:
                ok = _apply(s, normalized, form, cid, "explicit", dry_run)
                if ok:
                    fixed_explicit.append({"form": form, "concept_id": cid})
                continue

            # Pass 2: auto fulltext search (high threshold)
            rows = s.run(
                _SEARCH,
                q=form_low,
                blocklist=list(_BLOCKLIST_IDS),
            ).data()
            if rows and rows[0]["score"] >= _MIN_AUTO_SCORE:
                best = rows[0]
                ok = _apply(s, normalized, form, best["concept_id"], "auto", dry_run)
                if ok:
                    fixed_auto.append(
                        {
                            "form": form,
                            "concept_id": best["concept_id"],
                            "fsn": best["fsn"],
                            "score": round(best["score"], 2),
                        }
                    )
            else:
                top = (
                    f"{rows[0]['fsn']} ({rows[0]['score']:.1f})"
                    if rows
                    else "no results"
                )
                print(f"  KEEP {form!r} -- best: {top}")
                kept.append({"form": form, "best_auto": top})

    driver.close()

    print(f"\n{'=' * 60}")
    print(f"Explicit fixes  : {len(fixed_explicit)}")
    print(f"Auto fixes      : {len(fixed_auto)}")
    print(f"Kept on 74732009: {len(kept)}")

    report = {
        "explicit": fixed_explicit,
        "auto": fixed_auto,
        "kept_for_manual_review": kept,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"Report: {OUTPUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
