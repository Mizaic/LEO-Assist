"""Print all duplicate surface form mappings and flag wrong winners."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
report = json.loads(
    (ROOT / "scripts" / "investigations" / "surface_form_audit.json").read_text(
        encoding="utf-8"
    )
)

dups = report["duplicates"]
print(f"ALL {len(dups)} DUPLICATE SURFACE FORMS\n")

wrong_winners = []

for d in dups:
    mappings = sorted(
        d["mappings"], key=lambda m: m.get("confidence") or 0, reverse=True
    )
    winner = mappings[0]
    w_fsn = (winner.get("fsn") or "").lower()

    flag = ""
    is_wrong = False
    if "situation" in w_fsn or "history of" in w_fsn:
        flag = " <<< WRONG: situation wins over disorder"
        is_wrong = True
    elif w_fsn.strip() == "mental disorder (disorder)":
        flag = " <<< WRONG: too broad"
        is_wrong = True

    form_repr = repr(d["form"])
    print(form_repr + flag)
    for m in mappings:
        prov = m.get("provenance") or ""
        is_gcl = "[GCL]" if prov == "guideline_config_loader" else "     "
        cid = m.get("concept_id", "?")
        fsn = m.get("fsn", "?")
        conf = m.get("confidence")
        print(f"  {is_gcl} conf={conf}  {cid} | {fsn}")
    print()

    if is_wrong:
        wrong_winners.append(
            {
                "form": d["form"],
                "normalized": d.get("normalized"),
                "wrong_winner": winner,
                "correct": mappings[1] if len(mappings) > 1 else None,
                "all": mappings,
            }
        )

print("=" * 70)
print(f"WRONG WINNERS ({len(wrong_winners)} forms where bad concept wins):")
for w in wrong_winners:
    corr = w.get("correct") or {}
    print(f"  {w['form']!r}")
    print(
        f"    WRONG : {w['wrong_winner'].get('concept_id')} | {w['wrong_winner'].get('fsn')}"
    )
    print(f"    SHOULD: {corr.get('concept_id')} | {corr.get('fsn')}")
