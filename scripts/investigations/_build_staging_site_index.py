from __future__ import annotations

import json
from pathlib import Path

MAPPINGS_PATH = Path("configs/snomed/snomed_ncda_cancer_types_mapping.json")
OUT_PATH = Path("configs/staging_rules/_site_index.json")


_OVERRIDES: dict[str, str] = {
    # Brain / eye / head-neck
    "372063002": "medulloblastoma",
    "363461003": "carcinoma-of-conjuctiva",
    "255056009": "pharynx",
    # Thoracic
    "363358000": "lung",
    "363432004": "lung",
    "363494000": "thymic-tumours",
    # Haematological
    "363495004": "hodgkins-and-non-hodgkins-lymphoma",
    # Upper GI
    "269457002": "oesophagus",
    "255080008": "stomach",
    "363403002": "small-intestine",
    "93870000": "liver",
    "363415003": "gallbladder",
    "363418001": "pancreas",
    # Lower GI
    "363508008": "colon-and-rectum",
    # Urological
    "93849006": "kidney-tumours",
    "363458004": "renal-pelvis-and-ureter-tumours",
    "93689003": "urinary-bladder-tumours",
    "399068003": "prostate-tumours",
    "363459007": "uretha-tumours",
    "363460002": "uretha-tumours",
    "236740006": "prostate-tumours",
    "363516004": "penis-tumours",
    "363449006": "testis-tumours",
    "188235006": "testis-tumours",
    "363454002": "penis-tumours",
    "363453008": "testis-tumours",
    # Gynaecological
    "363443007": "ovarian-fallopian-tube-and-primary-peritoneal-carcinoma",
    "363444001": "ovarian-fallopian-tube-and-primary-peritoneal-carcinoma",
    "371972005": "uterus---endometrium",
    "363354003": "cervix-uteri",
    "363445000": "ovarian-fallopian-tube-and-primary-peritoneal-carcinoma",
    "609519004": "gestational-trophoblastic-neoplasms",
    "363367000": "vulva",
    # Other
    "254837009": "breast-tumours",
    "371982006": "thyroid-gland",
    "372130007": "malignant-melanoma-of-skin",
    "126598008": "soft-tissue",
    "428281000": "bone",
    "310504009": "hodgkins-and-non-hodgkins-lymphoma",
    "128462008": "hodgkins-and-non-hodgkins-lymphoma",
    "399935008": "breast-tumours",
    "447137006": "breast-tumours",
    "32102001": "breast-tumours",
    "716917000": "breast-tumours",
    "716918005": "breast-tumours",
}


def main() -> None:
    payload = json.loads(MAPPINGS_PATH.read_text(encoding="utf-8"))
    mappings = payload.get("mappings", {})
    out: dict[str, str] = {}
    for item in mappings.values():
        cid = str(item.get("concept_id") or "").strip()
        if not cid:
            continue
        slug = _OVERRIDES.get(cid)
        if slug:
            out[cid] = slug

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_PATH} with {len(out)} mappings")


if __name__ == "__main__":
    main()
