#!/usr/bin/env python3
"""Seed a complete demo GP practice ecosystem into the Patient Graph.

Creates a realistic cohort (80 patients, varied cancer types, comorbidities,
milestones, and blood-signal data) that satisfies every NCDA audit Cypher
query without modifying any application code.

Usage:
    python -m scripts.seed_demo_practice           # seed (idempotent guard)
    python -m scripts.seed_demo_practice --force   # teardown then re-seed
    python -m scripts.seed_demo_practice --teardown  # remove all demo data
    python -m scripts.seed_demo_practice --list    # print demo org/patient IDs

Guard: skips silently if demo-gp-001 already exists (unless --force).
Teardown: DETACH DELETE every node carrying source='demo'.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "secrets", ".env"))
# Also load root .env for local dev (credentials live there when secrets/ is empty)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

# ---------------------------------------------------------------------------
# Fixed seed so repeated --force runs produce the same patient IDs/dates.
# ---------------------------------------------------------------------------
_RNG = random.Random(42)

DEMO_GP_ID = "demo-gp-001"
DEMO_PCN_ID = "demo-pcn-001"
DEMO_ICB_ID = "demo-icb-001"
DEMO_ALLIANCE_ID = "demo-alliance-001"
DEMO_SP_ID = "demo-sp-001"
DEMO_SERVICE_ID = "demo-service-001"

_CANCER_TYPES = ["lung", "colorectal", "breast", "prostate", "upper_gi", "skin"]
_REFERRAL_ROUTES = ["2ww", "routine", "urgent"]
_PLACES = ["gp", "a_and_e", "other"]
_STAGES = ["I", "II", "III", "IV"]

# SNOMED concept IDs from _COMORBIDITY_CODE_META in _audit_comorbidities.py
_COMORBIDITY_SNOMED: list[tuple[str, str]] = [
    ("38341003", "Hypertension"),
    ("73211009", "Diabetes mellitus"),
    ("13645005", "COPD"),
    ("49601007", "Cardiovascular disease"),
    ("74732009", "Mental health disorder"),
    ("266987004", "Previous cancer"),
]

# Well-known SNOMED symptom concept IDs likely present in ncda-symptoms ValueSet
_SYMPTOM_SNOMED: list[tuple[str, str]] = [
    ("267060002", "Rectal bleeding"),
    ("21522001", "Abdominal pain"),
    ("162076009", "Excessive weight loss"),
    ("49727002", "Cough"),
    ("66857006", "Haemoptysis"),
    ("40739000", "Dysphagia"),
    ("83128009", "Haematuria"),
    ("309568002", "Breast lump"),
]

_N_PATIENTS = 80
_N_CANCER = 35
_N_BENIGN = 25
_N_OPEN = 10
_N_BLOOD = 10  # patients with bf_* blood signal data


# ---------------------------------------------------------------------------
# Org hierarchy
# ---------------------------------------------------------------------------

_ORG_SPECS: list[tuple[str, str, str, str]] = [
    ("GPPractice:Organization", DEMO_GP_ID, "Demo Medical Centre", "DEMO01"),
    ("PCN:Organization", DEMO_PCN_ID, "Demo PCN", "DEMOPCN"),
    ("ICB:Organization", DEMO_ICB_ID, "Demo ICB", "DEMOICB"),
    ("CancerAlliance:Organization", DEMO_ALLIANCE_ID, "Demo Cancer Alliance", "DEMOCA"),
    ("ServiceProvider:Organization", DEMO_SP_ID, "Demo Hospital Trust", "DEMOSP"),
]


def _seed_org_nodes(client: PatientGraphClient) -> None:
    for label_str, oid, name, ods in _ORG_SPECS:
        client.run(
            f"MERGE (o:{label_str} {{id: $id}}) "
            "ON CREATE SET o.name = $name, o.odsCode = $ods, "
            "  o.short_name = $name, o.source = 'demo', "
            "  o.onboarding_status = 'active', o.created_at = datetime()",
            id=oid,
            name=name,
            ods=ods,
        )


def _seed_org_hierarchy(client: PatientGraphClient) -> None:
    """Create GPPractice, PCN, ICB, CancerAlliance, ServiceProvider, Service."""
    _seed_org_nodes(client)
    _seed_org_relationships(client)
    _seed_service(client)
    print(f"  [OK] Org hierarchy seeded under {DEMO_GP_ID}")


def _seed_org_relationships(client: PatientGraphClient) -> None:
    client.run(
        "MATCH (gp:GPPractice {id: $gp}), (pcn:PCN {id: $pcn}) "
        "MERGE (gp)-[:PART_OF_PCN]->(pcn)",
        gp=DEMO_GP_ID,
        pcn=DEMO_PCN_ID,
    )
    client.run(
        "MATCH (pcn:PCN {id: $pcn}), (icb:ICB {id: $icb}) "
        "MERGE (pcn)-[:COMMISSIONED_BY]->(icb)",
        pcn=DEMO_PCN_ID,
        icb=DEMO_ICB_ID,
    )
    client.run(
        "MATCH (gp:GPPractice {id: $gp}), (icb:ICB {id: $icb}) "
        "MERGE (gp)-[:COMMISSIONED_BY]->(icb)",
        gp=DEMO_GP_ID,
        icb=DEMO_ICB_ID,
    )
    client.run(
        "MATCH (icb:ICB {id: $icb}), (ca:CancerAlliance {id: $ca}) "
        "MERGE (icb)-[:PART_OF_ALLIANCE]->(ca)",
        icb=DEMO_ICB_ID,
        ca=DEMO_ALLIANCE_ID,
    )


def _seed_service(client: PatientGraphClient) -> None:
    client.run(
        "MERGE (s:Service {id: $id}) "
        "ON CREATE SET s.name = 'Demo Oncology Service', "
        "  s.source = 'demo', s.created_at = datetime()",
        id=DEMO_SERVICE_ID,
    )
    client.run(
        "MATCH (sp:ServiceProvider {id: $sp}), (s:Service {id: $sid}) "
        "MERGE (sp)-[:PROVIDES_SERVICE]->(s)",
        sp=DEMO_SP_ID,
        sid=DEMO_SERVICE_ID,
    )


# ---------------------------------------------------------------------------
# Practitioner
# ---------------------------------------------------------------------------


def _seed_practitioner(client: PatientGraphClient) -> None:
    """Create demo clinician and demo admin linked to the demo GP."""
    users = [
        ("demo.clinician@demo.nhs.uk", "Demo Clinician", False, "triage_clinician"),
        ("demo.admin@demo.nhs.uk", "Demo Admin", True, "administrator"),
    ]
    for email, name, is_admin, role_name in users:
        client.run(
            "MERGE (pr:User {email: $email}) "
            "ON CREATE SET pr.name = $name, pr.is_platform_admin = $is_admin, "
            "  pr.source = 'demo', pr.selected_role = $role, "
            "  pr.created_at = datetime() "
            "SET pr:User",
            email=email,
            name=name,
            is_admin=is_admin,
            role=role_name,
        )
        client.run(
            "MATCH (pr:User {email: $email}), (o:Organization {id: $org}) "
            "MERGE (pr)-[:WORKS_AT]->(o)",
            email=email,
            org=DEMO_GP_ID,
        )
        client.run(
            "MATCH (pr:User {email: $email}) "
            "MERGE (r:Role {id: $role}) "
            "ON CREATE SET r.name = $role, r.source = 'demo' "
            "MERGE (g:Group {id: $gid}) "
            "ON CREATE SET g.name = $role, g.source = 'demo' "
            "MERGE (g)-[:HAS_ROLE]->(r) "
            "MERGE (pr)-[:IS_MEMBER_OF]->(g)",
            email=email,
            role=role_name,
            gid=f"demo-role-{role_name}",
        )
    print("  [OK] Practitioners seeded (demo.clinician / demo.admin)")


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------


def _rand_birth_date(age_min: int = 40, age_max: int = 85) -> str:
    age = _RNG.randint(age_min, age_max)
    anchor = date(2024, 6, 1)
    return (anchor - timedelta(days=age * 365 + _RNG.randint(0, 364))).isoformat()


def _seed_patients(client: PatientGraphClient) -> None:
    """Create 80 Patient nodes linked to the demo GP practice."""
    genders = ["male"] * 42 + ["female"] * 38
    _RNG.shuffle(genders)
    for i in range(1, _N_PATIENTS + 1):
        pid = f"demo-patient-{i:03d}"
        client.run(
            "MERGE (p:Patient {id: $id}) "
            "ON CREATE SET p.gender = $gender, p.birthDate = $dob, "
            "  p.source = 'demo', p.created_at = datetime()",
            id=pid,
            gender=genders[i - 1],
            dob=_rand_birth_date(),
        )
        client.run(
            "MATCH (p:Patient {id: $pid}), (gp:GPPractice {id: $gp}) "
            "MERGE (p)-[:HAS_GENERAL_PRACTITIONER]->(gp)",
            pid=pid,
            gp=DEMO_GP_ID,
        )
    print(f"  [OK] {_N_PATIENTS} patients seeded")


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


def _cohort_fields(idx: int) -> tuple:
    """Return (status, cancer_type, staging, early_late, inferred_outcome)."""
    ct = _CANCER_TYPES[(idx - 1) % len(_CANCER_TYPES)]
    if idx <= _N_CANCER:
        stg = _STAGES[(idx - 1) % len(_STAGES)]
        return "completed", ct, stg, "early" if stg in ("I", "II") else "late", "cancer"
    if idx <= _N_CANCER + _N_BENIGN:
        return "closed_benign", None, None, None, "cancer_excluded"
    if idx <= _N_CANCER + _N_BENIGN + _N_OPEN:
        return "in_progress", ct, None, None, None
    stg = _STAGES[(idx - 1) % 2]
    return "completed", ct, stg, "early", "cancer"


def _episode_props(idx: int) -> dict:
    """Return deterministic EpisodeOfCare properties for patient index idx."""
    pid = f"demo-patient-{idx:03d}"
    ep_id = f"demo-ep-{idx:03d}"
    ref_date = (date(2023, 1, 1) + timedelta(days=_RNG.randint(0, 700))).isoformat()
    fp_date = (
        date.fromisoformat(ref_date) - timedelta(days=_RNG.randint(7, 60))
    ).isoformat()
    status, cancer_type, staging, early_late, inferred = _cohort_fields(idx)
    return {
        "ep_id": ep_id,
        "patient_id": pid,
        "status": status,
        "cancer_type": cancer_type,
        "staging_value": staging,
        "staging_early_late": early_late,
        "referral_date": ref_date,
        "first_presentation_date": fp_date,
        "referral_route": _RNG.choice(_REFERRAL_ROUTES),
        "place_of_presentation": _RNG.choice(_PLACES),
        "prior_consultations_n": _RNG.randint(1, 5),
        "safety_netting_recorded": _RNG.random() > 0.35,
        "care_obstruction_patient_factor": _RNG.random() > 0.8,
        "care_obstruction_system_factor": _RNG.random() > 0.7,
        "audit_flag": _RNG.random() > 0.85,
        "inferred_outcome": inferred,
        "letter_inferred_benign": status == "closed_benign",
        "source": "ncda_detector",
    }


def _seed_episodes(client: PatientGraphClient) -> None:
    """Create one EpisodeOfCare per patient."""
    for i in range(1, _N_PATIENTS + 1):
        p = _episode_props(i)
        client.run(
            "MERGE (ep:EpisodeOfCare {episode_id: $ep_id}) "
            "ON CREATE SET "
            "  ep.patient_id = $patient_id, ep.status = $status, "
            "  ep.cancer_type = $cancer_type, ep.staging_value = $staging_value, "
            "  ep.staging_early_late = $staging_early_late, "
            "  ep.referral_date = $referral_date, "
            "  ep.first_presentation_date = $first_presentation_date, "
            "  ep.referral_route = $referral_route, "
            "  ep.place_of_presentation = $place_of_presentation, "
            "  ep.prior_consultations_n = $prior_consultations_n, "
            "  ep.safety_netting_recorded = $safety_netting_recorded, "
            "  ep.care_obstruction_patient_factor = $care_obstruction_patient_factor, "
            "  ep.care_obstruction_system_factor = $care_obstruction_system_factor, "
            "  ep.audit_flag = $audit_flag, "
            "  ep.inferred_outcome = $inferred_outcome, "
            "  ep.letter_inferred_benign = $letter_inferred_benign, "
            "  ep.source = $source, ep.created_at = datetime()",
            **p,
        )
        client.run(
            "MATCH (p:Patient {id: $pid}), (ep:EpisodeOfCare {episode_id: $ep_id}) "
            "MERGE (p)-[:HAS_EPISODE_OF_CARE]->(ep)",
            pid=p["patient_id"],
            ep_id=p["ep_id"],
        )
    print(f"  [OK] {_N_PATIENTS} episodes seeded")


# ---------------------------------------------------------------------------
# Milestone encounters
# ---------------------------------------------------------------------------


def _seed_milestone_encounters(client: PatientGraphClient) -> None:
    """Create referral + outcome milestone encounters per episode."""
    for i in range(1, _N_PATIENTS + 1):
        p = _episode_props(i)
        _create_milestone(
            client,
            i,
            "referral",
            p["referral_date"],
            p["patient_id"],
            p["ep_id"],
        )
        if p["status"] in ("completed",) and p["inferred_outcome"] == "cancer":
            diag_date = (
                date.fromisoformat(p["referral_date"])
                + timedelta(days=_RNG.randint(30, 120))
            ).isoformat()
            _create_milestone(
                client,
                i,
                "diagnosis",
                diag_date,
                p["patient_id"],
                p["ep_id"],
            )
        elif p["status"] == "closed_benign":
            close_date = (
                date.fromisoformat(p["referral_date"])
                + timedelta(days=_RNG.randint(20, 90))
            ).isoformat()
            _create_milestone(
                client,
                i,
                "benign_closure",
                close_date,
                p["patient_id"],
                p["ep_id"],
            )
    print(f"  [OK] Milestone encounters seeded")


def _create_milestone(
    client: PatientGraphClient,
    idx: int,
    milestone_type: str,
    enc_date: str,
    patient_id: str,
    ep_id: str,
) -> None:
    enc_id = f"demo-enc-{idx:03d}-{milestone_type}"
    client.run(
        "MERGE (enc:Encounter {id: $enc_id}) "
        "ON CREATE SET enc.date = $date, enc.source = 'demo', "
        "  enc.text = $text, enc.created_at = datetime()",
        enc_id=enc_id,
        date=enc_date,
        text=f"Demo {milestone_type} encounter",
    )
    client.run(
        "MATCH (p:Patient {id: $pid}), (enc:Encounter {id: $enc_id}) "
        "MERGE (p)-[:HAS_ENCOUNTER]->(enc)",
        pid=patient_id,
        enc_id=enc_id,
    )
    client.run(
        "MATCH (enc:Encounter {id: $enc_id}), (ep:EpisodeOfCare {episode_id: $ep_id}) "
        "MERGE (enc)-[r:IS_PART_OF {milestone_type: $mt}]->(ep)",
        enc_id=enc_id,
        ep_id=ep_id,
        mt=milestone_type,
    )


# ---------------------------------------------------------------------------
# Symptom encounters
# ---------------------------------------------------------------------------


def _fetch_kg_symptom_ids(client: PatientGraphClient) -> list[str]:
    """Try to read valid symptom concept IDs from the Knowledge Graph ValueSet."""
    try:
        from libs.neo4j_client.client import KnowledgeGraphClient

        kg = KnowledgeGraphClient()
        try:
            rows = kg.run(
                "MATCH (v:ValueSet {id: 'ncda-symptoms'}) "
                "RETURN v.rawJson AS raw_json LIMIT 1"
            )
        finally:
            kg.close()
        if rows and rows[0].get("raw_json"):
            import json

            vs = json.loads(rows[0]["raw_json"])
            ids = [
                str(c.get("code") or c.get("concept_id") or "")
                for entry in vs.get("compose", {}).get("include", [])
                for c in entry.get("concept", [])
                if c.get("code") or c.get("concept_id")
            ]
            if ids:
                return ids[:8]
    except Exception:  # noqa: BLE001
        pass
    # Fall back to well-known SNOMED symptom IDs
    return [cid for cid, _ in _SYMPTOM_SNOMED]


def _seed_symptom_encounters(client: PatientGraphClient) -> None:
    """Create symptom Encounters with DOCUMENTS edges within referral window."""
    symptom_ids = _fetch_kg_symptom_ids(client)
    cancer_patients = range(1, _N_CANCER + 1)
    for i in cancer_patients:
        p = _episode_props(i)
        ref_dt = date.fromisoformat(p["referral_date"])
        enc_date = (ref_dt - timedelta(days=_RNG.randint(0, 5))).isoformat()
        enc_id = f"demo-enc-{i:03d}-symptoms"
        client.run(
            "MERGE (enc:Encounter {id: $enc_id}) "
            "ON CREATE SET enc.date = $date, enc.source = 'demo', "
            "  enc.text = 'Demo symptom encounter', enc.created_at = datetime()",
            enc_id=enc_id,
            date=enc_date,
        )
        client.run(
            "MATCH (p:Patient {id: $pid}), (enc:Encounter {id: $enc_id}) "
            "MERGE (p)-[:HAS_ENCOUNTER]->(enc)",
            pid=p["patient_id"],
            enc_id=enc_id,
        )
        chosen = _RNG.sample(symptom_ids, min(3, len(symptom_ids)))
        for cid in chosen:
            _create_documents_edge(client, enc_id, cid, "symptoms")
    print(f"  [OK] Symptom encounters seeded ({len(symptom_ids)} symptom IDs)")


def _create_documents_edge(
    client: PatientGraphClient,
    enc_id: str,
    concept_id: str,
    domain: str,
) -> None:
    node_id = f"demo-disorder-{concept_id}"
    client.run(
        "MERGE (d:Disorder {id: $nid}) "
        "ON CREATE SET d.conceptId = $cid, d.source = 'demo', "
        "  d.name = $nid, d.created_at = datetime()",
        nid=node_id,
        cid=concept_id,
    )
    client.run(
        "MATCH (enc:Encounter {id: $enc_id}), (d:Disorder {id: $nid}) "
        "MERGE (enc)-[:DOCUMENTS {domain: $domain, conceptId: $cid}]->(d)",
        enc_id=enc_id,
        nid=node_id,
        domain=domain,
        cid=concept_id,
    )


# ---------------------------------------------------------------------------
# Comorbidities
# ---------------------------------------------------------------------------


def _seed_comorbidities(client: PatientGraphClient) -> None:
    """Add HAS_DISEASE edges from patients to Disorder nodes (SNOMED IDs)."""
    all_patients = range(1, _N_PATIENTS + 1)
    for i in all_patients:
        pid = f"demo-patient-{i:03d}"
        chosen = _RNG.sample(_COMORBIDITY_SNOMED, _RNG.randint(1, 3))
        for cid, label in chosen:
            node_id = f"demo-disorder-{cid}"
            client.run(
                "MERGE (d:Disorder {id: $nid}) "
                "ON CREATE SET d.conceptId = $cid, d.source = 'demo', "
                "  d.name = $label, d.created_at = datetime()",
                nid=node_id,
                cid=cid,
                label=label,
            )
            client.run(
                "MATCH (p:Patient {id: $pid}), (d:Disorder {id: $nid}) "
                "MERGE (p)-[:HAS_DISEASE {domain: 'comorbidities'}]->(d)",
                pid=pid,
                nid=node_id,
            )
    print(f"  [OK] Comorbidities seeded ({len(_COMORBIDITY_SNOMED)} SNOMED groups)")


# ---------------------------------------------------------------------------
# Blood signal
# ---------------------------------------------------------------------------


def _blood_z() -> float:
    return round(_RNG.gauss(0, 1), 4)


def _seed_blood_signal(client: PatientGraphClient) -> None:
    """Add bf_* z-score properties to the last _N_BLOOD episodes."""
    blood_range = range(
        _N_CANCER + _N_BENIGN + _N_OPEN + 1,
        _N_CANCER + _N_BENIGN + _N_OPEN + _N_BLOOD + 1,
    )
    for i in blood_range:
        p = _episode_props(i)
        anchor = p["referral_date"]
        cohort = "cancer" if p["inferred_outcome"] == "cancer" else "benign"
        client.run(
            "MATCH (ep:EpisodeOfCare {episode_id: $ep_id}) "
            "SET ep.bf_cohort_label = $label, ep.bf_anchor_date = $anchor, "
            "  ep.bf_lymphocyte_z = $lz, ep.bf_neutrophil_pct_z = $nz, "
            "  ep.bf_haemoglobin_z = $hz, ep.bf_platelet_z = $pz",
            ep_id=p["ep_id"],
            label=cohort,
            anchor=anchor,
            lz=_blood_z(),
            nz=_blood_z(),
            hz=_blood_z(),
            pz=_blood_z(),
        )
        _seed_blood_obs_encounter(client, i, p["patient_id"], anchor)
    print(f"  [OK] Blood signal properties set on {_N_BLOOD} episodes")


_BLOOD_OBS: list[tuple[str, str, str]] = [
    ("demo-obs-lymphocyte", "Lymphocyte count", "104208008"),
    ("demo-obs-neutrophil-pct", "Neutrophil percent count in blood", "415507003"),
    ("demo-obs-haemoglobin", "Haemoglobin", "259695003"),
    ("demo-obs-platelet", "Platelet count", "365632008"),
]


def _link_blood_obs_to_encounter(
    client: PatientGraphClient,
    enc_id: str,
) -> None:
    for obs_id, obs_name, cid in _BLOOD_OBS:
        client.run(
            "MERGE (obs:Observable_entity {id: $oid}) "
            "ON CREATE SET obs.name = $name, obs.conceptId = $cid, "
            "  obs.source = 'demo', obs.created_at = datetime()",
            oid=obs_id,
            name=obs_name,
            cid=cid,
        )
        client.run(
            "MATCH (enc:Encounter {id: $enc_id}), (obs:Observable_entity {id: $oid}) "
            "MERGE (enc)-[:DOCUMENTS {domain: 'observations', value: $val}]->(obs)",
            enc_id=enc_id,
            oid=obs_id,
            val=round(_RNG.gauss(5.0, 1.5), 2),
        )


def _seed_blood_obs_encounter(
    client: PatientGraphClient,
    idx: int,
    patient_id: str,
    anchor_date: str,
) -> None:
    """Create blood test encounters with Observable_entity DOCUMENTS edges."""
    enc_date = (
        date.fromisoformat(anchor_date) - timedelta(days=_RNG.randint(14, 90))
    ).isoformat()
    enc_id = f"demo-enc-{idx:03d}-blood"
    client.run(
        "MERGE (enc:Encounter {id: $enc_id}) "
        "ON CREATE SET enc.date = $date, enc.source = 'demo', "
        "  enc.text = 'Demo blood test encounter', enc.created_at = datetime()",
        enc_id=enc_id,
        date=enc_date,
    )
    client.run(
        "MATCH (p:Patient {id: $pid}), (enc:Encounter {id: $enc_id}) "
        "MERGE (p)-[:HAS_ENCOUNTER]->(enc)",
        pid=patient_id,
        enc_id=enc_id,
    )
    _link_blood_obs_to_encounter(client, enc_id)


# ---------------------------------------------------------------------------
# Guard, teardown, list
# ---------------------------------------------------------------------------


def _already_seeded(client: PatientGraphClient) -> bool:
    rows = client.run(
        "MATCH (o:Organization {id: $id}) RETURN count(o) AS cnt",
        id=DEMO_GP_ID,
    )
    return bool(rows and rows[0].get("cnt", 0) > 0)


def _teardown(client: PatientGraphClient) -> None:
    """Remove all nodes carrying source='demo'."""
    client.run("MATCH (n {source: 'demo'}) DETACH DELETE n")
    print("  [OK] Demo data removed")


def _list_demo_data(client: PatientGraphClient) -> None:
    orgs = client.run(
        "MATCH (o:Organization {source: 'demo'}) "
        "RETURN labels(o) AS labels, o.id AS id, o.name AS name ORDER BY o.name"
    )
    print(f"\n{'='*60}")
    print("DEMO ORGANISATIONS")
    print(f"{'='*60}")
    for r in orgs:
        print(f"  {r['name']} ({r['id']})  {r['labels']}")
    pts = client.run("MATCH (p:Patient {source: 'demo'}) RETURN count(p) AS n")
    print(f"\nPatients: {pts[0]['n'] if pts else 0}")
    eps = client.run(
        "MATCH (ep:EpisodeOfCare {source: 'ncda_detector'}) "
        "WHERE ep.episode_id STARTS WITH 'demo-' RETURN count(ep) AS n"
    )
    print(f"Episodes: {eps[0]['n'] if eps else 0}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _seed_all(client: PatientGraphClient) -> None:
    print(f"\n{'='*60}")
    print("SEEDING DEMO PRACTICE")
    print(f"{'='*60}")
    _seed_org_hierarchy(client)
    _seed_practitioner(client)
    _seed_patients(client)
    _seed_episodes(client)
    _seed_milestone_encounters(client)
    _seed_symptom_encounters(client)
    _seed_comorbidities(client)
    _seed_blood_signal(client)
    print(f"\n{'='*60}")
    print("DONE - login as demo.clinician@demo.nhs.uk and open /care/audit")
    print(f"{'='*60}\n")


def main() -> None:
    force = "--force" in sys.argv
    teardown_only = "--teardown" in sys.argv
    list_only = "--list" in sys.argv

    client = PatientGraphClient()
    try:
        if list_only:
            _list_demo_data(client)
            return

        if teardown_only:
            print("Removing demo data...")
            _teardown(client)
            return

        if _already_seeded(client):
            if not force:
                print(
                    f"Demo practice already seeded ({DEMO_GP_ID}). "
                    "Use --force to re-seed or --teardown to remove."
                )
                return
            print("--force: removing existing demo data before re-seeding...")
            _teardown(client)

        _seed_all(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
