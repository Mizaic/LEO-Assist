"""
Phase 10 - Migrate the 9 in-flight local YAMLs to Atlas before cutover.

These were authored by a concurrent dev workstream after the main
reconciliation completed and never landed in Atlas. This script
migrates them in dependency order:

  1. 3 User Needs:  UN-099, UN-100, UN-101
  2. 3 Design Inputs: DI-529 (UN-099), DI-530 (UN-101), DI-531 (UN-100)
  3. 1 Design Output: DO-529 (DI-529)
  4. 1 Verification Test: VT-527 (DI-529, DO-529)
  5. 1 Risk: R-515 (MITIGATES DI-529)
  6. record_verification_run for VT-527 (status=passed, 13/13 in
     execution_history).

Idempotent via design-controls/phase10-inflight-ledger.csv.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DC = ROOT / "design-controls"
sys.path.insert(0, str(ROOT))

from scripts.atlas._mcp_transport import call_tool, initialize  # noqa: E402
from scripts.atlas.product import PRODUCT_ID  # noqa: E402

LEDGER_PATH = DC / "phase10-inflight-ledger.csv"
LEDGER_COLS = [
    "kind",
    "local_id",
    "atlas_dcid",
    "atlas_uuid",
    "decision",
    "note",
    "ts",
]


def load_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    return list(csv.DictReader(LEDGER_PATH.open()))


def append_ledger(rows: list[dict]) -> None:
    new = not LEDGER_PATH.exists()
    with LEDGER_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS, lineterminator="\n")
        if new:
            w.writeheader()
        for r in rows:
            r.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            w.writerow({c: r.get(c, "") for c in LEDGER_COLS})


def find(led: list[dict], local_id: str, kind: str) -> dict | None:
    for r in led:
        if r.get("local_id") == local_id and r.get("kind") == kind:
            return r
    return None


def load_yaml(path: Path) -> dict:
    """Load a single-document YAML that may be a list-of-one or a dict."""
    raw = yaml.safe_load(path.read_text())
    if isinstance(raw, list) and raw:
        return raw[0]
    if isinstance(raw, dict):
        return raw
    raise ValueError(f"Unexpected YAML shape for {path}")


# Stakeholder/persona free-text -> Atlas enum.
STAKEHOLDER_OVERRIDE: dict[str, list[str]] = {
    "UN-LEO-AI-099": ["Clinician", "Quality Engineer", "Quality Manager"],
    "UN-LEO-AI-100": ["Clinician", "Quality Engineer", "Quality Manager"],
    "UN-LEO-AI-101": ["Clinician", "Quality Engineer"],
}


def create_un(local_id: str, ledger: list[dict]) -> str:
    if e := find(ledger, local_id, "user_need"):
        print(f"  {local_id} - already in ledger as {e['atlas_dcid']}")
        return e["atlas_dcid"]
    data = load_yaml(DC / "user-needs" / f"{local_id}.yaml")
    payload = {
        "product_id": PRODUCT_ID,
        "title": data.get("title") or local_id,
        "description": data.get("description") or data.get("title") or local_id,
        "rationale": data.get("rationale") or "",
        "priority": (
            "MUST" if (data.get("priority") or "").lower() == "high" else "SHOULD"
        ),
        "stakeholder_types": STAKEHOLDER_OVERRIDE.get(local_id, ["Quality Engineer"]),
        "acceptance_criteria": data.get("acceptance_criteria") or [],
        "safety_class": "B",
    }
    out = call_tool("create_user_need", payload)
    dcid = out.get("dcId") or out.get("dc_id") or ""
    uid = out.get("id") or ""
    append_ledger(
        [
            {
                "kind": "user_need",
                "local_id": local_id,
                "atlas_dcid": dcid,
                "atlas_uuid": uid,
                "decision": "created",
                "note": data.get("title", "")[:120],
            }
        ]
    )
    print(f"  {local_id} -> {dcid}")
    return dcid


def _ac_strings(criteria) -> list[str]:
    """Flatten a DI machine_spec.acceptance_criteria block into strings."""
    out: list[str] = []
    if isinstance(criteria, list):
        for c in criteria:
            if isinstance(c, str):
                out.append(c.strip())
            elif isinstance(c, dict):
                txt = c.get("spec") or c.get("criterion") or c.get("target") or ""
                if txt:
                    out.append(str(txt).strip())
    return [a for a in out if a]


def create_di(local_id: str, parent_un_dcid: str, ledger: list[dict]) -> str:
    if e := find(ledger, local_id, "design_input"):
        print(f"  {local_id} - already in ledger as {e['atlas_dcid']}")
        return e["atlas_dcid"]
    data = load_yaml(DC / "design-inputs" / f"{local_id}.yaml")
    title = data.get("title")
    if not title:
        for line in (
            (DC / "design-inputs" / f"{local_id}.yaml").read_text().splitlines()[:3]
        ):
            if line.startswith("# --") and " -- " in line:
                title = line.split(" -- ", 2)[-1].strip()
                break
    spec = data.get("machine_spec") or {}
    acs = _ac_strings(spec.get("acceptance_criteria"))
    payload = {
        "product_id": PRODUCT_ID,
        "title": title or local_id,
        "description": (data.get("requirement") or "").strip(),
        "rationale": (data.get("rationale") or "").strip(),
        "input_type": (data.get("type") or "Functional").lower(),
        "acceptance_criteria": acs,
        "safety_class": data.get("safety_class") or "B",
        "verification_method": "test",
    }
    out = call_tool("create_design_input", payload)
    dcid = out.get("dcId") or out.get("dc_id") or ""
    uid = out.get("id") or ""
    append_ledger(
        [
            {
                "kind": "design_input",
                "local_id": local_id,
                "atlas_dcid": dcid,
                "atlas_uuid": uid,
                "decision": "created",
                "note": title or "",
            }
        ]
    )
    if parent_un_dcid:
        call_tool(
            "link_design_controls",
            {
                "source_ids": [parent_un_dcid],
                "target_ids": [dcid],
                "relationship": "HAS_DESIGN_INPUT",
            },
        )
        append_ledger(
            [
                {
                    "kind": "link",
                    "local_id": local_id,
                    "atlas_dcid": dcid,
                    "atlas_uuid": "",
                    "decision": "created",
                    "note": f"UN {parent_un_dcid} -[HAS_DESIGN_INPUT]-> DI {dcid}",
                }
            ]
        )
    print(f"  {local_id} -> {dcid} (parent UN {parent_un_dcid})")
    return dcid


def create_do(local_id: str, parent_di_dcid: str, ledger: list[dict]) -> str:
    if e := find(ledger, local_id, "design_output"):
        print(f"  {local_id} - already in ledger as {e['atlas_dcid']}")
        return e["atlas_dcid"]
    data = load_yaml(DC / "design-outputs" / f"{local_id}.yaml")
    spec = data.get("specification") or {}
    impl = spec.get("implementation") or {}
    artifacts = impl.get("artifacts") or []
    files = [a.get("location") for a in artifacts if a.get("location")]
    acs_raw = spec.get("acceptance_criteria") or []
    acs: list[str] = []
    for a in acs_raw:
        if isinstance(a, dict):
            txt = a.get("criterion") or a.get("target") or ""
            if a.get("target") and a.get("criterion"):
                txt = f"{a['criterion']}: {a['target']}"
            if txt:
                acs.append(txt.strip())
        elif isinstance(a, str):
            acs.append(a.strip())
    payload = {
        "product_id": PRODUCT_ID,
        "title": spec.get("title") or local_id,
        "description": (spec.get("description") or "").strip(),
        "acceptance_criteria": acs,
        "output_type": "software",
        "source_reference": "; ".join(files),
        "software_item": local_id,
        "safety_class": (spec.get("safety_characteristics") or {}).get("safety_class")
        or "B",
    }
    out = call_tool("create_design_output", payload)
    dcid = out.get("dcId") or out.get("dc_id") or ""
    uid = out.get("id") or ""
    append_ledger(
        [
            {
                "kind": "design_output",
                "local_id": local_id,
                "atlas_dcid": dcid,
                "atlas_uuid": uid,
                "decision": "created",
                "note": spec.get("title", "")[:120],
            }
        ]
    )
    if parent_di_dcid:
        call_tool(
            "link_design_controls",
            {
                "source_ids": [dcid],
                "target_ids": [parent_di_dcid],
                "relationship": "IMPLEMENTS",
            },
        )
        append_ledger(
            [
                {
                    "kind": "link",
                    "local_id": local_id,
                    "atlas_dcid": dcid,
                    "atlas_uuid": "",
                    "decision": "created",
                    "note": f"DO {dcid} -[IMPLEMENTS]-> DI {parent_di_dcid}",
                }
            ]
        )
    print(f"  {local_id} -> {dcid}")
    return dcid


def create_vt(
    local_id: str, parent_di_dcid: str, parent_do_dcid: str, ledger: list[dict]
) -> tuple[str, str]:
    if e := find(ledger, local_id, "verification_test"):
        print(f"  {local_id} - already in ledger as {e['atlas_dcid']}")
        return e["atlas_dcid"], e["atlas_uuid"]
    data = load_yaml(DC / "verification-tests" / f"{local_id}.yaml")
    meta = data.get("metadata") or {}
    cases = data.get("test_cases") or []
    acs: list[str] = []
    steps: list[str] = []
    for c in cases:
        for ac in c.get("acceptance_criteria") or []:
            if ac:
                acs.append(str(ac).strip())
        for s in c.get("test_steps") or []:
            if s.get("action"):
                steps.append(f"{c.get('case_id', '')}: {s['action']}".strip(": "))
    payload = {
        "product_id": PRODUCT_ID,
        "title": meta.get("title") or local_id,
        "description": (meta.get("description") or "").strip(),
        "test_type": meta.get("test_level") or "unit",
        "verification_method": "test",
        "acceptance_criteria": acs,
        "protocol_steps": steps,
        "safety_class": meta.get("safety_class") or "B",
    }
    out = call_tool("create_verification_test", payload)
    dcid = out.get("dcId") or out.get("dc_id") or ""
    uid = out.get("id") or ""
    append_ledger(
        [
            {
                "kind": "verification_test",
                "local_id": local_id,
                "atlas_dcid": dcid,
                "atlas_uuid": uid,
                "decision": "created",
                "note": meta.get("title", "")[:120],
            }
        ]
    )
    for rel, tgt, label in [
        ("VERIFIES", parent_di_dcid, "VT-VERIFIES-DI"),
        ("TESTS", parent_do_dcid, "VT-TESTS-DO"),
    ]:
        if not tgt:
            continue
        call_tool(
            "link_design_controls",
            {"source_ids": [dcid], "target_ids": [tgt], "relationship": rel},
        )
        append_ledger(
            [
                {
                    "kind": "link",
                    "local_id": local_id,
                    "atlas_dcid": dcid,
                    "atlas_uuid": "",
                    "decision": "created",
                    "note": f"VT {dcid} -[{rel}]-> {tgt}",
                }
            ]
        )
    print(f"  {local_id} -> {dcid}")
    return dcid, uid


def record_run(local_vt_id: str, vt_uuid: str, ledger: list[dict]) -> None:
    if find(ledger, local_vt_id, "run"):
        return
    data = load_yaml(DC / "verification-tests" / f"{local_vt_id}.yaml")
    history = data.get("execution_history") or []
    if not history:
        return
    last = history[-1]
    notes = str(last.get("notes", "")).strip()
    extra = (
        f"executed_on={last.get('executed_on', '')}; "
        f"pass={last.get('pass_count', '?')}/fail={last.get('fail_count', '?')}; "
        f"local: {local_vt_id} run_id={last.get('run_id', '')}"
    )
    payload = {
        "vt_id": vt_uuid,
        "result": last.get("result", "pass"),
        "executed_by": last.get("executor", "ci-pytest"),
        "notes": (notes + "\n\n" + extra).strip(),
        "environment": "ci",
    }
    try:
        call_tool("record_verification_run", payload)
        append_ledger(
            [
                {
                    "kind": "run",
                    "local_id": local_vt_id,
                    "atlas_dcid": "",
                    "atlas_uuid": vt_uuid,
                    "decision": "recorded",
                    "note": f"{last.get('pass_count', '?')} pass / "
                    f"{last.get('fail_count', '?')} fail",
                }
            ]
        )
        print(f"  recorded run for {local_vt_id}")
    except Exception as e:
        print(f"  record_verification_run failed for {local_vt_id}: {e}")


def create_risk(
    local_id: str, mitigating_di_dcids: list[str], ledger: list[dict]
) -> str:
    if e := find(ledger, local_id, "risk"):
        return e["atlas_dcid"]
    data = load_yaml(DC / "risks" / f"{local_id}.yaml")
    init = data.get("initial_risk_estimate") or {}
    res = data.get("residual_risk_estimate") or {}
    mitigations = data.get("mitigation_measures") or []
    monitoring = data.get("monitoring") or {}
    if mitigations:
        first = mitigations[0]
        mitigation_text = "\n\n".join(
            f"({m.get('control_type', 'control')}): "
            f"{(m.get('description') or '').strip()} "
            f"[implemented_by: {','.join(m.get('implemented_by') or [])}; "
            f"verified_by: {','.join(m.get('verified_by') or [])}]"
            for m in mitigations
        )
        control_type = first.get("control_type") or "design_feature"
        effectiveness = first.get("effectiveness") or "effective"
    else:
        mitigation_text = "None"
        control_type = "design_feature"
        effectiveness = "pending"
    payload = {
        "product_id": PRODUCT_ID,
        "title": data.get("title") or local_id,
        "hazard_description": (
            (data.get("hazard") or {}).get("description") or ""
        ).strip(),
        "hazardous_situation": (data.get("hazardous_situation") or "").strip(),
        "harm_description": ((data.get("harm") or {}).get("description") or "").strip(),
        "harm_severity": (data.get("harm") or {}).get("severity") or "serious",
        "hazard_category": (data.get("hazard") or {}).get("category")
        or "clinical_safety",
        "initial_severity": init.get("severity", 3),
        "initial_probability": init.get("probability", 2),
        "initial_detectability": init.get("detectability", 3),
        "initial_risk_score": init.get("rpn", 18),
        "mitigation_plan_description": mitigation_text,
        "mitigation_control_type": control_type,
        "mitigation_effectiveness": effectiveness,
        "monitoring_plan": (monitoring.get("monitoring_plan") or "").strip(),
        "monitoring_metrics": monitoring.get("metrics") or [],
        "review_frequency": monitoring.get("review_frequency") or "Quarterly",
        "residual_severity": res.get("severity", 2),
        "residual_probability": res.get("probability", 1),
        "residual_detectability": res.get("detectability", 2),
        "residual_risk_score": res.get("rpn", 4),
        "residual_acceptability": res.get("acceptability", "acceptable"),
        "residual_justification": (res.get("justification") or "").strip(),
        "identified_by": (data.get("metadata") or {}).get(
            "identified_by", "Phase 10 in-flight migration"
        ),
        "identified_date": (data.get("metadata") or {}).get(
            "identified_date", time.strftime("%Y-%m-%d")
        ),
        "tags": (data.get("metadata") or {}).get("tags") or [],
        "status": {
            "identified": "Identified",
            "analyzed": "Analyzed",
            "mitigated": "Control Implemented",
            "control implemented": "Control Implemented",
            "residual accepted": "Residual Accepted",
            "closed": "Closed",
            "inactive": "Inactive",
            "obsolete": "Obsolete",
        }.get(
            (data.get("metadata") or {}).get("status", "analyzed").lower(),
            "Analyzed",
        ),
        "safety_class": "B",
    }
    out = call_tool("create_risk", payload)
    dcid = out.get("dcId") or out.get("dc_id") or ""
    uid = out.get("id") or ""
    append_ledger(
        [
            {
                "kind": "risk",
                "local_id": local_id,
                "atlas_dcid": dcid,
                "atlas_uuid": uid,
                "decision": "created",
                "note": (data.get("title") or "")[:120],
            }
        ]
    )
    for di_dcid in mitigating_di_dcids:
        if not di_dcid:
            continue
        call_tool(
            "link_design_controls",
            {
                "source_ids": [di_dcid],
                "target_ids": [dcid],
                "relationship": "MITIGATES",
            },
        )
        append_ledger(
            [
                {
                    "kind": "link",
                    "local_id": local_id,
                    "atlas_dcid": dcid,
                    "atlas_uuid": "",
                    "decision": "created",
                    "note": f"DI {di_dcid} -[MITIGATES]-> R {dcid}",
                }
            ]
        )
    print(f"  {local_id} -> {dcid}")
    return dcid


def main() -> None:
    print("Phase 10 - migrate in-flight YAMLs to Atlas")
    initialize()
    ledger = load_ledger()

    print("\n[1/6] User Needs")
    un = {
        "UN-LEO-AI-099": create_un("UN-LEO-AI-099", ledger),
        "UN-LEO-AI-100": create_un("UN-LEO-AI-100", load_ledger()),
        "UN-LEO-AI-101": create_un("UN-LEO-AI-101", load_ledger()),
    }

    print("\n[2/6] Design Inputs")
    di = {
        "DI-LEO-AI-529": create_di("DI-LEO-AI-529", un["UN-LEO-AI-099"], load_ledger()),
        "DI-LEO-AI-530": create_di("DI-LEO-AI-530", un["UN-LEO-AI-101"], load_ledger()),
        "DI-LEO-AI-531": create_di("DI-LEO-AI-531", un["UN-LEO-AI-100"], load_ledger()),
    }

    print("\n[3/6] Design Outputs")
    do_dcid = create_do("DO-LEO-AI-529", di["DI-LEO-AI-529"], load_ledger())

    print("\n[4/6] Verification Tests")
    vt_dcid, vt_uuid = create_vt(
        "VT-LEO-AI-527", di["DI-LEO-AI-529"], do_dcid, load_ledger()
    )

    print("\n[5/6] Risk")
    create_risk("R-LEO-AI-515", [di["DI-LEO-AI-529"]], load_ledger())

    print("\n[6/6] Record VT execution")
    record_run("VT-LEO-AI-527", vt_uuid, load_ledger())

    print("\nDone.")


if __name__ == "__main__":
    main()
