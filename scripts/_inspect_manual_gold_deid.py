"""Inspect de-identified sentence text for the 22 manual gold seed records.

Reads each candidate sentence (one per case), runs deidentify_text(),
prints the de-id text plus a DeIdValidator scan so we can hand-author
entity spans against a known-clean string.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from libs.ner.deid_validator import DeIdValidator
from libs.utils.deidentify import deidentify_text

CASES: list[dict[str, str]] = [
    # POS-01: 4300102074 / breast / mammogram tethered malignant L breast
    {
        "tag": "POS-01-breast-malignant-mammogram",
        "raw": (
            "Mammogram (537..) - b/l - features of tethered malignant L inner breast "
            "mass with associated microcalcifications"
        ),
    },
    # POS-02: 4709023328 / breast / ca breast confirmed
    # Note: Read code X78WM dropped from sentence because it collides with the
    # UK postcode regex in libs/utils/deidentify.py and would be replaced by
    # [POSTCODE]. The SNOMED concept id is preserved in the entity payload.
    {
        "tag": "POS-02-breast-ca-confirmed",
        "raw": "Malignant tumour of breast",
    },
    # POS-03: 6220044894 / gynae / endometrioid carcinoma + TAH BSO
    {
        "tag": "POS-03-gynae-endometrioid",
        "raw": (
            "Major: Endometrioid carcinoma (BB5j2) - Lapar total abdominal "
            "hysterect bilat salpingo-oophorectomy (XaJy8)"
        ),
    },
    # POS-04: 7039607018 / gynae / granulosa cell ovarian tumour + TAH BSO
    {
        "tag": "POS-04-gynae-granulosa",
        "raw": (
            "Lapar total abdominal hysterect bilat salpingo-oophorectomy (XaJy8) - "
            "Granulosa cell ovarian tumour"
        ),
    },
    # NEG-01: Read code X00pE collides with postcode regex; dropped from sentence.
    {
        "tag": "NEG-01-hn-nasendoscopy-normal",
        "raw": "Diagnostic nasendoscopy - normal larynx",
    },
    # NEG-02: 4245896566 / brain / cancer excluded
    {
        "tag": "NEG-02-brain-cancer-excluded",
        "raw": (
            "Triage: Cancer excluded - discharge to GP. "
            "No structural cause for symptoms demonstrated."
        ),
    },
    # NEG-03: 4246627143 / breast / cyst aspirated
    {
        "tag": "NEG-03-breast-cyst-aspirated",
        "raw": (
            "Cyst of breast (XaYQ7) - Aspiration of breast (Xa3qz) - "
            "Mammogram (537..) - M2 - US scan of breast (585C.) - U2"
        ),
    },
    # NEG-04: 4587360686 / colorectal / FOBT normal
    {
        "tag": "NEG-04-colorectal-fobt-normal",
        "raw": (
            "BCSP faecal occult blood test normal (XaPkd) - "
            "Bowel cancer screening programme: faecal occult blood result (XaPVj) - "
            "FOBT Normal. Sent following an overall negative result."
        ),
    },
    # NEG-05: 4621680811 / haematological / haem nil concerns
    {
        "tag": "NEG-05-haem-nil-concerns",
        "raw": "seen by haem - nil concerns raised about malignancy",
    },
    # NEG-06: 4622879921 / bladder / flexible cystoscopy normal
    {
        "tag": "NEG-06-bladder-cystoscopy-normal",
        "raw": "Flexible cystoscopy (Xa7va) - normal",
    },
    # NEG-07: 4644882798 / prostate / PSA 0.13 normal
    {
        "tag": "NEG-07-prostate-psa-normal",
        "raw": (
            "Prostate-specific antigen level (XE25C) 0.13 ng/ml - "
            "Normal. No Further Action."
        ),
    },
    # NEG-08: 4644882798 / urological / balanitis xerotica
    {
        "tag": "NEG-08-urology-balanitis",
        "raw": "Balanitis xerotica obliterans (K276.)",
    },
    # NEG-09: 4822020479 / colorectal / tubular adenoma
    {
        "tag": "NEG-09-colorectal-tubular-adenoma",
        "raw": "Tubular adenoma (Xa98X)",
    },
    # NEG-10: 4842019832 / head_and_neck / reflux + rhinitis
    {
        "tag": "NEG-10-hn-reflux-rhinitis",
        "raw": "Laryngopharyngeal reflux (XaK99) - Chronic rhinitis (XE0Xx)",
    },
    # NEG-11: Read code X00pE collides with postcode regex; dropped.
    {
        "tag": "NEG-11-hn-presbyacusis",
        "raw": "Diagnostic nasendoscopy - Audiometry - Presbyacusis (F5801)",
    },
    # NEG-12: Read code X70nW collides with postcode regex; dropped.
    {
        "tag": "NEG-12-renal-cyst",
        "raw": "Computed tomography of kidneys - Single renal cyst (PD10.)",
    },
    # NEG-13: 6012067550 / breast / USS R normal
    {
        "tag": "NEG-13-breast-uss-normal",
        "raw": "US scan of breast (585C.) - R - normal",
    },
    # NEG-14: 6268086643 / breast / mammo bl normal + USS L normal nodes
    {
        "tag": "NEG-14-breast-mammo-uss-normal",
        "raw": (
            "Mammogram (537..) - b/l - normal - "
            "US scan of breast (585C.) - L - normal nodes to L axilla"
        ),
    },
    # NEG-15: 6519712760 / liver / haemorrhoid + colonoscopy plan
    {
        "tag": "NEG-15-liver-haemorrhoid",
        "raw": (
            "Diagnosis: Haemorrhoids. Plan: Haemorrhoid referral. "
            "Lower GI 2ww referral for colonoscopy."
        ),
    },
    # NEG-16: 7322946243 / breast / viral wart R breast
    {
        "tag": "NEG-16-breast-viral-wart",
        "raw": "Other viral warts (XE0Tg) - R breast",
    },
    # NEG-17: 7343840665 / non_site_specific / 2WW NAD live vaccine
    {
        "tag": "NEG-17-paeds-2ww-nad",
        "raw": (
            "Was seen on 2WW, nad so safe to administer live vaccine."
        ),
    },
]


def main() -> int:
    validator = DeIdValidator()
    out: list[dict] = []
    for case in CASES:
        deid = deidentify_text(case["raw"], ner=False)
        issues = validator.check_record({"text": deid, "entities": []})
        out.append(
            {
                "tag": case["tag"],
                "deid_text": deid,
                "len": len(deid),
                "issues": [i.to_dict() for i in issues],
            }
        )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
