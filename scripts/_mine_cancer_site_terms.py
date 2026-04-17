"""Mine cancer-site surface forms from GoldLabel entities and SurfaceForm-MAPS_TO-Concept.

Goal: produce a per-site dictionary of literal surface forms that we can use
to populate `EpisodeOfCare.cancer_type`. The current pipeline classifies
every episode as `non_site_specific` because it relied on coded SNOMED
edges that were deleted.

Output: services/analysis_worker/app/analyzers/cancer_site_terms.py
(machine-generated dictionary that maps a cancer-site key -> list of
case-insensitive surface forms drawn from real annotations).
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402

# Anatomy / disease-stem -> canonical cancer-site key. Order matters: the
# first match in the loop wins, so put more-specific stems before generic.
# NCDA canonical site keys -- aligned with episode_builder/_site_resolution.py
# so the mined dictionary plugs into the existing pipeline cleanly.
SITE_PATTERNS: list[tuple[str, str]] = [
    # Specific subtypes first (longest / most specific match wins)
    ("breast",          r"\bbreast\b|\bmammar\w*|\bductal\b|\blobular\b|\bDCIS\b|\bLCIS\b"),
    ("prostate",        r"\bprostate?\b|\bprostatic\b|\bGleason\b"),
    ("lung",            r"\blung\b|\bpulmonary\b|\bbronch\w*|\bNSCLC\b|\bSCLC\b"),
    ("mesothelioma",    r"\bmesothelioma\b"),
    ("colorectal",      r"\bcolon\w*|\bcolorectal\b|\brect\w*|\bbowel\b|\bcaec\w*|\bsigmoid\b|\bDukes\b|\banus\b|\banal cancer\b"),
    ("melanoma",        r"\bmelanoma\b|\bcutaneous\b|\bdermal\b|\bdermatologic\b|\bBCC\b|\bSCC\b|\bbasal cell\b|\bsquamous cell\b|\bMohs\b|\bskin cancer\b|\bskin lesion\b"),
    ("bladder",         r"\bbladder\b|\burothel\w*|\bureter\w*"),
    ("renal",           r"\brenal\b|\bkidney\b|\bnephron\w*"),
    ("testicular",      r"\btestic\w*|\bscrot\w*|\borchidect\w*"),
    ("cervical",        r"\bcervi\w*"),
    ("endometrial",     r"\buterine\b|\bendometr\w*|\buterus\b"),
    ("ovarian",         r"\bovari\w*|\bfallopian\b"),
    ("vulval",          r"\bvulva\w*|\bvaginal\b"),
    ("oesophageal",     r"\boesoph\w*|\besoph\w*|\bbarrett\w*"),
    ("stomach",         r"\bgastric\b|\bstomach\b"),
    ("pancreatic",      r"\bpancrea\w*|\bWhipple\b"),
    ("liver",           r"\bliver\b|\bhepatic\b|\bhepatocell\w*"),
    ("gallbladder",     r"\bgall ?bladder\b|\bcholangio\w*|\bbiliary\b"),
    ("small_intestine", r"\bsmall intestin\w*|\bsmall bowel\b|\bduoden\w*"),
    ("thyroid",         r"\bthyroid\b|\bparathyroid\b"),
    ("laryngeal",       r"\blarynx\w*|\blaryng\w*|\bvocal cord\b|\bglottis\b"),
    ("oropharyngeal",   r"\bpharyn\w*|\btongue cancer\b|\boral cancer\b|\boropharyn\w*|\bnasopharyn\w*|\bsalivary\b|\btonsil\w*|\bparotid\b|\boral cavit\w*"),
    ("brain",           r"\bbrain\b|\bglio\w*|\bmenin\w*|\bastrocyt\w*|\bschwann\w*|\bspinal cord\b"),
    ("lymphoma",        r"\blymphoma\b|\bHodgkin\b|\bnon[- ]Hodgkin\b"),
    ("leukaemia",       r"\bleuk[ae]mia\b|\bAML\b|\bALL\b|\bCML\b|\bCLL\b|\bMDS\b|\bmyelodysplas\w*|\bmyeloid\b|\bmyeloproliferat\w*"),
    ("myeloma",         r"\bmyeloma\b|\bplasma cell\b"),
    ("sarcoma",         r"\bsarcoma\b|\bGIST\b|\bsoft tissue tumou?r\b"),
    ("childrens_tumour", r"\bWilms\b|\bneuroblastoma\b|\bretinoblastoma\b|\brhabdomyosarcoma\b"),
    # Pathway-level fallbacks (used only if no specific subtype matched first)
    ("head_and_neck",   r"\bhead and neck\b|\bENT cancer\b"),
    ("urological",      r"\burolog\w*"),
    ("gynaecological",  r"\bgynaecolog\w*|\bgynecolog\w*|\bFIGO\b"),
    ("upper_gi",        r"\bupper GI\b|\bupper gastrointestin\w*"),
    ("haematological",  r"\bhaematolog\w*|\bhematolog\w*"),
]

# Words that disqualify a candidate term -- e.g. screening for a benign
# condition that mentions an organ. We still include screening surface
# forms because they help with route detection later, but we exclude pure
# benign findings without a malignancy stem.
MALIGNANCY_STEMS = re.compile(
    r"\b(?:cancer|carcinoma|malignan\w*|tumou?r|neoplas\w*|melanoma|sarcoma|"
    r"lymphoma|leuk[ae]mia|myeloma|adenocarcinoma|DCIS|LCIS|BCC|SCC|"
    r"glioma|astrocytoma|mesothelioma|in.situ|metasta\w*|"
    r"oncolog\w*|chemo\w*|radiotherap\w*|brachytherap\w*|"
    r"prostat\w*|breast|lung|colon|melanoma|skin|cervix|cervi\w*|"
    r"endometr\w*|ovari\w*|bladder|kidney|renal|liver|hepatic|pancrea\w*|"
    r"oesoph\w*|esoph\w*|gastric|stomach|bowel|rectum|larynx|thyroid|brain)\b",
    re.IGNORECASE,
)


def site_key_for(term: str) -> str | None:
    """Return the most-specific site key whose pattern matches the term."""
    for key, pat in SITE_PATTERNS:
        if re.search(pat, term, re.IGNORECASE):
            return key
    return None


def collect() -> dict:
    c = KnowledgeGraphClient()
    try:
        gold_terms: list[tuple[str, str, str]] = []
        rows = c.run(
            """
            MATCH (g:GoldLabel)
            RETURN g.entities_json AS ents, g.label_id AS lid
            """
        )
        for row in rows:
            raw = row["ents"]
            if not raw:
                continue
            try:
                ents = json.loads(raw)
            except (TypeError, ValueError):
                continue
            for e in ents:
                tag = (e.get("semantic_tag") or e.get("label") or "").lower()
                if tag not in ("disorder", "situation", "procedure", "finding"):
                    continue
                term = (e.get("snomed_term") or e.get("text") or "").strip()
                surface = (e.get("text") or "").strip()
                if term:
                    gold_terms.append((term, tag, surface))

        sf_rows = c.run(
            """
            MATCH (s:SurfaceForm)-[:MAPS_TO]->(c:Concept)
            RETURN s.form AS form, c.fsn AS fsn, c.semantic_tag AS tag
            """
        )
        sf_terms: list[tuple[str, str, str]] = []
        for r in sf_rows:
            tag = (r.get("tag") or "").lower()
            if tag not in ("disorder", "situation", "procedure", "finding"):
                continue
            sf_terms.append(
                (str(r.get("fsn") or ""), tag, str(r.get("form") or ""))
            )
    finally:
        c.close()

    return {"gold": gold_terms, "surface": sf_terms}


# Anatomy stems that the SURFACE FORM itself must mention to count.
# Without this, generic findings ("cramps", "amy was not elevated") get
# vacuumed in just because their parent SNOMED concept FSN mentions an
# organ. Aligned 1:1 with the site keys above.
_SURFACE_ANATOMY_STEM: dict[str, str] = {
    "breast":          r"breast|mammar|ductal|lobular|DCIS|LCIS",
    "prostate":        r"prostate?|prostatic|gleason|psa",
    "lung":            r"lung|pulmonary|bronch|NSCLC|SCLC",
    "mesothelioma":    r"mesothelioma|pleural",
    "colorectal":      r"colon|colorectal|rect|bowel|caec|sigmoid|dukes|anus|anal",
    "melanoma":        r"melanoma|skin|cutaneous|dermal|dermatolog|mole|naevus|BCC|SCC|basal cell|squamous cell|mohs",
    "bladder":         r"bladder|urothel|ureter",
    "renal":           r"renal|kidney|nephron",
    "testicular":      r"testic|scrot|orchid",
    "cervical":        r"cervi|smear|cin",
    "endometrial":     r"endometr|uterine|uterus",
    "ovarian":         r"ovari|fallopian",
    "vulval":          r"vulva|vaginal",
    "oesophageal":     r"oesoph|esoph|barrett",
    "stomach":         r"gastric|stomach",
    "pancreatic":      r"pancrea|whipple",
    "liver":           r"liver|hepatic|hepatocell",
    "gallbladder":     r"gall ?bladder|cholangio|biliary",
    "small_intestine": r"small intestin|small bowel|duoden",
    "thyroid":         r"thyroid|parathyroid",
    "laryngeal":       r"laryn|vocal cord|glottis",
    "oropharyngeal":   r"pharyn|tongue|oropharyn|nasopharyn|salivary|tonsil|parotid|oral cancer|oral cavit",
    "brain":           r"brain|glio|menin|astrocyt|schwann|spinal cord|cns",
    "lymphoma":        r"lymphoma|hodgkin",
    "leukaemia":       r"leuk|AML|ALL|CML|CLL|MDS|myelodysplas|myeloid|myeloproliferat",
    "myeloma":         r"myeloma|plasma cell",
    "sarcoma":         r"sarcoma|GIST|soft tissue",
    "childrens_tumour": r"wilms|neuroblastoma|retinoblastoma|rhabdomyosarcoma",
    "head_and_neck":   r"head and neck|ENT cancer",
    "urological":      r"urolog",
    "gynaecological":  r"gynaecolog|gynecolog|FIGO",
    "upper_gi":        r"upper GI|upper gastrointestin",
    "haematological":  r"haematolog|hematolog",
}

_SURFACE_ANATOMY_RX: dict[str, re.Pattern[str]] = {
    k: re.compile(v, re.IGNORECASE) for k, v in _SURFACE_ANATOMY_STEM.items()
}


def categorise(terms: list[tuple[str, str, str]]) -> dict[str, set[str]]:
    """Bucket each (concept_term, semantic_tag, surface_form) by site key.

    Conditions for inclusion:
    1. Concept term contains a malignancy stem
    2. Concept term matches a SITE_PATTERN -> candidate site
    3. Surface form ITSELF mentions the site's anatomy stem (filters noise
       like 'cramps' or 'amy was not elevated' whose parent concept happens
       to contain an organ word)
    """
    out: dict[str, set[str]] = defaultdict(set)
    skipped_no_malignancy = skipped_no_site = skipped_no_anatomy = 0
    for concept_term, _tag, surface in terms:
        if not concept_term:
            continue
        if not MALIGNANCY_STEMS.search(concept_term):
            skipped_no_malignancy += 1
            continue
        site = site_key_for(concept_term)
        if site is None:
            skipped_no_site += 1
            continue
        f = (surface or "").strip().lower()
        if not (3 <= len(f) <= 80):
            continue
        anatomy_rx = _SURFACE_ANATOMY_RX.get(site)
        if anatomy_rx is None or not anatomy_rx.search(f):
            skipped_no_anatomy += 1
            continue
        out[site].add(f)
    print(
        f"  Skipped: no_malignancy={skipped_no_malignancy} "
        f"no_site={skipped_no_site} no_anatomy_in_surface={skipped_no_anatomy}"
    )
    return out


def render_module(
    site_to_forms: dict[str, set[str]], output_path: Path
) -> None:
    header = (
        '"""Cancer-site surface form dictionary.\n\n'
        "AUTO-GENERATED from GoldLabel entities and SurfaceForm-MAPS_TO-Concept\n"
        "edges in the knowledge graph by scripts/_mine_cancer_site_terms.py.\n\n"
        "Each entry maps a canonical cancer-site key to a deduplicated list\n"
        "of lower-case surface forms drawn from real clinical text. Use\n"
        "match_cancer_site(text) to pick the highest-scoring site key for a\n"
        "given block of text.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "import re\n\n"
    )
    body = ["CANCER_SITE_TERMS: dict[str, list[str]] = {"]
    for key in sorted(site_to_forms.keys()):
        forms = sorted(site_to_forms[key])
        body.append(f"    {key!r}: [")
        for f in forms:
            body.append(f"        {f!r},")
        body.append("    ],")
    body.append("}")
    body.append("")
    body.append("# Pre-compiled per-site regexes for fast site detection.")
    body.append("_CANCER_SITE_REGEXES: dict[str, re.Pattern[str]] = {")
    body.append("    key: re.compile(")
    body.append("        r'\\b(?:' + '|'.join(re.escape(f) for f in forms) + r')\\b',")
    body.append("        re.IGNORECASE,")
    body.append("    )")
    body.append("    for key, forms in CANCER_SITE_TERMS.items()")
    body.append("    if forms")
    body.append("}")
    body.append("")
    body.append("def match_cancer_site(text: str) -> tuple[str, int] | None:")
    body.append('    """Return (site_key, hit_count) for the site with the most matches."""')
    body.append("    if not text:")
    body.append("        return None")
    body.append("    best: tuple[str, int] | None = None")
    body.append("    for key, rx in _CANCER_SITE_REGEXES.items():")
    body.append("        n = len(rx.findall(text))")
    body.append("        if n > 0 and (best is None or n > best[1]):")
    body.append("            best = (key, n)")
    body.append("    return best")
    body.append("")
    output_path.write_text(header + "\n".join(body))


def main() -> None:
    data = collect()
    print(f"GoldLabel entities pulled       : {len(data['gold'])}")
    print(f"SurfaceForm-Concept pairs pulled: {len(data['surface'])}")

    combined = data["gold"] + data["surface"]
    site_to_forms = categorise(combined)

    print()
    print("Surface forms per cancer site:")
    print(f"  {'Site':<28} {'Forms':>6}  Sample")
    print(f"  {'-'*28} {'-'*6}  ---")
    for key in sorted(site_to_forms.keys()):
        forms = sorted(site_to_forms[key])
        sample = ", ".join(forms[:3])
        print(f"  {key:<28} {len(forms):>6}  {sample}")

    out = ROOT / "services/analysis_worker/app/analyzers/cancer_site_terms.py"
    render_module(site_to_forms, out)
    print()
    print(f"Wrote {out.relative_to(ROOT)}")
    print(f"Total sites populated: {len(site_to_forms)}")
    print(f"Total unique surface forms: {sum(len(v) for v in site_to_forms.values())}")


if __name__ == "__main__":
    main()
