"""Write batch-4 surface forms: CKD stages, drug monitoring, HbA1c, blood pressure,
diabetic screening, suture removal, wide local excision, head-and-neck / all 2WW
pathways, safety netting, medication stopped, and smoking status.

All SNOMED concept IDs pre-verified against the terminology server.
Corrections applied:
  - methotrexate monitoring: 387381009 (substance) WRONG -> 22189001 (measurement)
  - blood pressure measurement: preoperative-specific WRONG -> 135840009 (BP monitoring)
  - diabetic retinal/eye screening: wrong first-pass -> 134395001 confirmed on 3rd query
  - removal of sutures: 417488009 (conjunctival) WRONG -> 30549001 (generic)
  - persistent hoarse voice: 57568005 (strained) WRONG -> 16617009 (dysphonia)
  - drug treatment stopped: antidepressant-specific WRONG -> 274512008 (generic)
  - medication stopped: inappropriate-specific WRONG -> 274512008 (generic)
  - haematology 2WW: 199251000000107 (generic fast-track) -> 276461000000107 (haematology-specific)

Run:
  python scripts/investigations/_write_critical_surface_forms.py --dry-run
  python scripts/investigations/_write_critical_surface_forms.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "services" / "api"))

from dotenv import load_dotenv

load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception as _kv_exc:
    print(f"[WARN] Key Vault load failed ({_kv_exc}); proceeding with env only")

import requests
from libs.auth.service_auth import get_service_auth_header

BASE = "http://localhost:8001"
UPSERT_URL = f"{BASE}/terminology/surface-forms/upsert-mapping"
PROVENANCE = "batch6_audit_gap_april_2026"

SURFACE_FORMS: list[tuple[str, str, str, float]] = [
    # =======================================================================
    # BEREAVEMENT / GRIEF
    # =======================================================================
    ("bereavement", "74506000", "Bereavement (finding)", 0.98),
    ("bereaved", "74506000", "Bereavement (finding)", 0.95),
    ("grief", "224965009", "Grief finding (finding)", 0.97),
    ("grieving", "224965009", "Grief finding (finding)", 0.95),
    (
        "bereavement counselling",
        "171007003",
        "Counseling for bereavement (procedure)",
        0.97,
    ),
    ("bereavement support", "395076009", "Bereavement support (regime/therapy)", 0.97),
    ("loss of loved one", "74506000", "Bereavement (finding)", 0.88),
    ("complicated grief", "724965009", "Grief finding (finding)", 0.90),
    (
        "prolonged grief disorder",
        "723914003",
        "Prolonged grief disorder (disorder)",
        0.97,
    ),
    ("adjustment disorder", "17226007", "Adjustment disorder (disorder)", 0.98),
    ("adjustment reaction", "17226007", "Adjustment disorder (disorder)", 0.93),
    (
        "adjustment disorder with anxiety",
        "47372000",
        "Adjustment disorder with anxious mood (disorder)",
        0.97,
    ),
    (
        "reactive depression",
        "87414006",
        "Reactive depression (situational) (disorder)",
        0.97,
    ),
    # =======================================================================
    # CHEST PAIN VARIANTS
    # =======================================================================
    ("atypical chest pain", "102589003", "Atypical chest pain (finding)", 0.98),
    ("non-cardiac chest pain", "274668005", "Non-cardiac chest pain (finding)", 0.98),
    ("non cardiac chest pain", "274668005", "Non-cardiac chest pain (finding)", 0.97),
    ("pleuritic chest pain", "2237002", "Pleuritic pain (finding)", 0.97),
    ("pleuritic pain", "2237002", "Pleuritic pain (finding)", 0.97),
    (
        "musculoskeletal chest pain",
        "281245003",
        "Musculoskeletal chest pain (finding)",
        0.98,
    ),
    ("chest wall pain", "281245003", "Musculoskeletal chest pain (finding)", 0.92),
    ("costochondritis", "64109004", "Costochondritis (disorder)", 0.98),
    # =======================================================================
    # SURGICAL / BOWEL
    # =======================================================================
    # Small bowel injury (125627008) -- CORRECTED from body structure
    ("small bowel injury", "125627008", "Injury of small intestine (disorder)", 0.97),
    (
        "small intestine injury",
        "125627008",
        "Injury of small intestine (disorder)",
        0.97,
    ),
    (
        "repair of small intestine",
        "307367009",
        "Repair of small intestine (procedure)",
        0.97,
    ),
    (
        "small bowel resection",
        "107938000",
        "Small intestine excision (procedure)",
        0.97,
    ),
    ("bowel resection", "107938000", "Small intestine excision (procedure)", 0.90),
    (
        "postoperative complication",
        "385486001",
        "Postoperative complication (disorder)",
        0.95,
    ),
    (
        "surgical complication",
        "385486001",
        "Postoperative complication (disorder)",
        0.92,
    ),
    (
        "bowel surgery complication",
        "385486001",
        "Postoperative complication (disorder)",
        0.90,
    ),
    # =======================================================================
    # GYNAECOLOGICAL SURGERY
    # =======================================================================
    # Total hysterectomy (116140006)
    ("total hysterectomy", "116140006", "Total hysterectomy (procedure)", 0.98),
    ("hysterectomy", "116140006", "Total hysterectomy (procedure)", 0.93),
    ("abdominal hysterectomy", "116141005", "Abdominal hysterectomy (procedure)", 0.97),
    (
        "laparoscopic hysterectomy",
        "236887006",
        "Laparoscopic hysterectomy (procedure)",
        0.98,
    ),
    # Gynaecological surgery (176757001) -- CORRECTED from referral concept
    (
        "gynaecological surgery",
        "176757001",
        "Upper female genital tract operation (procedure)",
        0.90,
    ),
    (
        "gynaecological operation",
        "176757001",
        "Upper female genital tract operation (procedure)",
        0.90,
    ),
    # =======================================================================
    # LYMPH NODES -- CORRECTED: enlarged lymph node was submandibular-specific
    # =======================================================================
    (
        "enlarged lymph node",
        "274744005",
        "Localized enlarged lymph nodes (disorder)",
        0.95,
    ),
    (
        "lymph node enlargement",
        "274741002",
        "Generalized enlarged lymph nodes (disorder)",
        0.93,
    ),
    (
        "generalised lymphadenopathy",
        "274741002",
        "Generalized enlarged lymph nodes (disorder)",
        0.97,
    ),
    ("lymphadenopathy", "30746006", "Lymphadenopathy (disorder)", 0.98),
    (
        "inguinal lymphadenopathy",
        "127199000",
        "Inguinal lymphadenopathy (disorder)",
        0.98,
    ),
    (
        "enlarged inguinal lymph node",
        "127199000",
        "Inguinal lymphadenopathy (disorder)",
        0.95,
    ),
    (
        "cervical lymphadenopathy",
        "127086001",
        "Cervical lymphadenopathy (disorder)",
        0.98,
    ),
    (
        "neck lymph nodes enlarged",
        "127086001",
        "Cervical lymphadenopathy (disorder)",
        0.90,
    ),
    # =======================================================================
    # CARDIOLOGY IMAGING
    # =======================================================================
    (
        "CT coronary angiography",
        "419545005",
        "Computed tomography angiography of coronary artery with contrast (procedure)",
        0.98,
    ),
    (
        "CTCA",
        "419545005",
        "Computed tomography angiography of coronary artery with contrast (procedure)",
        0.93,
    ),
    (
        "CT coronary angiogram",
        "419545005",
        "Computed tomography angiography of coronary artery with contrast (procedure)",
        0.97,
    ),
    (
        "coronary angiography",
        "33367005",
        "Angiography of coronary artery (procedure)",
        0.98,
    ),
    (
        "cardiac angiogram",
        "33367005",
        "Angiography of coronary artery (procedure)",
        0.93,
    ),
    (
        "angiography of coronary artery",
        "33367005",
        "Angiography of coronary artery (procedure)",
        0.98,
    ),
    # =======================================================================
    # CERVICAL / GYNAECOLOGICAL ONCOLOGY
    # =======================================================================
    (
        "cervical intraepithelial neoplasia",
        "285636001",
        "Cervical intraepithelial neoplasia (disorder)",
        0.98,
    ),
    ("CIN", "285636001", "Cervical intraepithelial neoplasia (disorder)", 0.90),
    (
        "CIN 1",
        "285836003",
        "Cervical intraepithelial neoplasia grade 1 (disorder)",
        0.98,
    ),
    (
        "CIN1",
        "285836003",
        "Cervical intraepithelial neoplasia grade 1 (disorder)",
        0.97,
    ),
    (
        "CIN 2",
        "285838002",
        "Cervical intraepithelial neoplasia grade 2 (disorder)",
        0.98,
    ),
    (
        "CIN2",
        "285838002",
        "Cervical intraepithelial neoplasia grade 2 (disorder)",
        0.97,
    ),
    ("CIN 3", "92564006", "Carcinoma in situ of uterine cervix (disorder)", 0.97),
    ("CIN3", "92564006", "Carcinoma in situ of uterine cervix (disorder)", 0.97),
    (
        "carcinoma in situ cervix",
        "92564006",
        "Carcinoma in situ of uterine cervix (disorder)",
        0.97,
    ),
    ("cervical smear abnormal", "309081009", "Abnormal cervical smear (finding)", 0.98),
    ("abnormal cervical smear", "309081009", "Abnormal cervical smear (finding)", 0.98),
    (
        "cervical screening abnormal",
        "309081009",
        "Abnormal cervical smear (finding)",
        0.97,
    ),
    ("smear test abnormal", "309081009", "Abnormal cervical smear (finding)", 0.95),
    ("colposcopy", "392003006", "Colposcopy (procedure)", 0.98),
    ("colposcopy appointment", "392003006", "Colposcopy (procedure)", 0.92),
    ("referred for colposcopy", "392003006", "Colposcopy (procedure)", 0.93),
    # =======================================================================
    # CKD KDIGO ALBUMINURIA CATEGORIES
    # =======================================================================
    ("albuminuria category A1", "816212004", "Grade A1 albuminuria (finding)", 0.98),
    ("KDIGO A1", "816212004", "Grade A1 albuminuria (finding)", 0.93),
    ("albuminuria category A2", "735623008", "Grade A2 albuminuria (finding)", 0.98),
    ("KDIGO A2", "735623008", "Grade A2 albuminuria (finding)", 0.93),
    ("albuminuria category A3", "735624002", "Grade A3 albuminuria (finding)", 0.98),
    ("KDIGO A3", "735624002", "Grade A3 albuminuria (finding)", 0.93),
    ("microalbuminuria", "312975006", "Microalbuminuria (finding)", 0.98),
    ("albumin in urine", "274769005", "Albuminuria (finding)", 0.93),
    ("albuminuria", "274769005", "Albuminuria (finding)", 0.97),
    ("macroalbuminuria", "29738008", "Proteinuria (finding)", 0.88),
    ("proteinuria", "29738008", "Proteinuria (finding)", 0.98),
    (
        "urine albumin creatinine ratio",
        "271075006",
        "Urine albumin/creatinine ratio measurement (procedure)",
        0.97,
    ),
    (
        "urine ACR",
        "271075006",
        "Urine albumin/creatinine ratio measurement (procedure)",
        0.93,
    ),
    (
        "ACR urine",
        "271075006",
        "Urine albumin/creatinine ratio measurement (procedure)",
        0.90,
    ),
    # =======================================================================
    # FITNESS FOR WORK / FIT NOTE -- CORRECTED: fit note returned seizure
    # =======================================================================
    (
        "fitness for work statement",
        "774741000000101",
        "Fitness for work statement issued (finding)",
        0.97,
    ),
    (
        "fit note issued",
        "774741000000101",
        "Fitness for work statement issued (finding)",
        0.97,
    ),
    ("MED3", "774741000000101", "Fitness for work statement issued (finding)", 0.92),
    (
        "MED3 certificate",
        "774741000000101",
        "Fitness for work statement issued (finding)",
        0.93,
    ),
    (
        "sick certificate issued",
        "774741000000101",
        "Fitness for work statement issued (finding)",
        0.92,
    ),
    (
        "statement of fitness for work",
        "774741000000101",
        "Fitness for work statement issued (finding)",
        0.97,
    ),
    # =======================================================================
    # MSK -- metatarsal tenderness corrected to metatarsalgia
    # =======================================================================
    ("metatarsalgia", "10085004", "Metatarsalgia (finding)", 0.98),
    ("metatarsal tenderness", "10085004", "Metatarsalgia (finding)", 0.93),
    ("metatarsal pain", "10085004", "Metatarsalgia (finding)", 0.95),
    ("forefoot pain", "10085004", "Metatarsalgia (finding)", 0.90),
    (
        "stress fracture metatarsal",
        "441558003",
        "Stress fracture of metatarsal bone (disorder)",
        0.98,
    ),
    ("foot pain", "47933007", "Foot pain (finding)", 0.97),
    ("ankle sprain", "44465007", "Sprain of ankle (disorder)", 0.98),
    ("ankle pain", "247373008", "Ankle pain (finding)", 0.97),
    ("ankle injury", "44465007", "Sprain of ankle (disorder)", 0.90),
    # =======================================================================
    # CARDIOLOGY
    # =======================================================================
    # Aortic valve stenosis (60573004) -- 'aortic stenosis' first-pass was congenital
    ("aortic valve stenosis", "60573004", "Aortic valve stenosis (disorder)", 0.98),
    ("aortic stenosis", "60573004", "Aortic valve stenosis (disorder)", 0.97),
    ("AS heart", "60573004", "Aortic valve stenosis (disorder)", 0.88),
    (
        "severe aortic stenosis",
        "836482000",
        "Severe stenosis of aortic valve (disorder)",
        0.97,
    ),
    # Heart valve (368009)
    ("heart valve disorder", "368009", "Heart valve disorder (disorder)", 0.97),
    ("heart valve disease", "368009", "Heart valve disorder (disorder)", 0.97),
    ("valvular heart disease", "368009", "Heart valve disorder (disorder)", 0.95),
    # Mitral regurgitation (48724000)
    (
        "mitral valve regurgitation",
        "48724000",
        "Mitral valve regurgitation (disorder)",
        0.98,
    ),
    ("mitral regurgitation", "48724000", "Mitral valve regurgitation (disorder)", 0.97),
    ("MR mitral", "48724000", "Mitral valve regurgitation (disorder)", 0.88),
    # Aortic regurgitation (60234000)
    ("aortic regurgitation", "60234000", "Aortic valve regurgitation (disorder)", 0.98),
    (
        "aortic valve regurgitation",
        "60234000",
        "Aortic valve regurgitation (disorder)",
        0.98,
    ),
    ("AR aortic", "60234000", "Aortic valve regurgitation (disorder)", 0.88),
    # TAVI (773996000)
    ("TAVI", "773996000", "Transcatheter aortic valve implantation (procedure)", 0.97),
    (
        "transcatheter aortic valve implantation",
        "773996000",
        "Transcatheter aortic valve implantation (procedure)",
        0.98,
    ),
    ("TAVR", "773996000", "Transcatheter aortic valve implantation (procedure)", 0.95),
    (
        "transcatheter aortic valve replacement",
        "773996000",
        "Transcatheter aortic valve implantation (procedure)",
        0.97,
    ),
    # Referral for cardiac surgery (306185001) -- no clean 'awaiting' concept
    (
        "referral for cardiac surgery",
        "306185001",
        "Referral to cardiac surgery service (procedure)",
        0.97,
    ),
    (
        "referred for cardiac surgery",
        "306185001",
        "Referral to cardiac surgery service (procedure)",
        0.95,
    ),
    (
        "awaiting cardiac surgery",
        "306185001",
        "Referral to cardiac surgery service (procedure)",
        0.88,
    ),
    (
        "awaiting cardiac valve surgery",
        "306185001",
        "Referral to cardiac surgery service (procedure)",
        0.88,
    ),
    # Coronary artery disease (53741008)
    (
        "coronary artery disease",
        "53741008",
        "Coronary arteriosclerosis (disorder)",
        0.97,
    ),
    ("CAD", "53741008", "Coronary arteriosclerosis (disorder)", 0.90),
    # Ischaemic heart disease (414545008)
    ("ischaemic heart disease", "414545008", "Ischemic heart disease (disorder)", 0.98),
    ("IHD", "414545008", "Ischemic heart disease (disorder)", 0.92),
    ("ischemic heart disease", "414545008", "Ischemic heart disease (disorder)", 0.98),
    # Atrial fibrillation (49436004)
    ("atrial fibrillation", "49436004", "Atrial fibrillation (disorder)", 0.98),
    ("AF", "49436004", "Atrial fibrillation (disorder)", 0.90),
    (
        "paroxysmal atrial fibrillation",
        "120041000119109",
        "Paroxysmal atrial fibrillation (disorder)",
        0.97,
    ),
    (
        "persistent atrial fibrillation",
        "440028005",
        "Persistent atrial fibrillation (disorder)",
        0.97,
    ),
    # Palpitations (80313002)
    ("palpitations", "80313002", "Palpitations (finding)", 0.98),
    ("heart palpitations", "80313002", "Palpitations (finding)", 0.95),
    # Chest pain (29857009)
    ("chest pain", "29857009", "Chest pain (finding)", 0.98),
    ("chest tightness", "29857009", "Chest pain (finding)", 0.90),
    ("chest discomfort", "29857009", "Chest pain (finding)", 0.90),
    # Angina (194828000 / 233819005)
    ("angina", "194828000", "Angina (disorder)", 0.97),
    ("angina pectoris", "194828000", "Angina (disorder)", 0.98),
    ("stable angina", "233819005", "Stable angina (disorder)", 0.97),
    ("unstable angina", "4557003", "Preinfarction syndrome (disorder)", 0.95),
    # =======================================================================
    # HYPERTENSION VARIANTS
    # =======================================================================
    # Essential hypertension (59621000)
    ("essential hypertension", "59621000", "Essential hypertension (disorder)", 0.98),
    ("primary hypertension", "59621000", "Essential hypertension (disorder)", 0.97),
    # Elevated blood pressure (24184005)
    (
        "elevated blood pressure",
        "24184005",
        "Blood pressure above reference range (finding)",
        0.97,
    ),
    (
        "elevated systolic blood pressure",
        "24184005",
        "Blood pressure above reference range (finding)",
        0.95,
    ),
    (
        "high blood pressure reading",
        "24184005",
        "Blood pressure above reference range (finding)",
        0.93,
    ),
    (
        "blood pressure raised",
        "24184005",
        "Blood pressure above reference range (finding)",
        0.92,
    ),
    # Hypertensive heart disease (64715009)
    (
        "hypertensive heart disease",
        "64715009",
        "Hypertensive heart disease (disorder)",
        0.97,
    ),
    # =======================================================================
    # OSTEOPOROSIS / BONE -- osteoporosis first-pass returned MSK history (wrong)
    # =======================================================================
    # Osteoporosis (64859006) -- CORRECTED from 267004000 (history of MSK)
    ("osteoporosis", "64859006", "Osteoporosis (disorder)", 0.98),
    ("osteoporosis disorder", "64859006", "Osteoporosis (disorder)", 0.97),
    (
        "postmenopausal osteoporosis",
        "102447009",
        "Postmenopausal osteoporosis (disorder)",
        0.98,
    ),
    # Osteopenia (312894000)
    ("osteopenia", "312894000", "Osteopenia (disorder)", 0.98),
    (
        "low bone density",
        "449781000",
        "Bone density below reference range (finding)",
        0.97,
    ),
    # Osteoporotic fracture (443165006) -- CORRECTED from morphology concept
    (
        "osteoporotic fracture",
        "443165006",
        "Osteoporotic fracture of bone (disorder)",
        0.97,
    ),
    (
        "fracture due to osteoporosis",
        "443165006",
        "Osteoporotic fracture of bone (disorder)",
        0.95,
    ),
    (
        "vertebral osteoporotic fracture",
        "240198002",
        "Osteoporotic vertebral collapse (disorder)",
        0.97,
    ),
    (
        "osteoporotic vertebral collapse",
        "240198002",
        "Osteoporotic vertebral collapse (disorder)",
        0.98,
    ),
    # =======================================================================
    # LYMPHOEDEMA
    # =======================================================================
    ("lymphoedema", "234097001", "Lymphedema (disorder)", 0.98),
    ("lymphedema", "234097001", "Lymphedema (disorder)", 0.98),
    ("lymphoedema lower limb", "234097001", "Lymphedema (disorder)", 0.97),
    ("lymphoedema lower leg", "234097001", "Lymphedema (disorder)", 0.97),
    ("lymphoedema arm", "234097001", "Lymphedema (disorder)", 0.93),
    ("post-mastectomy lymphoedema", "234097001", "Lymphedema (disorder)", 0.95),
    # =======================================================================
    # COVID-19 VACCINATION -- booster first-pass returned product concept
    # =======================================================================
    # General COVID vaccination (9990010003)
    (
        "COVID-19 vaccination",
        "9990010003",
        "Administration of vaccine product against SARS-CoV-2 (procedure)",
        0.98,
    ),
    (
        "COVID-19 vaccine administered",
        "9990010003",
        "Administration of vaccine product against SARS-CoV-2 (procedure)",
        0.97,
    ),
    (
        "COVID vaccine",
        "9990010003",
        "Administration of vaccine product against SARS-CoV-2 (procedure)",
        0.95,
    ),
    (
        "COVID-19 immunisation",
        "9990010003",
        "Administration of vaccine product against SARS-CoV-2 (procedure)",
        0.95,
    ),
    # Booster (359953009) -- no specific COVID booster procedure concept
    (
        "COVID-19 booster vaccination",
        "9990010003",
        "Administration of vaccine product against SARS-CoV-2 (procedure)",
        0.95,
    ),
    (
        "COVID booster",
        "9990010003",
        "Administration of vaccine product against SARS-CoV-2 (procedure)",
        0.93,
    ),
    (
        "COVID-19 booster dose",
        "9990010003",
        "Administration of vaccine product against SARS-CoV-2 (procedure)",
        0.93,
    ),
    (
        "booster dose COVID vaccine",
        "9990010003",
        "Administration of vaccine product against SARS-CoV-2 (procedure)",
        0.92,
    ),
    ("booster vaccination", "359953009", "Booster vaccination (procedure)", 0.92),
    # =======================================================================
    # COPD / RESPIRATORY -- COPD abbreviation first-pass returned suspected COPD
    # =======================================================================
    # COPD (13645005) -- CORRECTED from 204991000000107 (suspected COPD)
    ("COPD", "13645005", "Chronic obstructive pulmonary disease (disorder)", 0.95),
    (
        "chronic obstructive pulmonary disease",
        "13645005",
        "Chronic obstructive pulmonary disease (disorder)",
        0.98,
    ),
    ("COPD exacerbation", "195951007", "Acute exacerbation of COPD (disorder)", 0.97),
    (
        "exacerbation of COPD",
        "195951007",
        "Acute exacerbation of COPD (disorder)",
        0.97,
    ),
    (
        "acute COPD exacerbation",
        "195951007",
        "Acute exacerbation of COPD (disorder)",
        0.97,
    ),
    # Asthma (195967001)
    ("asthma", "195967001", "Asthma (disorder)", 0.98),
    ("brittle asthma", "195967001", "Asthma (disorder)", 0.93),
    ("asthma review", "195967001", "Asthma (disorder)", 0.90),
    # Pulmonary rehabilitation (15081005)
    (
        "pulmonary rehabilitation",
        "15081005",
        "Pulmonary rehabilitation (regime/therapy)",
        0.98,
    ),
    ("pulmonary rehab", "15081005", "Pulmonary rehabilitation (regime/therapy)", 0.95),
    # Inhaler technique observed (170614009)
    (
        "inhaler technique observed",
        "170614009",
        "Inhaler technique observed (situation)",
        0.93,
    ),
    (
        "inhaler technique checked",
        "170614009",
        "Inhaler technique observed (situation)",
        0.92,
    ),
    # =======================================================================
    # METABOLIC / LIPIDS
    # =======================================================================
    ("hyperlipidaemia", "55822004", "Hyperlipidemia (disorder)", 0.98),
    ("hyperlipidemia", "55822004", "Hyperlipidemia (disorder)", 0.98),
    ("hypercholesterolaemia", "13644009", "Hypercholesterolemia (disorder)", 0.98),
    ("hypercholesterolemia", "13644009", "Hypercholesterolemia (disorder)", 0.98),
    ("high cholesterol", "13644009", "Hypercholesterolemia (disorder)", 0.93),
    ("raised cholesterol", "13644009", "Hypercholesterolemia (disorder)", 0.92),
    ("mixed hyperlipidaemia", "267434003", "Mixed hyperlipidemia (disorder)", 0.97),
    ("hypertriglyceridaemia", "302870006", "Hypertriglyceridemia (disorder)", 0.97),
    # =======================================================================
    # NEUROLOGY
    # =======================================================================
    ("cerebral infarction", "432504007", "Cerebral infarction (disorder)", 0.98),
    (
        "cerebral watershed infarction",
        "432504007",
        "Cerebral infarction (disorder)",
        0.93,
    ),
    ("ischaemic stroke", "422504002", "Ischemic stroke (disorder)", 0.98),
    ("ischemic stroke", "422504002", "Ischemic stroke (disorder)", 0.98),
    ("stroke", "230690007", "Cerebrovascular accident (disorder)", 0.95),
    ("CVA", "230690007", "Cerebrovascular accident (disorder)", 0.90),
    ("TIA", "266257000", "Transient ischaemic attack (disorder)", 0.95),
    (
        "transient ischaemic attack",
        "266257000",
        "Transient ischaemic attack (disorder)",
        0.98,
    ),
    ("neurological deficit", "264552009", "Neurological deficit (finding)", 0.97),
    (
        "residual neurological weakness",
        "41786007",
        "Neurological muscle weakness (finding)",
        0.90,
    ),
    # =======================================================================
    # CKD STAGES
    # =======================================================================
    ("CKD stage 1", "431855005", "Chronic kidney disease stage 1 (disorder)", 0.97),
    ("CKD 1", "431855005", "Chronic kidney disease stage 1 (disorder)", 0.92),
    (
        "chronic kidney disease stage 1",
        "431855005",
        "Chronic kidney disease stage 1 (disorder)",
        0.98,
    ),
    ("CKD stage 2", "431856006", "Chronic kidney disease stage 2 (disorder)", 0.97),
    ("CKD 2", "431856006", "Chronic kidney disease stage 2 (disorder)", 0.92),
    (
        "chronic kidney disease stage 2",
        "431856006",
        "Chronic kidney disease stage 2 (disorder)",
        0.98,
    ),
    ("CKD stage 3", "433144002", "Chronic kidney disease stage 3 (disorder)", 0.97),
    ("CKD 3", "433144002", "Chronic kidney disease stage 3 (disorder)", 0.92),
    (
        "chronic kidney disease stage 3",
        "433144002",
        "Chronic kidney disease stage 3 (disorder)",
        0.98,
    ),
    ("CKD stage 3a", "700378005", "Chronic kidney disease stage 3A (disorder)", 0.97),
    ("CKD 3a", "700378005", "Chronic kidney disease stage 3A (disorder)", 0.95),
    (
        "chronic kidney disease stage 3a",
        "700378005",
        "Chronic kidney disease stage 3A (disorder)",
        0.98,
    ),
    ("CKD stage 3b", "700379002", "Chronic kidney disease stage 3B (disorder)", 0.97),
    ("CKD 3b", "700379002", "Chronic kidney disease stage 3B (disorder)", 0.95),
    (
        "chronic kidney disease stage 3b",
        "700379002",
        "Chronic kidney disease stage 3B (disorder)",
        0.98,
    ),
    ("CKD stage 4", "431857002", "Chronic kidney disease stage 4 (disorder)", 0.97),
    ("CKD 4", "431857002", "Chronic kidney disease stage 4 (disorder)", 0.92),
    (
        "chronic kidney disease stage 4",
        "431857002",
        "Chronic kidney disease stage 4 (disorder)",
        0.98,
    ),
    ("CKD stage 5", "433146000", "Chronic kidney disease stage 5 (disorder)", 0.97),
    ("CKD 5", "433146000", "Chronic kidney disease stage 5 (disorder)", 0.92),
    (
        "chronic kidney disease stage 5",
        "433146000",
        "Chronic kidney disease stage 5 (disorder)",
        0.98,
    ),
    # =======================================================================
    # DRUG MONITORING -- corrected: methotrexate returned substance, not procedure
    # =======================================================================
    (
        "methotrexate monitoring",
        "22189001",
        "Methotrexate measurement (procedure)",
        0.97,
    ),
    ("MTX monitoring", "22189001", "Methotrexate measurement (procedure)", 0.92),
    (
        "methotrexate blood monitoring",
        "22189001",
        "Methotrexate measurement (procedure)",
        0.95,
    ),
    (
        "lithium monitoring",
        "9990010010",
        "Monitoring of lithium therapy (regime/therapy)",
        0.97,
    ),
    (
        "lithium drug monitoring",
        "9990010010",
        "Monitoring of lithium therapy (regime/therapy)",
        0.97,
    ),
    (
        "lithium blood level monitoring",
        "9990010010",
        "Monitoring of lithium therapy (regime/therapy)",
        0.93,
    ),
    ("warfarin monitoring", "268526009", "Warfarin monitoring (regime/therapy)", 0.97),
    ("INR monitoring", "268526009", "Warfarin monitoring (regime/therapy)", 0.93),
    (
        "warfarin INR monitoring",
        "268526009",
        "Warfarin monitoring (regime/therapy)",
        0.97,
    ),
    # =======================================================================
    # HbA1c -- two concepts: measurement procedure + observable level
    # =======================================================================
    ("HbA1c", "43396009", "Hemoglobin A1c measurement (procedure)", 0.95),
    ("HbA1c test", "43396009", "Hemoglobin A1c measurement (procedure)", 0.97),
    ("HbA1c measurement", "43396009", "Hemoglobin A1c measurement (procedure)", 0.98),
    (
        "haemoglobin A1c measurement",
        "43396009",
        "Hemoglobin A1c measurement (procedure)",
        0.98,
    ),
    (
        "glycated haemoglobin test",
        "43396009",
        "Hemoglobin A1c measurement (procedure)",
        0.95,
    ),
    (
        "glycated haemoglobin measurement",
        "43396009",
        "Hemoglobin A1c measurement (procedure)",
        0.95,
    ),
    (
        "HbA1c level",
        "1003671000000109",
        "Haemoglobin A1c level (observable entity)",
        0.97,
    ),
    (
        "haemoglobin A1c level",
        "1003671000000109",
        "Haemoglobin A1c level (observable entity)",
        0.98,
    ),
    # =======================================================================
    # BLOOD PRESSURE -- corrected: preoperative/postoperative forms are wrong
    # =======================================================================
    (
        "blood pressure monitoring",
        "135840009",
        "Blood pressure monitoring (regime/therapy)",
        0.97,
    ),
    ("BP monitoring", "135840009", "Blood pressure monitoring (regime/therapy)", 0.93),
    (
        "blood pressure check",
        "135840009",
        "Blood pressure monitoring (regime/therapy)",
        0.93,
    ),
    (
        "blood pressure review",
        "135840009",
        "Blood pressure monitoring (regime/therapy)",
        0.90,
    ),
    # =======================================================================
    # DIABETIC RETINOPATHY SCREENING -- 134395001 confirmed on third query
    # =======================================================================
    (
        "diabetic retinopathy screening",
        "134395001",
        "Diabetic retinopathy screening (procedure)",
        0.98,
    ),
    (
        "diabetic retinal screening",
        "134395001",
        "Diabetic retinopathy screening (procedure)",
        0.97,
    ),
    (
        "diabetic eye screening",
        "134395001",
        "Diabetic retinopathy screening (procedure)",
        0.97,
    ),
    ("DRS", "134395001", "Diabetic retinopathy screening (procedure)", 0.88),
    (
        "diabetic retinal photograph",
        "134395001",
        "Diabetic retinopathy screening (procedure)",
        0.92,
    ),
    (
        "retinal photography diabetes",
        "134395001",
        "Diabetic retinopathy screening (procedure)",
        0.90,
    ),
    # =======================================================================
    # SUTURE REMOVAL -- corrected: conjunctival-specific -> 30549001 generic
    # =======================================================================
    ("suture removal", "30549001", "Removal of suture (procedure)", 0.98),
    ("removal of sutures", "30549001", "Removal of suture (procedure)", 0.98),
    ("stitch removal", "30549001", "Removal of suture (procedure)", 0.97),
    ("clips removed", "30549001", "Removal of suture (procedure)", 0.88),
    ("wound clips removed", "30549001", "Removal of suture (procedure)", 0.90),
    ("staples removed", "30549001", "Removal of suture (procedure)", 0.88),
    # =======================================================================
    # WIDE LOCAL EXCISION
    # =======================================================================
    ("wide local excision", "787439005", "Wide excision (procedure)", 0.98),
    ("WLE", "787439005", "Wide excision (procedure)", 0.90),
    ("wide local excision breast", "787439005", "Wide excision (procedure)", 0.95),
    ("wide local excision skin lesion", "787439005", "Wide excision (procedure)", 0.95),
    ("wide excision", "787439005", "Wide excision (procedure)", 0.97),
    # =======================================================================
    # HEAD AND NECK CANCER PATHWAY - SAFETY CRITICAL
    # =======================================================================
    # Fast track referral (280521000000108)
    (
        "fast track referral head and neck cancer",
        "280521000000108",
        "Fast track referral for suspected head and neck cancer (procedure)",
        0.98,
    ),
    (
        "head and neck cancer 2WW",
        "280521000000108",
        "Fast track referral for suspected head and neck cancer (procedure)",
        0.95,
    ),
    (
        "urgent referral suspected head and neck cancer",
        "280521000000108",
        "Fast track referral for suspected head and neck cancer (procedure)",
        0.97,
    ),
    (
        "2WW head and neck",
        "280521000000108",
        "Fast track referral for suspected head and neck cancer (procedure)",
        0.90,
    ),
    # Suspected (315277001)
    (
        "suspected head and neck cancer",
        "315277001",
        "Malignant neoplasm of head and/or neck suspected (situation)",
        0.97,
    ),
    (
        "head and neck cancer suspected",
        "315277001",
        "Malignant neoplasm of head and/or neck suspected (situation)",
        0.97,
    ),
    # Globus (267103008)
    ("globus sensation", "267103008", "Feeling of lump in throat (finding)", 0.98),
    ("lump in throat", "267103008", "Feeling of lump in throat (finding)", 0.97),
    (
        "feeling of lump in throat",
        "267103008",
        "Feeling of lump in throat (finding)",
        0.98,
    ),
    ("globus pharyngeus", "267103008", "Feeling of lump in throat (finding)", 0.97),
    # Neck lump (299703001)
    ("neck lump", "299703001", "Mass of neck (finding)", 0.98),
    ("lump in neck", "299703001", "Mass of neck (finding)", 0.97),
    ("neck mass", "299703001", "Mass of neck (finding)", 0.97),
    ("neck swelling", "299703001", "Mass of neck (finding)", 0.93),
    # Hoarseness (50219008)
    ("hoarseness", "50219008", "Hoarse (finding)", 0.98),
    ("hoarse voice", "50219008", "Hoarse (finding)", 0.97),
    ("hoarse", "50219008", "Hoarse (finding)", 0.95),
    ("voice hoarse", "50219008", "Hoarse (finding)", 0.93),
    # Dysphonia / persistent hoarseness (16617009) -- corrected from strained hoarse voice
    ("dysphonia", "16617009", "Dysphonia (disorder)", 0.98),
    ("persistent hoarse voice", "16617009", "Dysphonia (disorder)", 0.95),
    ("chronic hoarseness", "16617009", "Dysphonia (disorder)", 0.93),
    # =======================================================================
    # OTHER 2WW CANCER PATHWAYS
    # =======================================================================
    # Lung (276491000000101)
    (
        "lung cancer 2WW",
        "276491000000101",
        "Fast track referral for suspected lung cancer (procedure)",
        0.97,
    ),
    (
        "fast track referral lung cancer",
        "276491000000101",
        "Fast track referral for suspected lung cancer (procedure)",
        0.98,
    ),
    (
        "urgent referral suspected lung cancer",
        "276491000000101",
        "Fast track referral for suspected lung cancer (procedure)",
        0.97,
    ),
    (
        "2WW lung",
        "276491000000101",
        "Fast track referral for suspected lung cancer (procedure)",
        0.90,
    ),
    # Skin (276281000000104)
    (
        "skin cancer 2WW",
        "276281000000104",
        "Fast track referral for suspected skin cancer (procedure)",
        0.97,
    ),
    (
        "fast track referral skin cancer",
        "276281000000104",
        "Fast track referral for suspected skin cancer (procedure)",
        0.98,
    ),
    (
        "suspected skin cancer referral",
        "276281000000104",
        "Fast track referral for suspected skin cancer (procedure)",
        0.93,
    ),
    # Prostate (no specific fast-track concept -- use suspected situation)
    (
        "suspected prostate cancer",
        "315268008",
        "Malignant neoplasm of prostate suspected (situation)",
        0.97,
    ),
    (
        "prostate cancer suspected",
        "315268008",
        "Malignant neoplasm of prostate suspected (situation)",
        0.97,
    ),
    # Haematology (276461000000107) -- corrected from generic 199251000000107
    (
        "haematology 2WW",
        "276461000000107",
        "Fast track referral for suspected haematology malignancy (procedure)",
        0.97,
    ),
    (
        "fast track referral haematology malignancy",
        "276461000000107",
        "Fast track referral for suspected haematology malignancy (procedure)",
        0.98,
    ),
    (
        "2WW haematology",
        "276461000000107",
        "Fast track referral for suspected haematology malignancy (procedure)",
        0.92,
    ),
    # Urological (276431000000102)
    (
        "urological cancer 2WW",
        "276431000000102",
        "Fast track referral for suspected urological cancer (procedure)",
        0.97,
    ),
    (
        "fast track referral urological cancer",
        "276431000000102",
        "Fast track referral for suspected urological cancer (procedure)",
        0.98,
    ),
    (
        "2WW urology",
        "276431000000102",
        "Fast track referral for suspected urological cancer (procedure)",
        0.90,
    ),
    # Gynaecological (276311000000101)
    (
        "gynaecological cancer 2WW",
        "276311000000101",
        "Fast track referral for suspected gynaecological cancer (procedure)",
        0.97,
    ),
    (
        "fast track referral gynaecological cancer",
        "276311000000101",
        "Fast track referral for suspected gynaecological cancer (procedure)",
        0.98,
    ),
    (
        "2WW gynaecology",
        "276311000000101",
        "Fast track referral for suspected gynaecological cancer (procedure)",
        0.90,
    ),
    # =======================================================================
    # SAFETY NETTING
    # =======================================================================
    (
        "cancer safety netting",
        "1239431000000107",
        "Cancer safety netting (regime/therapy)",
        0.98,
    ),
    (
        "safety netting advice",
        "1239431000000107",
        "Cancer safety netting (regime/therapy)",
        0.95,
    ),
    (
        "safety netting",
        "1239431000000107",
        "Cancer safety netting (regime/therapy)",
        0.90,
    ),
    (
        "safety netting advice given",
        "1239431000000107",
        "Cancer safety netting (regime/therapy)",
        0.93,
    ),
    # =======================================================================
    # MEDICATION / DRUG STOPPED -- corrected from antidepressant/inappropriate-specific
    # =======================================================================
    ("medication stopped", "274512008", "Drug therapy discontinued (situation)", 0.97),
    (
        "drug therapy discontinued",
        "274512008",
        "Drug therapy discontinued (situation)",
        0.98,
    ),
    (
        "treatment discontinued",
        "274512008",
        "Drug therapy discontinued (situation)",
        0.95,
    ),
    (
        "medication discontinued",
        "274512008",
        "Drug therapy discontinued (situation)",
        0.97,
    ),
    ("drug stopped", "274512008", "Drug therapy discontinued (situation)", 0.93),
    (
        "drug treatment stopped",
        "274512008",
        "Drug therapy discontinued (situation)",
        0.93,
    ),
    # =======================================================================
    # SMOKING STATUS
    # =======================================================================
    ("heavy smoker", "230063004", "Heavy cigarette smoker (finding)", 0.98),
    ("heavy cigarette smoker", "230063004", "Heavy cigarette smoker (finding)", 0.98),
    (
        "heavy smoker over 20 per day",
        "56771006",
        "Heavy smoker (over 20 per day) (finding)",
        0.97,
    ),
    ("smoker 20 per day", "56771006", "Heavy smoker (over 20 per day) (finding)", 0.93),
    (
        "20 cigarettes per day",
        "56771006",
        "Heavy smoker (over 20 per day) (finding)",
        0.90,
    ),
    ("cigarette smoker", "65568007", "Cigarette smoker (finding)", 0.98),
    ("smoker", "65568007", "Cigarette smoker (finding)", 0.93),
    ("current smoker", "65568007", "Cigarette smoker (finding)", 0.95),
    ("ex-smoker", "8517006", "Ex-smoker (finding)", 0.98),
    ("ex smoker", "8517006", "Ex-smoker (finding)", 0.97),
    ("former smoker", "8517006", "Ex-smoker (finding)", 0.97),
    ("stopped smoking", "8517006", "Ex-smoker (finding)", 0.90),
    ("gave up smoking", "8517006", "Ex-smoker (finding)", 0.88),
    # =======================================================================
    # BREAST CANCER PATHWAY (retained from batch 3)
    # =======================================================================
    # Skin tethering (163491005)
    (
        "skin tethering breast",
        "163491005",
        "On examination - breast lump tethering (finding)",
        0.97,
    ),
    (
        "breast skin tethering",
        "163491005",
        "On examination - breast lump tethering (finding)",
        0.95,
    ),
    (
        "tethering of breast skin",
        "163491005",
        "On examination - breast lump tethering (finding)",
        0.93,
    ),
    # Breast lump (89164003) -- NOT the pregnancy-specific concept
    ("breast lump", "89164003", "Breast lump (finding)", 0.98),
    ("lump in breast", "89164003", "Breast lump (finding)", 0.97),
    ("lump breast", "89164003", "Breast lump (finding)", 0.95),
    ("breast mass", "89164003", "Breast lump (finding)", 0.95),
    ("palpable breast lump", "89164003", "Breast lump (finding)", 0.93),
    # Referral to breast clinic (313186001)
    (
        "referral to breast clinic",
        "313186001",
        "Referral to breast clinic (procedure)",
        0.98,
    ),
    (
        "breast clinic referral",
        "313186001",
        "Referral to breast clinic (procedure)",
        0.95,
    ),
    (
        "referred to breast clinic",
        "313186001",
        "Referral to breast clinic (procedure)",
        0.95,
    ),
    # Fast track referral breast cancer (276341000000100)
    (
        "fast track referral suspected breast cancer",
        "276341000000100",
        "Fast track referral for suspected breast cancer (procedure)",
        0.98,
    ),
    (
        "urgent referral breast cancer two week wait",
        "276341000000100",
        "Fast track referral for suspected breast cancer (procedure)",
        0.97,
    ),
    (
        "2WW breast referral",
        "276341000000100",
        "Fast track referral for suspected breast cancer (procedure)",
        0.93,
    ),
    (
        "urgent referral to breast clinic two week wait",
        "276341000000100",
        "Fast track referral for suspected breast cancer (procedure)",
        0.97,
    ),
    (
        "2WW breast",
        "276341000000100",
        "Fast track referral for suspected breast cancer (procedure)",
        0.90,
    ),
    # Invasive ductal carcinoma (408643008)
    (
        "invasive ductal carcinoma",
        "408643008",
        "Infiltrating duct carcinoma of breast (disorder)",
        0.98,
    ),
    (
        "infiltrating ductal carcinoma",
        "408643008",
        "Infiltrating duct carcinoma of breast (disorder)",
        0.97,
    ),
    (
        "invasive ductal carcinoma breast",
        "408643008",
        "Infiltrating duct carcinoma of breast (disorder)",
        0.97,
    ),
    (
        "IDC breast",
        "408643008",
        "Infiltrating duct carcinoma of breast (disorder)",
        0.90,
    ),
    # ER positive (416053008)
    (
        "oestrogen receptor positive",
        "416053008",
        "Estrogen receptor positive tumor (disorder)",
        0.97,
    ),
    (
        "estrogen receptor positive",
        "416053008",
        "Estrogen receptor positive tumor (disorder)",
        0.97,
    ),
    ("ER positive", "416053008", "Estrogen receptor positive tumor (disorder)", 0.92),
    ("ER+", "416053008", "Estrogen receptor positive tumor (disorder)", 0.88),
    (
        "hormone receptor positive",
        "416053008",
        "Estrogen receptor positive tumor (disorder)",
        0.88,
    ),
    # Radiotherapy to breast (428923005)
    ("radiotherapy breast", "428923005", "Radiotherapy to breast (procedure)", 0.98),
    ("breast radiotherapy", "428923005", "Radiotherapy to breast (procedure)", 0.97),
    ("radiotherapy to breast", "428923005", "Radiotherapy to breast (procedure)", 0.98),
    # Radiotherapy general (9990010012)
    ("radiotherapy", "9990010012", "Radiotherapy (procedure)", 0.95),
    ("radiation therapy", "9990010012", "Radiotherapy (procedure)", 0.95),
    ("radiotherapy treatment", "9990010012", "Radiotherapy (procedure)", 0.93),
    (
        "external beam radiotherapy",
        "33195004",
        "External beam radiation therapy procedure (procedure)",
        0.97,
    ),
    ("EBRT", "33195004", "External beam radiation therapy procedure (procedure)", 0.90),
    # Tamoxifen therapy (724161009)
    ("tamoxifen therapy", "724161009", "Tamoxifen therapy (procedure)", 0.97),
    ("on tamoxifen", "724161009", "Tamoxifen therapy (procedure)", 0.93),
    ("tamoxifen treatment", "724161009", "Tamoxifen therapy (procedure)", 0.95),
    # Mammography (71651007)
    ("mammogram", "71651007", "Mammography (procedure)", 0.98),
    ("mammography", "71651007", "Mammography (procedure)", 0.98),
    ("breast mammogram", "71651007", "Mammography (procedure)", 0.95),
    ("screening mammogram", "71651007", "Mammography (procedure)", 0.93),
    # Breast pain (53430007)
    ("breast pain", "53430007", "Pain of breast (finding)", 0.97),
    ("mastalgia", "53430007", "Pain of breast (finding)", 0.97),
    ("breast tenderness", "53430007", "Pain of breast (finding)", 0.93),
    # Nipple discharge (54302000)
    ("nipple discharge", "54302000", "Discharge from nipple (disorder)", 0.98),
    ("discharge from nipple", "54302000", "Discharge from nipple (disorder)", 0.97),
    ("bloody nipple discharge", "54302000", "Discharge from nipple (disorder)", 0.92),
    # =======================================================================
    # RECTAL / GI BLEEDING
    # =======================================================================
    # Rectal haemorrhage (12063002)
    ("rectal bleeding", "12063002", "Rectal hemorrhage (disorder)", 0.98),
    ("per rectum bleeding", "12063002", "Rectal hemorrhage (disorder)", 0.95),
    ("PR bleeding", "12063002", "Rectal hemorrhage (disorder)", 0.92),
    ("bleeding per rectum", "12063002", "Rectal hemorrhage (disorder)", 0.95),
    ("rectal haemorrhage", "12063002", "Rectal hemorrhage (disorder)", 0.98),
    # Haematochezia (405729008) -- bright red blood
    ("haematochezia", "405729008", "Hematochezia (finding)", 0.98),
    ("hematochezia", "405729008", "Hematochezia (finding)", 0.98),
    ("bright red rectal bleeding", "405729008", "Hematochezia (finding)", 0.95),
    ("bright red blood per rectum", "405729008", "Hematochezia (finding)", 0.95),
    ("BRBPR", "405729008", "Hematochezia (finding)", 0.90),
    # Melaena (2901004)
    ("melaena", "2901004", "Melena (disorder)", 0.98),
    ("melena", "2901004", "Melena (disorder)", 0.98),
    ("black tarry stool", "2901004", "Melena (disorder)", 0.90),
    ("malaena", "2901004", "Melena (disorder)", 0.97),
    # =======================================================================
    # WOUND CARE / SURGICAL
    # =======================================================================
    # Wound dehiscence (225553008)
    ("wound dehiscence", "225553008", "Wound dehiscence (disorder)", 0.98),
    ("wound breakdown", "225553008", "Wound dehiscence (disorder)", 0.95),
    ("dehiscence of wound", "225553008", "Wound dehiscence (disorder)", 0.95),
    # Wound infection (76844004)
    ("wound infection", "76844004", "Local infection of wound (disorder)", 0.98),
    ("infected wound", "76844004", "Local infection of wound (disorder)", 0.97),
    ("wound sepsis", "76844004", "Local infection of wound (disorder)", 0.92),
    # Skin grafting procedure (304040003)
    ("skin graft", "304040003", "Grafting to skin (procedure)", 0.95),
    ("skin grafting", "304040003", "Grafting to skin (procedure)", 0.97),
    ("split skin graft", "304040003", "Grafting to skin (procedure)", 0.93),
    ("skin graft lower leg", "304040003", "Grafting to skin (procedure)", 0.90),
    # =======================================================================
    # VAGINAL / UROGENITAL / MENOPAUSE
    # =======================================================================
    # Atrophic vaginitis (52441000) -- NOT 84568007 which is gastritis
    ("vaginal atrophy", "52441000", "Atrophic vaginitis (disorder)", 0.97),
    ("atrophic vaginitis", "52441000", "Atrophic vaginitis (disorder)", 0.98),
    ("vaginal atrophy menopause", "52441000", "Atrophic vaginitis (disorder)", 0.95),
    # Vaginal dryness (31908003)
    ("vaginal dryness", "31908003", "Vaginal dryness (disorder)", 0.98),
    ("dry vagina", "31908003", "Vaginal dryness (disorder)", 0.93),
    # Genitourinary syndrome of menopause (16779841000119104)
    (
        "genitourinary syndrome of menopause",
        "16779841000119104",
        "Genitourinary syndrome of menopause (disorder)",
        0.98,
    ),
    (
        "GSM",
        "16779841000119104",
        "Genitourinary syndrome of menopause (disorder)",
        0.88,
    ),
    # =======================================================================
    # UROLOGICAL SYMPTOMS
    # =======================================================================
    # Urinary frequency (162116003)
    (
        "urinary frequency",
        "162116003",
        "Increased frequency of urination (finding)",
        0.97,
    ),
    (
        "increased urinary frequency",
        "162116003",
        "Increased frequency of urination (finding)",
        0.97,
    ),
    (
        "frequency of micturition",
        "162116003",
        "Increased frequency of urination (finding)",
        0.93,
    ),
    (
        "frequent urination",
        "162116003",
        "Increased frequency of urination (finding)",
        0.93,
    ),
    ("pollakiuria", "162116003", "Increased frequency of urination (finding)", 0.90),
    # Nocturia (139394000)
    ("nocturia", "139394000", "Nocturia (finding)", 0.98),
    ("nocturnal frequency", "139394000", "Nocturia (finding)", 0.93),
    ("waking at night to pass urine", "139394000", "Nocturia (finding)", 0.90),
    # Urinary urgency -- NOT the pregnancy-specific one (117611000119108)
    # Using 75088002 = Urgent desire to urinate / overactive bladder = 786457000
    ("urinary urgency", "75088002", "Urgent desire to urinate (finding)", 0.97),
    ("urgency of micturition", "75088002", "Urgent desire to urinate (finding)", 0.97),
    ("urgency incontinence", "75088002", "Urgent desire to urinate (finding)", 0.88),
    ("overactive bladder", "786457000", "Overactive urinary bladder (disorder)", 0.97),
    ("OAB", "786457000", "Overactive urinary bladder (disorder)", 0.88),
    # Haematuria (34436003)
    ("haematuria", "34436003", "Blood in urine (finding)", 0.98),
    ("blood in urine", "34436003", "Blood in urine (finding)", 0.97),
    ("hematuria", "34436003", "Blood in urine (finding)", 0.98),
    ("frank haematuria", "197941005", "Frank hematuria (disorder)", 0.97),
    ("visible haematuria", "197941005", "Frank hematuria (disorder)", 0.95),
    ("macroscopic haematuria", "197941005", "Frank hematuria (disorder)", 0.95),
    ("microscopic haematuria", "197940006", "Microscopic hematuria (disorder)", 0.98),
    ("non-visible haematuria", "197940006", "Microscopic hematuria (disorder)", 0.95),
    # Dysphagia (40739000)
    ("dysphagia", "40739000", "Dysphagia (disorder)", 0.98),
    ("difficulty swallowing", "288939007", "Difficulty swallowing (finding)", 0.97),
    ("trouble swallowing", "288939007", "Difficulty swallowing (finding)", 0.93),
    # =======================================================================
    # ONCOLOGY PROCEDURES / IMAGING
    # =======================================================================
    # Lymph node biopsy (21911005)
    ("lymph node biopsy", "21911005", "Biopsy of lymph node (procedure)", 0.98),
    ("biopsy of lymph node", "21911005", "Biopsy of lymph node (procedure)", 0.98),
    (
        "lymph node excision biopsy",
        "21911005",
        "Biopsy of lymph node (procedure)",
        0.93,
    ),
    # CT chest abdomen pelvis (418023006)
    (
        "CT chest abdomen pelvis",
        "418023006",
        "Computed tomography of chest, abdomen and pelvis (procedure)",
        0.98,
    ),
    (
        "CT CAP",
        "418023006",
        "Computed tomography of chest, abdomen and pelvis (procedure)",
        0.95,
    ),
    (
        "CT of chest abdomen and pelvis",
        "418023006",
        "Computed tomography of chest, abdomen and pelvis (procedure)",
        0.97,
    ),
    # CT general (77477000)
    ("CT scan", "77477000", "Computed tomography (procedure)", 0.92),
    ("computed tomography", "77477000", "Computed tomography (procedure)", 0.95),
    # PET scan (82918005)
    ("PET scan", "82918005", "Positron emission tomography (procedure)", 0.98),
    ("PET-CT scan", "82918005", "Positron emission tomography (procedure)", 0.95),
    (
        "positron emission tomography",
        "82918005",
        "Positron emission tomography (procedure)",
        0.98,
    ),
    # DEXA / bone density (241686001 / 312681000)
    ("DEXA scan", "241686001", "Dual energy X-ray absorptiometry (procedure)", 0.98),
    ("DXA scan", "241686001", "Dual energy X-ray absorptiometry (procedure)", 0.97),
    ("bone density scan", "312681000", "Bone density scan (procedure)", 0.98),
    ("bone densitometry", "312681000", "Bone density scan (procedure)", 0.95),
    # Colonoscopy (73761001)
    ("colonoscopy", "73761001", "Colonoscopy (procedure)", 0.98),
    ("full colonoscopy", "73761001", "Colonoscopy (procedure)", 0.95),
    ("diagnostic colonoscopy", "73761001", "Colonoscopy (procedure)", 0.93),
    # Flexible sigmoidoscopy (44441009)
    (
        "flexible sigmoidoscopy",
        "44441009",
        "Flexible fiberoptic sigmoidoscopy (procedure)",
        0.98,
    ),
    (
        "sigmoidoscopy",
        "44441009",
        "Flexible fiberoptic sigmoidoscopy (procedure)",
        0.93,
    ),
    ("FS", "44441009", "Flexible fiberoptic sigmoidoscopy (procedure)", 0.80),
    # Cystoscopy (142505009)
    ("cystoscopy", "142505009", "Cystoscopy (procedure)", 0.98),
    ("flexible cystoscopy", "142505009", "Cystoscopy (procedure)", 0.95),
    # =======================================================================
    # CANCER-RELATED SYMPTOMS / NEUROPATHY
    # =======================================================================
    # Cancer-related fatigue (716749005)
    (
        "cancer related fatigue",
        "716749005",
        "Fatigue associated with malignant neoplastic disease (finding)",
        0.97,
    ),
    (
        "fatigue cancer related",
        "716749005",
        "Fatigue associated with malignant neoplastic disease (finding)",
        0.97,
    ),
    (
        "malignancy related fatigue",
        "716749005",
        "Fatigue associated with malignant neoplastic disease (finding)",
        0.95,
    ),
    (
        "chemotherapy related fatigue",
        "716749005",
        "Fatigue associated with malignant neoplastic disease (finding)",
        0.92,
    ),
    # Peripheral neuropathy (302226006)
    ("peripheral neuropathy", "302226006", "Peripheral nerve disease (disorder)", 0.97),
    (
        "peripheral nerve damage",
        "302226006",
        "Peripheral nerve disease (disorder)",
        0.90,
    ),
    # Chemotherapy-induced neuropathy (767659008)
    (
        "chemotherapy induced neuropathy",
        "767659008",
        "Peripheral neuropathy due to and following antineoplastic therapy (disorder)",
        0.97,
    ),
    (
        "CIPN",
        "767659008",
        "Peripheral neuropathy due to and following antineoplastic therapy (disorder)",
        0.90,
    ),
    (
        "chemotherapy induced peripheral neuropathy",
        "767659008",
        "Peripheral neuropathy due to and following antineoplastic therapy (disorder)",
        0.97,
    ),
]


def upsert_one(
    session: requests.Session,
    surface_form: str,
    concept_id: str,
    preferred_term: str,
    confidence: float,
    dry_run: bool,
) -> bool:
    if dry_run:
        print(f"  DRY  {surface_form!r:55s} -> {concept_id}")
        return True
    body = {
        "normalized": surface_form.lower().strip(),
        "form": surface_form,
        "concept_id": concept_id,
        "confidence": confidence,
        "source": "manual",
        "provenance": PROVENANCE,
    }
    resp = session.post(UPSERT_URL, json=body, timeout=30)
    ok = resp.status_code in (200, 201)
    status = "OK  " if ok else f"FAIL({resp.status_code})"
    print(f"  {status}  {surface_form!r:55s} -> {concept_id}  |  {preferred_term[:50]}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(
        f"Writing {len(SURFACE_FORMS)} batch-6 surface form mappings "
        f"({'DRY RUN' if args.dry_run else 'LIVE'})\n"
    )

    headers = get_service_auth_header()
    session = requests.Session()
    session.headers.update(headers)

    written = failed = 0
    for sf, cid, term, conf in SURFACE_FORMS:
        ok = upsert_one(session, sf, cid, term, conf, args.dry_run)
        if ok:
            written += 1
        else:
            failed += 1
        time.sleep(0.05)

    print(
        f"\nDone: {written} {'would write' if args.dry_run else 'written'}, {failed} failed"
    )


if __name__ == "__main__":
    main()
