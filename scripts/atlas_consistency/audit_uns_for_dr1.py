"""Audit LEO Core AI User Needs for DR-1 attachment.

Inputs:
  - scripts/atlas_consistency/all_leo_uns_full.json
    (pre-fetched snapshot of all 137 non-obsolete UNs for
    PROD-LEO-CORE-AI-20260415-6AE8A23B [historical product id reference:
    this describes the id the snapshot file was captured under, not the
    live/current product id -- see scripts/atlas/product.py], with
    personas, needs, and embedded traceability_edges for
    HAS_DESIGN_INPUT relationships)
  - candidate UN list from list_design_review_artifact_candidates
  - candidate Risk list from list_design_review_artifact_candidates

Quality gates applied:
  1. Reject if persona is not a user type (e.g. "AI Coding Agent").
  2. Flag if persona is vague ("Other") or empty.
  3. Classify MVP vs post-MVP using the release classifier (R1+R3+R4+R5+R7).

Emits:
  - dr1_un_audit.csv - per-UN decision table
  - dr1_un_audit.md - human-readable report
  - dr1_attach_v2.json - final attach payload for DR-1
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_backlog import classify_release  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.atlas.product import PRODUCT_ID  # noqa: E402

BASE = Path(
    "/Users/robsmith/.cursor/projects/"
    "Users-robsmith-Documents-github-LEO-AI-CORE/agent-tools"
)
UN_CANDIDATES = BASE / "1ac261f3-59f6-4d9f-9bcf-e1cb9359f75d.txt"
RISK_CANDIDATES = BASE / "6fcd2e1c-1a39-4450-a719-1cadbbb9f7cc.txt"

UN_DUMP = Path(__file__).parent / "all_leo_uns_full.json"
OUT_CSV = Path(__file__).parent / "dr1_un_audit.csv"
OUT_MD = Path(__file__).parent / "dr1_un_audit.md"
OUT_JSON = Path(__file__).parent / "dr1_attach_v2.json"

REVIEW_ID = "2a5e98df-96b0-4a37-8c80-4cbaf8b80cb1"

# Personas that are legitimate user roles for a UKCA Class I clinical
# pipeline product SDK. Developer / Engineering Lead are kept because
# LEO Core AI is a regulated SDK - the developer integrating it into a
# downstream product is a bona-fide external user.
LEGITIMATE_PERSONAS = {
    "Clinician",
    "Pathway Supervisor",
    "Clinical Safety Officer",
    "Quality Engineer",
    "Quality Manager",
    "Regulatory Affairs / QA Lead",
    "Knowledge Base Author",
    "Administrator",
    "IT Admin",
    "Developer",
    "Engineering Lead",
}

# Personas that are NOT users of the product.
REJECT_PERSONAS = {
    "AI Coding Agent",  # the software itself, not a user
    None,
    "",
}

# Personas that need review but are borderline.
FLAG_PERSONAS = {
    "Other",
}


def audit_persona(un: dict) -> tuple[str, str]:
    """Return (verdict, reason) where verdict is 'accept'|'reject'|'flag'."""
    persona = un.get("persona")
    if persona in REJECT_PERSONAS:
        return "reject", f"persona '{persona}' is not a user role"
    if persona in FLAG_PERSONAS:
        return "flag", f"persona '{persona}' is ambiguous"
    if persona in LEGITIMATE_PERSONAS:
        return "accept", f"persona '{persona}' OK"
    return "flag", f"persona '{persona}' not on allow-list"


def derive_release_wave(un: dict) -> str:
    """Use the classifier from build_backlog to assign R1/R3/R4/R5/R7
    or post-MVP. Operates on dcId+title+need."""
    dc_id = un.get("dc_id") or ""
    title = un.get("title") or ""
    need = un.get("need") or ""
    return classify_release(dc_id, title, need)


MACHINE_SUBJECTS = {
    "pipeline",
    "worker",
    "scheduler",
    "orchestrator",
    "service",
    "router",
    "module",
    "engine",
    "api",
    "system",
    "server",
    "job",
    "daemon",
    "coding worker pipeline",
    "fastapi router",
    "pipeline worker",
    "pipeline orchestrator",
    "platform scheduler",
    "coding worker",
    "analysis worker",
}

USER_ROLE_KEYWORDS = (
    "clinician",
    "clinical",
    "nurse",
    "doctor",
    "gp",
    "practitioner",
    "pharmacist",
    "radiologist",
    "oncolog",
    "surgeon",
    "coder",
    "auditor",
    "reviewer",
    "developer",
    "engineer",
    "administrator",
    "admin",
    "operator",
    "officer",
    "manager",
    "lead",
    "author",
    "patient",
    "user",
    "staff",
    "team",
    "supervisor",
    "personnel",
    "safety officer",
    "knowledge author",
    "data protection officer",
    "product manager",
    "regulatory",
)


def un_is_user_story(un: dict) -> tuple[bool, str]:
    """Heuristic: a UN should describe a need from a human (or external
    org/role) perspective, not from the perspective of a software
    component.

    Rejects user-stories written as 'As the <machine-subject>, I need X'
    (these are DI/DO content mis-labelled as UN). Accepts everything
    else that mentions a legitimate user role.
    """
    need = (un.get("need") or "").strip()
    if not need:
        return False, "empty 'need' text"

    lowered = need.lower()

    # 1. Detect machine-as-user stories: 'As the <machine>, I need ...'
    #    (This is the classic anti-pattern - DI text mislabelled as UN.)
    for lead in ("as the ", "as a ", "as an "):
        if lowered.startswith(lead):
            rest = lowered[len(lead) :]
            subject = rest.split(",")[0].split(" i need")[0].strip()
            subject_words = subject.split()
            # Check if the subject words overlap with any machine subject
            machine_hit = any(word in MACHINE_SUBJECTS for word in subject_words)
            # If the subject contains a human role word, accept even if
            # it also contains a technical noun (e.g. 'platform operator').
            human_hit = any(role in subject for role in USER_ROLE_KEYWORDS)
            if machine_hit and not human_hit:
                return False, f"machine-centric UN: subject='{subject}'"
            return True, ""

    # 2. Narrative form: 'Clinicians today open five screens...' - accept
    #    if a user-role keyword appears in the first sentence.
    first_sentence = lowered.split(".")[0][:240]
    if any(role in first_sentence for role in USER_ROLE_KEYWORDS):
        return True, ""

    # 3. Fallback: accept if the title surfaces a user role and the
    #    'need' text is narrative. This catches UNs whose body opens
    #    with context rather than the stakeholder.
    title_lower = (un.get("title") or "").lower()
    if any(role in title_lower for role in USER_ROLE_KEYWORDS):
        return True, ""

    return False, "no user role identified in opening sentence or title"


def main() -> None:
    uns = json.loads(UN_DUMP.read_text())
    un_cands = json.loads(UN_CANDIDATES.read_text())["items"]
    risk_cands = json.loads(RISK_CANDIDATES.read_text())["items"]

    un_cand_ids = {c["entity_id"] for c in un_cands}
    risk_cand_ids = {c["entity_id"] for c in risk_cands}

    rows = []
    accepted_mvp_un_uuids = set()
    accepted_mvp_un_dc_ids = set()
    mvp_di_uuids = set()
    mvp_risk_uuids = set()

    # Build a UUID -> UN index from the dump
    un_by_uuid = {u["id"]: u for u in uns}

    for un in uns:
        persona_verdict, persona_reason = audit_persona(un)
        story_ok, story_reason = un_is_user_story(un)
        wave = derive_release_wave(un)
        mvp_in_scope = wave in ("R1", "R3", "R4", "R5", "R7")
        in_candidate_pool = un["id"] in un_cand_ids

        # Final decision: attach to DR-1 iff all gates pass
        decision = "attach"
        reasons = []
        if persona_verdict == "reject":
            decision = "reject"
            reasons.append(persona_reason)
        if not story_ok:
            decision = "reject"
            reasons.append(story_reason)
        if not mvp_in_scope:
            decision = "exclude-post-mvp"
            reasons.append(f"release wave = {wave}")
        if not in_candidate_pool:
            # Only skip attach (it's already reviewed or not a candidate)
            if decision == "attach":
                decision = "skip-not-candidate"
            reasons.append("not in DR-1 candidate pool")
        if persona_verdict == "flag":
            reasons.append(f"FLAG: {persona_reason}")

        row = {
            "dc_id": un["dc_id"],
            "uuid": un["id"],
            "persona": un.get("persona") or "",
            "intended_users": "|".join(un.get("intended_users") or []),
            "status": un.get("status") or "",
            "release_wave": wave,
            "persona_verdict": persona_verdict,
            "user_story_ok": "Y" if story_ok else "N",
            "in_candidate_pool": "Y" if in_candidate_pool else "N",
            "decision": decision,
            "reasons": "; ".join(reasons) if reasons else "",
            "title": un.get("title") or "",
        }
        rows.append(row)

        if decision == "attach":
            accepted_mvp_un_uuids.add(un["id"])
            accepted_mvp_un_dc_ids.add(un["dc_id"])
            # Collect DI UUIDs from embedded traceability_edges
            edges = un.get("traceability_edges") or {}
            for di in edges.get("HAS_DESIGN_INPUT") or []:
                mvp_di_uuids.add(di["dc_id"])

    # For each accepted MVP UN, also pull in risks that MITIGATE its DIs.
    # The traceability_edges on UNs don't include MITIGATES risks directly
    # (risks attach via DI -> MITIGATES -> Risk), so we need to look them
    # up in the traceability matrix file. For now we use the candidate
    # pool as an anchor - if a risk is a DR-1 candidate and its linked
    # DI sits under an accepted UN, attach it.
    matrix_file = BASE / "6b57d34c-b6ac-4b8b-88d3-6ac09982d3f3.txt"
    try:
        mx = json.loads(matrix_file.read_text())
    except FileNotFoundError:
        mx = {"nodes": [], "links": []}

    mx_nodes = {n["id"]: n for n in mx.get("nodes", [])}
    links = mx.get("links", [])

    # Build DI -> risks (MITIGATES src=DI, tgt=Risk)
    risk_by_di = {}
    for ln in links:
        if ln.get("relationship") == "MITIGATES":
            risk_by_di.setdefault(ln["source"], []).append(ln["target"])

    for di_uuid in list(mvp_di_uuids):
        for risk_uuid in risk_by_di.get(di_uuid, []):
            if risk_uuid in risk_cand_ids:
                mvp_risk_uuids.add(risk_uuid)

    # Also include risks directly linked to accepted UNs (HAS_RISK if exists)
    for ln in links:
        if (
            ln.get("relationship") == "HAS_RISK"
            and ln["source"] in accepted_mvp_un_uuids
        ):
            if ln["target"] in risk_cand_ids:
                mvp_risk_uuids.add(ln["target"])

    # Emit CSV
    with OUT_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # Emit attach payload
    payload = {
        "review_id": REVIEW_ID,
        "product_id": PRODUCT_ID,
        "user_needs": sorted(accepted_mvp_un_uuids),
        "design_inputs": sorted(mvp_di_uuids),
        "risks": sorted(mvp_risk_uuids),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))

    # Emit summary MD
    from collections import Counter

    decision_counts = Counter(r["decision"] for r in rows)
    persona_counts = Counter(r["persona"] for r in rows)
    wave_counts = Counter(r["release_wave"] for r in rows)

    lines = [
        "# DR-1 UN Audit Report",
        "",
        f"- Source UN snapshot: {UN_DUMP.name} ({len(rows)} UNs)",
        f"- Candidate pool size (server): {len(un_cand_ids)} UNs, "
        f"{len(risk_cand_ids)} Risks",
        "",
        "## Decision summary",
        "",
    ]
    for k in ("attach", "exclude-post-mvp", "skip-not-candidate", "reject"):
        lines.append(f"- **{k}**: {decision_counts.get(k, 0)}")

    lines += [
        "",
        "## Release-wave distribution (all UNs)",
        "",
    ]
    for wave, n in sorted(wave_counts.items()):
        lines.append(f"- {wave}: {n}")

    lines += [
        "",
        "## Persona distribution (all UNs)",
        "",
    ]
    for p, n in persona_counts.most_common():
        lines.append(f"- {p or '(empty)'}: {n}")

    # Rejected UNs
    rejected = [r for r in rows if r["decision"] == "reject"]
    lines += [
        "",
        "## Rejected UNs (not attached to DR-1)",
        "",
    ]
    for r in rejected:
        lines.append(
            f"- `{r['dc_id']}` persona=`{r['persona']}` "
            f"wave=`{r['release_wave']}` :: {r['title'][:100]}"
        )
        lines.append(f"  - reason: {r['reasons']}")

    # Flag list (attach but with warnings)
    flagged = [r for r in rows if "FLAG" in r["reasons"]]
    if flagged:
        lines += [
            "",
            "## Flagged UNs (still attached, but need review)",
            "",
        ]
        for r in flagged:
            lines.append(
                f"- `{r['dc_id']}` persona=`{r['persona']}` "
                f"wave=`{r['release_wave']}` :: {r['title'][:100]}"
            )
            lines.append(f"  - reason: {r['reasons']}")

    # Final attach list
    lines += [
        "",
        "## Final DR-1 attach payload",
        "",
        f"- UNs:            {len(accepted_mvp_un_uuids)}",
        f"- Design Inputs:  {len(mvp_di_uuids)}",
        f"- Risks:          {len(mvp_risk_uuids)}",
        "",
    ]

    # Accepted UN list grouped by wave
    lines += ["## Accepted MVP UNs (attach list)", ""]
    for wave in ("R1", "R3", "R4", "R5", "R7"):
        wave_rows = [
            r for r in rows if r["decision"] == "attach" and r["release_wave"] == wave
        ]
        if wave_rows:
            lines.append(f"### {wave} ({len(wave_rows)})")
            lines.append("")
            for r in wave_rows:
                lines.append(f"- `{r['dc_id']}` ({r['persona']}) :: {r['title'][:100]}")
            lines.append("")

    OUT_MD.write_text("\n".join(lines))

    print("=" * 80)
    print(f"UNs audited:  {len(rows)}")
    for k in ("attach", "exclude-post-mvp", "skip-not-candidate", "reject"):
        print(f"  {k:22s} {decision_counts.get(k, 0)}")
    print()
    print(f"Attach payload written: {OUT_JSON}")
    print(f"  user_needs:    {len(payload['user_needs'])}")
    print(f"  design_inputs: {len(payload['design_inputs'])}")
    print(f"  risks:         {len(payload['risks'])}")
    print()
    print(f"Audit report:  {OUT_MD}")
    print(f"Audit CSV:     {OUT_CSV}")


if __name__ == "__main__":
    main()
