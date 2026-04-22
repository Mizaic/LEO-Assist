"""Author per-site text_channel regex catalogues.

Atlas trace:
  DI: DI-FA3CE229 (RulebookBundle-backed runtime)

Writes clinician-readable regex patterns into each site's champion
rulebook JSON under ``signals.text_channel.regex_catalogue``. The
patterns are UK-English, boundary-anchored, and case-insensitive when
compiled by the text-channel extractor. The patterns deliberately
stay short (<200 chars; validate_no_pii caps free-text length) and
digit-free (validate_no_pii rejects 7+ digit runs).

This script is idempotent: it overwrites the text_channel entry for
each site to the curated catalogue below, leaving every other field
untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULTS_DIR = Path("libs/episode_detector/defaults")

CATALOGUES: dict[str, list[str]] = {
    "breast": [
        r"\bbreast\b",
        r"\b(mammogra|mammo)\w*",
        r"\bbreast (ultrasound|biopsy|mri|imaging|clinic)\b",
        r"\b(nipple (discharge|retraction|inversion))\b",
        r"\b(lump|mass|thickening) in (the )?breast\b",
        r"\b(dcis|ductal carcinoma( in situ)?)\b",
        r"\b(lobular carcinoma|invasive ductal)\b",
        r"\b(core biopsy|fine needle aspirat|fna)\b",
        r"\b(one[- ]stop breast|triple assessment)\b",
        r"\b(oestrogen receptor|er[+-]|her2)\b",
    ],
    "lung": [
        r"\b(lung|pulmonary|pleur)\w*",
        r"\b(bronchoscop|thoracoscop|mediastinoscop)\w*",
        r"\b(ct chest|cxr|chest x[- ]?ray|hrct)\b",
        r"\b(haemoptysis|spiculat\w*|pulmonary nodule)\b",
        r"\b(smoker|ex[- ]smoker|pack year|pack-year)\b",
        r"\b(persistent cough|chronic cough|breathless\w*)\b",
        r"\b(lung cancer|nsclc|sclc|mesothelioma)\b",
        r"\b(chest pain on inspiration|pleuritic)\b",
    ],
    "prostate_urological": [
        r"\b(prostate|prostat\w+)\b",
        r"\b(psa|prostate[- ]specific antigen)\b",
        r"\b(urology|urological|urologist)\b",
        r"\b(trus|transrectal)\b",
        r"\b(mri prostate|mp[- ]?mri)\b",
        r"\b(bph|benign prostatic|lower urinary tract symptoms|luts)\b",
        r"\b(haematuria|blood in (the )?urine)\b",
        r"\b(bladder cancer|renal cell|kidney cancer)\b",
        r"\b(nocturia|hesitancy|poor stream|dribbling)\b",
        r"\b(digital rectal exam|dre)\b",
    ],
    "upper_gi": [
        r"\b(dysphagia|odynophagia)\b",
        r"\b(reflux|heartburn|indigestion|dyspepsia|epigastric)\b",
        r"\b(ogd|gastroscop\w*|endoscop\w*|oesophago\w*)\b",
        r"\b(stomach cancer|gastric cancer|oesophageal cancer)\b",
        r"\b(barrett|barretts|barrett's)\b",
        r"\b(weight loss|appetite loss|anorexi\w*)\b",
        r"\b(helicobacter|h\. pylori|h pylori)\b",
        r"\b(upper gi|upper gastrointestinal)\b",
    ],
    "lower_gi": [
        r"\b(bowel|colorectal|colon|rectal|rectum|anal)\b",
        r"\b(colonoscop\w*|sigmoidoscop\w*|flexi sig)\b",
        r"\b(fit test|faecal immunochemical|fob test)\b",
        r"\b(rectal bleed\w*|pr bleed\w*|haematochezia)\b",
        r"\b(change in bowel habit|cibh|cbh)\b",
        r"\b(bowel cancer|colon cancer|rectal cancer|colorectal cancer)\b",
        r"\b(tenesmus|mucus pr|per rectum)\b",
        r"\b(iron deficiency anaemia|ida)\b",
    ],
    "gynae": [
        r"\b(ovar\w+|uterine|uterus|endometri\w+|cervical|cervix|vulva|vagin\w+)\b",
        r"\b(post[- ]?menopausal bleed\w*|pmb)\b",
        r"\b(inter[- ]?menstrual bleed\w*|imb)\b",
        r"\b(post[- ]?coital bleed\w*|pcb)\b",
        r"\b(ca[- ]?125|risk of malignancy index|rmi)\b",
        r"\b(ovarian (mass|cyst|cancer))\b",
        r"\b(endometrial (thickness|cancer|hyperplasia))\b",
        r"\b(hysteroscop\w*|colposcop\w*)\b",
        r"\b(gynae\w*|gynaecolog\w*)\b",
    ],
    "head_neck": [
        r"\b(oral cavity|tongue|throat|larynx|laryngeal|pharynx|pharyngeal)\b",
        r"\b(hoarseness|persistent hoarse)\b",
        r"\b(neck (lump|mass|swelling))\b",
        r"\b(thyroid (lump|nodule|cancer))\b",
        r"\b(oral ulcer|mouth ulcer|white patch|red patch|leukoplakia)\b",
        r"\b(head and neck|head[- ]?and[- ]?neck)\b",
        r"\b(ent referral|ent clinic)\b",
        r"\b(salivary gland|parotid)\b",
    ],
    "haematology": [
        r"\b(lymphoma|leukaem\w+|myeloma|myelodysplas\w+|mds)\b",
        r"\b(lymph node|lymphadenopathy)\b",
        r"\b(spleen|splenomegal\w*|hepatosplenomegal\w*)\b",
        r"\b(night sweats|weight loss).{0,40}\b(fever|pyrexia)\b",
        r"\b(b[- ]?symptoms)\b",
        r"\b(pancytopen\w*|thrombocytopen\w*|neutropen\w*)\b",
        r"\b(full blood count|fbc).{0,40}(abnormal|low|high)\b",
        r"\b(haematolog\w+)\b",
    ],
    "skin": [
        r"\b(melanoma|melanocytic)\b",
        r"\b(mole|nevus|naevus)\b.{0,30}\b(chang\w+|irregular|asymmetric|bleed\w*)\b",
        r"\b(bcc|basal cell carcinoma)\b",
        r"\b(scc|squamous cell carcinoma)\b",
        r"\b(skin lesion|pigment\w* lesion)\b",
        r"\b(dermoscop\w*|dermoscopy)\b",
        r"\b(2[- ]?week wait skin|skin 2ww)\b",
    ],
    "brain_cns": [
        r"\b(brain tumour|brain tumor|glioma|meningioma|astrocytoma)\b",
        r"\b(cns|central nervous system)\b",
        r"\b(new[- ]?onset seizure|first seizure|focal seizure)\b",
        r"\b(progressive headache|worst headache|new headache)\b",
        r"\b(visual disturbance|diplopia|papilloedema)\b",
        r"\b(focal neurolog\w+|hemiparesis|dysphasia)\b",
        r"\b(ct head|mri head|mri brain|neuro[- ]imaging)\b",
    ],
}


def _target_paths(site: str) -> list[Path]:
    """Return every rulebook JSON for the site (v0 + v1 + any v1_1)."""
    return sorted(DEFAULTS_DIR.glob(f"{site}.v*.json"))


def _patch_file(path: Path, regexes: list[str]) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    current = (
        data.get("signals", {}).get("text_channel", {}).get("regex_catalogue") or []
    )
    if list(current) == regexes:
        return False
    data.setdefault("signals", {}).setdefault("text_channel", {})
    data["signals"]["text_channel"]["regex_catalogue"] = regexes
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return True


def main() -> int:
    touched = 0
    for site, regexes in CATALOGUES.items():
        paths = _target_paths(site)
        if not paths:
            print(f"  {site}: WARNING no rulebook files found")
            continue
        for path in paths:
            if _patch_file(path, regexes):
                print(f"  {site}: updated {path.name}")
                touched += 1
    print(f"Done. Touched {touched} rulebook files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
