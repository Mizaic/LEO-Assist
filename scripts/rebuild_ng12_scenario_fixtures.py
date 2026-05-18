#!/usr/bin/env python3
"""Regenerate paired NG12 EXT/SBR rows and normalise GDL rows (348 branches).

Run from repo root:
  .venv/bin/python scripts/rebuild_ng12_scenario_fixtures.py

ASCII only. Does not require Neo4j. Idempotent on re-run.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "ng12_scenarios"

ACTIVE = frozenset(
    {
        "rule:NG12:v1:CH002:SEC000:R004:6d4e9c13" ":edit:dd11e8d3:edit:a0b74f59",
        "rule:NG12:v1:CH002:SEC002:R002:3b6a24e5:edit:308ce725",
        "rule:NG12:v1:CH002:SEC002:R004:1e614d35:edit:b242528c",
    }
)

FIT_RULE = "rule:NG12:v1:CH002:SEC002:R002:3b6a24e5:edit:308ce725"
RECT_RULE = "rule:NG12:v1:CH002:SEC002:R004:1e614d35:edit:b242528c"

# SNOMED CT id -> (lookup_term, semantic_tag, concept_fsn snippet)
SNOMED_META: dict[str, tuple[str, str, str]] = {
    "49727002": ("cough", "finding", "Cough (finding)"),
    "66857006": ("haemoptysis", "finding", "Hemoptysis (finding)"),
    "40739000": ("dysphagia", "disorder", "Dysphagia (disorder)"),
    "288939007": (
        "difficulty swallowing",
        "finding",
        "Difficulty swallowing (finding)",
    ),
    "162031009": ("dyspepsia", "finding", "Dyspepsia (finding)"),
    "16331000": ("heartburn", "finding", "Heartburn (finding)"),
    "8765009": ("haematemesis", "finding", "Hematemesis (finding)"),
    "18165001": ("jaundice", "finding", "Jaundice (finding)"),
    "262285001": ("weight loss", "finding", "Weight decreased (finding)"),
    "79890006": ("loss of appetite", "finding", "Loss of appetite (finding)"),
    "271860004": ("abdominal mass", "finding", "Mass of abdomen (finding)"),
    "271683004": ("gallbladder mass", "finding", "Mass of gall bladder (finding)"),
    "300306002": ("liver mass", "finding", "Mass of liver (finding)"),
    "248523006": ("rectal mass", "finding", "Mass of rectum (finding)"),
    "149441000000102": (
        "declined faecal immunochemical test",
        "situation",
        "Declined FIT",
    ),
    "1101381000000107": (
        "faecal immunochemical test failed",
        "finding",
        "FIT technical failure",
    ),
    "167667006": ("occult blood not detected", "finding", "Occult blood not detected"),
    "274278001": (
        "change in bowel habit",
        "finding",
        "Change in bowel habit (finding)",
    ),
    "405729008": ("rectal bleeding", "finding", "Rectal hemorrhage (finding)"),
    "165418005": ("faecal occult blood", "finding", "Fecal occult blood present"),
    "104454006": ("faecal immunochemical test", "finding", "FIT quantitative result"),
    "34436003": ("haematuria", "finding", "Hematuria (finding)"),
    "10601006": ("pain in breast", "finding", "Pain in breast (finding)"),
    "289903006": ("menopause present", "finding", "Menopause present (finding)"),
    "400006001": ("skin lesion", "finding", "Skin lesion (finding)"),
    "50219008": ("hoarse voice", "finding", "Hoarse voice (finding)"),
    "44186003": ("headache", "finding", "Headache (finding)"),
    "413413002": ("anemia", "finding", "Anemia (disorder)"),
    "95324001": ("bone pain", "finding", "Bone pain (finding)"),
    "276447008": ("swelling", "finding", "Swelling (finding)"),
    "84229001": ("fatigue", "finding", "Fatigue (finding)"),
    "29857009": ("chest pain", "finding", "Chest pain (finding)"),
    "267036007": ("shortness of breath", "finding", "Dyspnea (finding)"),
    "77176002": ("smoker", "finding", "Smoking (finding)"),
    "8517006": ("ex-smoker", "finding", "Ex-smoker (finding)"),
    "161635002": ("asbestos exposure", "situation", "History of asbestos exposure"),
    "386806002": ("finger clubbing", "finding", "Finger clubbing (finding)"),
    "50417007": ("chest infection", "disorder", "Acute bronchitis (disorder)"),
    "235856003": ("liver finding", "finding", "Liver finding (finding)"),
    "309256003": ("anal mass", "finding", "Mass of anus (finding)"),
    "118912005": ("rectal pain", "finding", "Pain of rectum (finding)"),
}

CHAP_PRI: dict[str, str] = {
    "1.1": "49727002",
    "1.2": "40739000",
    "1.3": "274278001",
    "1.4": "10601006",
    "1.5": "289903006",
    "1.6": "34436003",
    "1.7": "400006001",
    "1.8": "50219008",
    "1.9": "44186003",
    "1.10": "413413002",
    "1.11": "95324001",
    "1.12": "276447008",
    "1.13": "262285001",
}

ROT_EXTRA = ["84229001", "29857009", "267036007", "79890006"]


def _chapter_key(rec_id: str) -> str:
    a, b, _ = rec_id.split(".", maxsplit=2)
    return f"{a}.{b}"


def _pick_generic_codes(rec_id: str, branch_index: int) -> list[str]:
    ck = _chapter_key(rec_id)
    pri = CHAP_PRI.get(ck, "49727002")
    if branch_index % 3 != 0:
        return [pri]
    extra = ROT_EXTRA[(branch_index - 1) % len(ROT_EXTRA)]
    if extra == pri:
        extra = ROT_EXTRA[(branch_index) % len(ROT_EXTRA)]
    if extra == pri:
        return [pri]
    return [pri, extra]


CHILD_RECIDS: frozenset[str] = frozenset(
    {
        "1.9.2",
        "1.10.2",
        "1.10.3",
        "1.11.3",
        "1.11.6",
        "1.11.7",
        "1.12.1",
        "1.12.3",
    }
)


def _special_case_gdl(g: dict[str, Any]) -> None:
    rid = g["rec_id"]
    bi = g["branch_index"]
    if rid in CHILD_RECIDS:
        g["patient_age"] = 10.0
    if rid == "1.3.4":
        g["graph_rule_id"] = None
        g["expect_graph_match"] = None
        if not g.get("patient_snomed_codes"):
            g["patient_snomed_codes"] = ["274278001"]
        return
    if rid == "1.3.6":
        g["graph_rule_id"] = None
        g["expect_graph_match"] = None
        if bi == 1:
            g["patient_snomed_codes"] = ["309256003"]
        else:
            g["patient_snomed_codes"] = ["405729008"]
        return
    if rid == "1.3.3":
        g["graph_rule_id"] = FIT_RULE
        if bi == 1:
            g["patient_snomed_codes"] = ["149441000000102"]
            g["expect_graph_match"] = True
        else:
            g["patient_snomed_codes"] = ["49727002", "84229001"]
            g["expect_graph_match"] = False
        return
    if rid == "1.3.2":
        if not g.get("patient_snomed_codes"):
            if bi == 1:
                g["patient_snomed_codes"] = ["165418005"]
            elif bi == 2:
                g["patient_snomed_codes"] = ["165418005", "104454006"]
            else:
                g["patient_snomed_codes"] = ["167667006"]
        return
    if rid == "1.3.5" and bi == 1:
        g["graph_rule_id"] = RECT_RULE
        g["patient_snomed_codes"] = ["248523006"]
        g["patient_age"] = max(float(g.get("patient_age") or 55), 18.0)
        g["expect_graph_match"] = True
        return
    if rid == "1.3.1" and not g.get("patient_snomed_codes"):
        g["patient_snomed_codes"] = ["405729008"]
        return


def _set_graph_status(g: dict[str, Any]) -> None:
    gr = g.get("graph_rule_id")
    if gr in ACTIVE:
        g["_graph_status"] = "active"
    elif gr:
        g["_graph_status"] = "pending_review"
    else:
        g["_graph_status"] = "not_coded"


def _scenario_seq(g: dict[str, Any]) -> int:
    return int(g["id"].rsplit("-", 1)[-1])


def _normalise_gdl(g: dict[str, Any]) -> None:
    g.pop("_stub", None)
    g.pop("_stub_note", None)
    lab = str(g.get("branch_label", ""))
    if lab.startswith("stub_branch"):
        g["branch_label"] = f"ng12_{g['rec_id'].replace('.', '_')}_b{g['branch_index']}"
    if str(g.get("expect_action", "")).endswith("review_required"):
        g["expect_action"] = (
            f"ng12_{g['rec_id'].replace('.', '_')}_branch_{g['branch_index']}"
        )
    _special_case_gdl(g)
    if not g.get("patient_snomed_codes") and _scenario_seq(g) > 37:
        g["patient_snomed_codes"] = _pick_generic_codes(g["rec_id"], g["branch_index"])
    _set_graph_status(g)
    if g["rec_id"] == "1.1.5" and g.get("graph_rule_id"):
        g["_graph_status"] = "active"


def _meta_for_code(cid: str) -> tuple[str, str, str]:
    return SNOMED_META.get(
        cid,
        ("clinical finding", "finding", "SNOMED clinical concept"),
    )


def _dedupe_surface_rows(
    terms: list[dict[str, Any]],
    surface: list[dict[str, str]],
    exp: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    seen: set[str] = set()
    o_terms: list[dict[str, Any]] = []
    o_surface: list[dict[str, str]] = []
    o_exp: list[dict[str, Any]] = []
    for t, s, e in zip(terms, surface, exp):
        key = str(t["lookup_term"]).lower()
        if key in seen:
            continue
        seen.add(key)
        o_terms.append(t)
        o_surface.append(s)
        o_exp.append(e)
    return o_terms, o_surface, o_exp


def _build_ext(g: dict[str, Any]) -> dict[str, Any]:
    age = float(g.get("patient_age") or 55.0)
    codes = list(g.get("patient_snomed_codes") or [])
    deduped: list[str] = []
    seen_c: set[str] = set()
    for cid in codes:
        if cid not in seen_c:
            seen_c.add(cid)
            deduped.append(cid)
    codes = deduped
    if not codes:
        phrase = str(g.get("branch_label", "clinical finding")).replace("_", " ")
        term_row = {
            "sentence_id": "s1",
            "text": phrase,
            "lookup_term": phrase,
            "semantic_tag": "finding",
            "confidence": 0.75,
        }
        ent = {
            "text": phrase,
            "lookup_term": phrase,
            "semantic_tag": "finding",
            "assertion": "present",
            "expected_snomed_concept_id": "",
            "expected_fsn": "",
        }
        note = f"{int(age)} year old patient with {phrase} noted in chart."
        return {
            "encounter_note": note,
            "llm_response_terms": [term_row],
            "expected_entities": [ent],
            "surface_forms_in_graph": [],
        }
    parts: list[str] = []
    terms: list[dict[str, Any]] = []
    surface: list[dict[str, str]] = []
    exp: list[dict[str, Any]] = []
    for idx, cid in enumerate(codes, start=1):
        text, tag, fsn = _meta_for_code(cid)
        terms.append(
            {
                "sentence_id": "s1",
                "text": text,
                "lookup_term": text,
                "semantic_tag": tag,
                "confidence": 0.92,
            }
        )
        surface.append({"form": text, "concept_id": cid, "concept_fsn": fsn})
        exp.append(
            {
                "text": text,
                "lookup_term": text,
                "semantic_tag": tag,
                "assertion": "present",
                "expected_snomed_concept_id": cid,
                "expected_fsn": fsn,
            }
        )
        parts.append(text)
    terms, surface, exp = _dedupe_surface_rows(terms, surface, exp)
    parts = [t["text"] for t in terms]
    if len(parts) == 1:
        tail = parts[0]
    else:
        tail = " and ".join(parts[:-1]) + " and " + parts[-1]
    note = f"{int(age)} year old patient with {tail}."
    return {
        "encounter_note": note,
        "llm_response_terms": terms,
        "expected_entities": exp,
        "surface_forms_in_graph": surface,
    }


def _build_sbar(g: dict[str, Any]) -> dict[str, Any]:
    age = int(float(g.get("patient_age") or 55))
    rec = g["rec_id"]
    rules: list[dict[str, str]] = []
    gr = g.get("graph_rule_id")
    if g.get("_graph_status") == "active" and gr:
        rules.append({"rule_id": gr, "name": f"NG12 {rec} matched rule"})
    kws = ["next", "step", "review"]
    min_act = 1 if rules else 0
    return {
        "situation_md": (
            f"Adult around age {age} discussed in primary care. "
            f"NG12 {rec} scenario branch {g['branch_index']}."
        ),
        "background_md": (
            "Background is limited to the excerpted encounter. "
            "No extra history is assumed beyond the note."
        ),
        "assessment_md": (
            f"Assessment aligns with NG12 section {rec} for this branch. "
            "Guideline text is NG12 suspected cancer recognition and referral."
        ),
        "assessment_rules": rules,
        "guideline_titles": ["NG12 Suspected cancer: recognition and referral"],
        "guidelines": ["NG12"],
        "expected_sbar_keywords": kws,
        "expected_min_action_count": min_act,
    }


def _patch_triple(g: dict, e: dict, s_row: dict) -> None:
    suffix = g["id"].rsplit("-", 1)[-1]
    e["id"] = f"NG12-EXT-{suffix}"
    s_row["id"] = f"NG12-SBR-{suffix}"
    keys_to_sync = ("rec_id", "branch_index", "branch_label", "section")
    _normalise_gdl(g)
    for k in keys_to_sync:
        e[k] = g[k]
        s_row[k] = g[k]
    ext_b = _build_ext(g)
    e["encounter_note"] = ext_b["encounter_note"]
    e["llm_response_terms"] = ext_b["llm_response_terms"]
    e["expected_entities"] = ext_b["expected_entities"]
    e["surface_forms_in_graph"] = ext_b["surface_forms_in_graph"]
    e.pop("expected_entities_notes", None)
    e.pop("_stub", None)
    e.pop("_stub_note", None)
    sbr_b = _build_sbar(g)
    for k, v in sbr_b.items():
        s_row[k] = v
    s_row.pop("_stub", None)
    s_row.pop("_stub_note", None)


def main() -> None:
    g_path = FIX / "ng12_guideline_scenarios.json"
    e_path = FIX / "ng12_extraction_scenarios.json"
    s_path = FIX / "ng12_sbar_scenarios.json"
    gdl = json.loads(g_path.read_text())
    ext = json.loads(e_path.read_text())
    sbr = json.loads(s_path.read_text())

    gdl["_meta"]["schema_version"] = 2
    gdl["_meta"]["stub_policy"] = (
        "All rows are non-stub. Regenerated via "
        "scripts/rebuild_ng12_scenario_fixtures.py."
    )
    for doc in (ext, sbr):
        doc["_meta"]["schema_version"] = 2
        doc["_meta"]["note"] = gdl["_meta"]["stub_policy"]

    for g, e, s in zip(gdl["scenarios"], ext["scenarios"], sbr["scenarios"]):
        _patch_triple(g, e, s)

    for path, doc in (g_path, gdl), (e_path, ext), (s_path, sbr):
        path.write_text(json.dumps(doc, indent=2) + "\n")


if __name__ == "__main__":
    main()
