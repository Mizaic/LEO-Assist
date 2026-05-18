"""Author per-site text_channel regex catalogues.

Atlas trace:
  DI: DI-FA3CE229 (RulebookBundle-backed runtime)
  DI: DI-2C015ADE (AI-eligible context-tier milestones)

Writes clinician-readable regex patterns into each site's champion
rulebook JSON under:

* ``signals.text_channel.regex_catalogue`` -- one flat list of
  site-specific patterns that raise a ``role="diagnosis"`` signal
  when they match the encounter text.
* ``signals.text_channel.context_role_catalogue`` -- dict keyed by
  the seven canonical context-tier milestone tags (see
  ``libs.episode_detector.rulebook.CONTEXT_MILESTONE_TAGS``); each
  entry is a list of regex patterns. Matches raise
  ``role="context_milestone"`` signals that the episode_engine
  fuses with its LLM-emitted context milestones.

All patterns are UK-English, boundary-anchored, and case-insensitive
when compiled by the text-channel extractor. They are kept short
(<200 chars; ``validate_no_pii`` caps free-text length) and digit-free
(``validate_no_pii`` rejects 7+ digit runs).

This script is idempotent: it overwrites the text_channel entries
for each site to the curated catalogues below, leaving every other
field untouched.
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


# ----------------------------------------------------------------------
# Context-tier catalogues (DI-2C015ADE).
# Six of the seven tags use a shared base of site-agnostic UK primary-
# care / secondary-care language; only specialist_diagnostics is
# materially site-specific so it is authored per site below.
# ----------------------------------------------------------------------

SHARED_CONTEXT_CATALOGUES: dict[str, list[str]] = {
    "related_gp_visit": [
        r"\bgp (consultation|appointment|review|visit|surgery)\b",
        r"\bprimary[- ]care (consultation|review|appointment)\b",
        r"\btelephone (consultation|triage|appointment)\b",
        r"\bhome visit\b",
        r"\bsurgery consultation\b",
        r"\b(seen by|reviewed by) gp\b",
        r"\b(locum|duty) gp\b",
    ],
    "primary_care_investigations": [
        r"\b(full blood count|fbc)\b",
        r"\b(u\s?&\s?e|u and e|urea and electrolytes)\b",
        r"\b(lft|liver function tests?)\b",
        r"\b(tft|thyroid function tests?)\b",
        r"\b(crp|c[- ]reactive protein|esr|inflammatory markers)\b",
        r"\b(urinalysis|dipstick|msu|mid[- ]?stream urine)\b",
        r"\b(bloods|blood tests|venepuncture|phlebotomy)\b",
        r"\bplain (film|x[- ]?ray)\b",
        r"\b(ecg|electrocardiogram)\b",
        r"\bgp[- ]requested (imaging|scan|ultrasound)\b",
    ],
    "referral_admin": [
        r"\breferral letter (sent|dictated|typed|drafted)\b",
        r"\breferral (received|accepted|rejected|returned|lost)\b",
        r"\b2[- ]?week[- ]?wait (form|letter|proforma)\b",
        r"\b(did not attend|dna|dnas)\b",
        r"\b(rebook\w+|re[- ]?appointment|reschedul\w+)\b",
        r"\b(waiting list|appointment (confirmed|booked|sent))\b",
        r"\bchoose and book\b",
        r"\b(e[- ]?rs|ebrs|electronic referral)\b",
        r"\bappointment (cancelled|rescheduled)\b",
    ],
    "referral_sent": [
        r"\b(2[- ]?week[- ]?wait|2ww|two[- ]week[- ]?wait)[ \-]?(referral|pathway)\b",
        r"\burgent (suspected cancer )?referral\b",
        r"\bsuspected cancer (pathway|referral|form)\b",
        r"\bfast[- ]?track referral\b",
        r"\breferral (sent|submitted|made|raised|actioned)\b",
        r"\b(usc|urgent suspected cancer)\b",
        r"\b(refer(red)? (to|for)) (2ww|urgent|fast[- ]?track)\b",
    ],
    "related_specialist_visit": [
        r"\bconsultant (review|clinic|follow[- ]?up|appointment)\b",
        r"\b(mdt|multi[- ]?disciplinary)[ ]?(meeting|discussion|review|outcome)\b",
        r"\boutpatient (review|appointment|clinic|follow[- ]?up)\b",
        r"\b(oncology|haematology) (clinic|review|follow[- ]?up)\b",
        r"\b(clinic review|review in clinic|clinic follow[- ]?up)\b",
        r"\b(seen|reviewed) in (the )?(clinic|outpatients?)\b",
    ],
    "related_correspondence": [
        r"\b(clinic letter|discharge summary|discharge letter)\b",
        r"\bmdt (letter|outcome letter|summary|report)\b",
        r"\bconsultant letter (received|sent|copied)\b",
        r"\bletter (received|copied|forwarded) (to|from)\b",
        r"\b(specialist|hospital) correspondence\b",
        r"\b(results (received|back|returned)|report received)\b",
    ],
}


SITE_SPECIFIC_DIAGNOSTICS: dict[str, list[str]] = {
    "breast": [
        r"\b(mammogra|mammo)\w*",
        r"\bbreast (ultrasound|us|biopsy|mri|imaging)\b",
        r"\b(core biopsy|fine needle aspirat|fna)\b",
        r"\b(one[- ]stop (breast )?clinic|triple assessment)\b",
        r"\b(sentinel (lymph )?node|wire[- ]?localisation)\b",
    ],
    "lung": [
        r"\b(bronchoscop|ebus|endobronchial ultrasound)\w*",
        r"\b(mediastinoscop|thoracoscop)\w*",
        r"\b(ct chest|hrct|pet[- ]?ct|ct thorax)\b",
        r"\b(lung biopsy|trans[- ]?thoracic biopsy|ttna)\b",
        r"\b(pleural (aspiration|tap|drain|biopsy))\b",
    ],
    "prostate_urological": [
        r"\b(trus|transrectal ultrasound)\b",
        r"\b(mri prostate|mp[- ]?mri|multiparametric mri)\b",
        r"\b(prostate biopsy|template biopsy|transperineal biopsy)\b",
        r"\b(cystoscop|flexible cystoscop|ureteroscop)\w*",
        r"\b(renal biopsy|nephrostom)\w*",
    ],
    "upper_gi": [
        r"\b(ogd|gastroscop|oesophagogastro)\w*",
        r"\b(eus|endoscopic ultrasound)\b",
        r"\b(oesophageal|gastric|stomach) biopsy\b",
        r"\bbarium (swallow|meal)\b",
        r"\b(ct chest abdomen pelvis|ct cap)\b",
    ],
    "lower_gi": [
        r"\bcolonoscop\w*",
        r"\b(sigmoidoscop|flexi(ble)? sig)\w*",
        r"\b(ct colonograph\w*|ctc|virtual colonoscop\w*)\b",
        r"\bbarium enema\b",
        r"\b(colonic|rectal) biopsy\b",
    ],
    "gynae": [
        r"\bhysteroscop\w*",
        r"\bcolposcop\w*",
        r"\b(endometrial biopsy|pipelle)\b",
        r"\b(tvus|transvaginal ultrasound|pelvic ultrasound)\b",
        r"\b(laparoscop|cone biopsy|lletz)\w*",
    ],
    "head_neck": [
        r"\b(flexible naso[- ]?endoscop|fnes|panendoscop)\w*",
        r"\bneck (ultrasound|us|biopsy)\b",
        r"\bthyroid (ultrasound|us|biopsy|fna)\b",
        r"\b(fna neck|lymph node biopsy|excision biopsy (of )?node)\b",
        r"\b(ct (head and )?neck|mri neck|mri (head and )?neck)\b",
    ],
    "haematology": [
        r"\bbone marrow (aspirate|biopsy|trephine)\b",
        r"\b(lymph node|excision) biopsy\b",
        r"\b(ct chest abdomen pelvis|ct cap|pet[- ]?ct)\b",
        r"\b(flow cytometry|immunophenotyping)\b",
        r"\b(cytogenetics|karyotyp\w+|fish test)\b",
    ],
    "skin": [
        r"\bdermoscop\w*",
        r"\b(punch biopsy|shave biopsy|excision biopsy)\b",
        r"\b(sentinel (lymph )?node biopsy|slnb)\b",
        r"\bwide local excision\b",
        r"\b(mohs|mohs micrographic)\b",
    ],
    "brain_cns": [
        r"\b(ct head|ct brain)\b",
        r"\b(mri head|mri brain|neuro[- ]?imaging)\b",
        r"\b(stereotactic biopsy|craniotomy (and )?biopsy)\b",
        r"\blumbar puncture\b",
        r"\b(eeg|electroencephalogra\w+)\b",
    ],
}


def build_context_catalogue(site: str) -> dict[str, list[str]]:
    """Return the full seven-tag context catalogue for one site.

    Six of the seven tags come from SHARED_CONTEXT_CATALOGUES
    verbatim; the seventh (specialist_diagnostics) is per-site.
    """
    if site not in SITE_SPECIFIC_DIAGNOSTICS:
        raise KeyError(f"no specialist_diagnostics catalogue for site={site!r}")
    catalogue: dict[str, list[str]] = {
        tag: list(patterns) for tag, patterns in SHARED_CONTEXT_CATALOGUES.items()
    }
    catalogue["specialist_diagnostics"] = list(SITE_SPECIFIC_DIAGNOSTICS[site])
    return catalogue


def _target_paths(site: str) -> list[Path]:
    """Return every rulebook JSON for the site (v0 + v1 + any v1_1)."""
    return sorted(DEFAULTS_DIR.glob(f"{site}.v*.json"))


def _patch_file(
    path: Path,
    regexes: list[str],
    context_catalogue: dict[str, list[str]],
) -> bool:
    """Rewrite both text_channel catalogues in the rulebook JSON.

    Returns True when the file content changed on disk.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    current_diag = (
        data.get("signals", {}).get("text_channel", {}).get("regex_catalogue") or []
    )
    current_ctx = (
        data.get("signals", {}).get("text_channel", {}).get("context_role_catalogue")
        or {}
    )
    normalised_ctx = {
        tag: list(current_ctx.get(tag) or []) for tag in context_catalogue
    }
    if list(current_diag) == regexes and normalised_ctx == context_catalogue:
        return False
    data.setdefault("signals", {}).setdefault("text_channel", {})
    data["signals"]["text_channel"]["regex_catalogue"] = regexes
    data["signals"]["text_channel"]["context_role_catalogue"] = context_catalogue
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
        context_catalogue = build_context_catalogue(site)
        for path in paths:
            if _patch_file(path, regexes, context_catalogue):
                print(f"  {site}: updated {path.name}")
                touched += 1
    print(f"Done. Touched {touched} rulebook files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
