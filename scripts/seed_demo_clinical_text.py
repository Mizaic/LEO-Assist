#!/usr/bin/env python3
"""Add rich free-text clinical content to the demo practice patient graph.

Layers added (all idempotent):

  1. Encounter text  - realistic GP / specialist prose for all 195 demo
                       milestone encounters (referral, diagnosis, symptoms,
                       benign_closure, blood).

  2. Narrative referral letter chunks
                     - flowing prose "reason for referral" chunk appended
                       to each existing 2WW / specialist referral DR.

  3. Clinic response letters
                     - outpatient response DocumentReference + Chunks from
                       secondary care back to the referring GP (all 80 patients).

  4. Discharge summaries
                     - inpatient discharge summary DocumentReference + Chunks
                       for completed cancer patients 001-035.

Usage:
    python -m scripts.seed_demo_clinical_text            # add all layers
    python -m scripts.seed_demo_clinical_text --force    # teardown + re-add
    python -m scripts.seed_demo_clinical_text --teardown # remove added content
"""

from __future__ import annotations

import hashlib
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "secrets" / ".env")
load_dotenv(ROOT / ".env", override=False)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

_RNG = random.Random(77)

_SOURCE_TAG = "demo-clinical-text"

# ---------------------------------------------------------------------------
# Encounter text templates
# Per milestone type x pathway (or status for benign/blood)
# ---------------------------------------------------------------------------

_REFERRAL_ENC: dict[str, str] = {
    "lung": (
        "62-year-old male smoker presents today requesting urgent review. "
        "6-week history of progressive haemoptysis - intermittent bright red blood "
        "in sputum, occurring approximately three times per week. "
        "Associated with a persistent dry cough present for several months. "
        "30 pack-year smoking history; currently smoking 15 cigarettes per day. "
        "Background of COPD managed with inhalers. "
        "Chest X-ray arranged earlier this week demonstrates a right hilar opacity "
        "with possible mass lesion - radiologist suggests urgent CT chest. "
        "No weight loss or haemoptysis currently. Observations stable. "
        "Given the clinical picture and radiological findings, I am referring urgently "
        "under the 2-week wait pathway for suspected lung cancer. "
        "Prescriptions: Salbutamol 100mcg PRN, Tiotropium 18mcg OD, Amlodipine 5mg OD. "
        "Plan: 2WW lung cancer referral sent. Repeat CXR in 4 weeks if not seen sooner."
    ),
    "colorectal": (
        "58-year-old female presenting with a 10-week history of fresh rectal bleeding. "
        "Reports blood mixed with stool, not just on paper. "
        "Concurrent change in bowel habit - looser stools, increased frequency to 4-5 times "
        "daily with associated urgency. No abdominal mass palpable. "
        "FIT test performed 2 weeks ago: result 45 micrograms Hb per gram (significantly elevated). "
        "Blood results today: Hb 108 g/L, MCV 74 (iron deficiency pattern), "
        "ferritin 8 ng/ml. Iron deficiency anaemia confirmed. "
        "Father had colorectal cancer diagnosed at 62 years old. "
        "Background: type 2 diabetes, hypertension. "
        "2-week wait referral made today for suspected colorectal malignancy. "
        "Iron supplementation commenced: Ferrous fumarate 210mg BD. "
        "CEA sent: 4.2 ng/ml. Patient counselled regarding possible diagnosis."
    ),
    "breast": (
        "47-year-old female presents with a 4-week history of a lump in the right breast. "
        "On examination: 2 cm firm, irregular, non-tender mass in the upper outer quadrant. "
        "Skin puckering noted overlying the lesion. No axillary lymphadenopathy palpable. "
        "No nipple discharge. No family history of breast cancer. "
        "Last mammogram over 3 years ago - normal at that time. "
        "Patient understandably anxious. I have discussed the need for urgent assessment. "
        "2-week wait referral submitted today to the one-stop breast clinic. "
        "Advised patient she will receive an appointment within 2 weeks. "
        "Bloods: FBC normal, CA125 not indicated at this stage. "
        "Plan: Urgent 2WW breast referral. Safety-netting advice given."
    ),
    "prostate": (
        "68-year-old male presents with a 3-month history of lower urinary tract symptoms. "
        "Reports urinary hesitancy, poor stream, sensation of incomplete emptying, "
        "and nocturia three times per night. No haematuria. No back pain. "
        "Digital rectal examination today: prostate feels hard and irregular bilaterally, "
        "significantly enlarged. "
        "PSA result: 18.2 ng/ml (age-specific threshold 4 ng/ml). Markedly elevated. "
        "Previous PSA 2 years ago was 6.8 - progressive rise. "
        "Background: hypertension. Medications: Ramipril 5mg OD. "
        "Given elevated PSA and abnormal DRE, urgent 2WW urology referral submitted "
        "today for suspected prostate cancer. "
        "IPSS score documented: 21 (severely symptomatic). "
        "Patient counselled; aware of the possibility of malignancy."
    ),
    "upper_gi": (
        "72-year-old female presents with a 6-week history of progressive dysphagia. "
        "Initially difficulty swallowing solids, now struggling with soft foods. "
        "Associated with significant unintentional weight loss - patient reports losing "
        "approximately 8 kg over the past 2 months (confirmed on scales today vs 3 months ago). "
        "Epigastric pain present, worse after eating. No vomiting. "
        "H. pylori breath test: positive. "
        "Blood results: Hb 102 g/L, MCV 78, ALP 122 (mildly raised), albumin 30 g/L, "
        "CRP 64 mg/L. Significant hypoalbuminaemia and raised inflammatory markers. "
        "I am very concerned about the possibility of oesophageal or gastric malignancy. "
        "Urgent 2WW referral submitted today to upper GI surgery. "
        "H. pylori eradication therapy started: Omeprazole 20mg BD, "
        "Amoxicillin 1g BD, Clarithromycin 500mg BD for 7 days."
    ),
    "skin": (
        "54-year-old male presents with a changing pigmented lesion on the left shoulder. "
        "He first noticed the lesion 2 years ago but reports it has visibly changed "
        "over the past 8 weeks - larger, borders more irregular, colour more varied. "
        "On examination: 12 mm asymmetric lesion with irregular border, multiple shades "
        "of brown and black with a darker area at the centre. No satellite lesions. "
        "No palpable lymphadenopathy in the axilla. "
        "Weighted 7-point checklist: Major features - change in size [2], "
        "irregular border [2]. Score 4. "
        "Urgent 2-week wait referral to dermatology / pigmented lesion clinic submitted. "
        "Patient advised to keep lesion covered from sun exposure. "
        "Safety net: return if lesion bleeds or ulcerates before appointment."
    ),
    "cardiology": (
        "64-year-old male presents with a 3-month history of exertional chest pain. "
        "Describes tight, central chest pressure radiating to the left arm, occurring "
        "on climbing one flight of stairs or walking briskly on the flat. "
        "Resolves within 5 minutes of rest. No symptoms at rest. "
        "Risk factors: hypertension (10 years), type 2 diabetes (5 years), "
        "ex-smoker (20 pack-years, stopped 8 years ago). "
        "ECG performed today: ST depression in V4-V6 during episode of pain. "
        "Troponin I: <14 ng/L (negative). "
        "Echo arranged: LV function mildly impaired, EF estimated 45%. "
        "Cholesterol: 6.2 mmol/L, LDL 3.8, HbA1c 58 mmol/mol. "
        "Impression: likely stable angina with possible underlying coronary artery disease. "
        "Urgent referral to cardiology outpatients. "
        "Started on Aspirin 75mg OD, Atorvastatin 40mg ON. "
        "GTN spray prescribed for acute episodes. Safety netting: 999 if chest pain at rest."
    ),
    "urology": (
        "61-year-old male presents with a 6-week history of painless visible haematuria. "
        "Two distinct episodes of macroscopic haematuria - terminal in pattern. "
        "No dysuria, no loin pain, no urinary frequency beyond baseline. "
        "No anticoagulant use. No recent urological procedures. "
        "MSU sent 2 weeks ago: no growth, no infection. "
        "Urine cytology: atypical cells present - reported as 'cannot exclude high-grade "
        "urothelial carcinoma'. "
        "Bloods: FBC Hb 129 g/L (normal), eGFR 68 mL/min, PSA 2.1 ng/ml. "
        "CT KUB requested - result pending. "
        "Background: recurrent UTIs (3 in past year), hypertension. "
        "Given the haematuria and atypical cytology, urgent urology referral made today. "
        "Patient advised to re-present if further haematuria or urinary retention. "
        "Advised to stay well hydrated."
    ),
    "gastroenterology": (
        "34-year-old female presents with a 4-month history of change in bowel habit. "
        "Reports 5-6 loose stools per day with urgency and occasional rectal bleeding "
        "- blood mixed with stool. Crampy lower abdominal pain preceding defaecation. "
        "Associated 5 kg unintentional weight loss over 4 months. Fatigue significant. "
        "Faecal calprotectin: 820 mcg/g (markedly elevated). "
        "FBC: Hb 104 g/L, WCC 12.1, Plts 520, MCV 78, albumin 28 g/L. "
        "CRP 42 mg/L, ESR 55 mm/hr. Significant systemic inflammation. "
        "FIT: 35 mcg Hb/g. "
        "Mother has Crohn's disease. No prior GI diagnosis. "
        "Clinical picture strongly suspicious for inflammatory bowel disease. "
        "Urgent gastroenterology referral submitted. "
        "Ferrous fumarate 210mg BD commenced. "
        "Advised to keep a food and symptom diary."
    ),
    "rheumatology": (
        "52-year-old female presents with a 3-month history of joint swelling and pain. "
        "Affects small joints of hands and wrists symmetrically. "
        "Morning stiffness lasting over 1 hour - often extends to 2-3 hours. "
        "Grip strength significantly reduced. Difficulty opening jars, buttoning clothes. "
        "No psoriasis, no eye symptoms, no recent infection or diarrhoea. "
        "Anti-CCP antibody: 140 U/ml (strongly positive). "
        "Rheumatoid factor: 64 IU/ml (positive). "
        "CRP 38 mg/L, ESR 62 mm/hr. Significant systemic inflammation. "
        "X-ray hands: periarticular osteopenia bilaterally, no erosions identified yet. "
        "Background: hypothyroidism (Levothyroxine 100mcg OD). Sister has RA. "
        "Impression: highly likely early seropositive rheumatoid arthritis. "
        "Urgent rheumatology referral submitted - DMARD therapy likely needed. "
        "Naproxen 500mg BD commenced as bridge. Proton pump inhibitor added."
    ),
    "neurology": (
        "71-year-old male presents acutely following a TIA-like episode this morning. "
        "Developed sudden onset right arm weakness and slurred speech that lasted "
        "approximately 20 minutes before fully resolving. No headache, no visual change. "
        "NIHSS on arrival: 0 - fully recovered. "
        "ABCD2 score: 5 (age >60, BP >140, unilateral weakness, duration >10 min) - high risk. "
        "CT head performed in A&E: no acute infarct, no haemorrhage, no mass lesion. "
        "ECG: sinus rhythm, no AF. "
        "Carotid Doppler: 40% stenosis right ICA. "
        "Background: hypertension (poorly controlled - BP 162/94 today), "
        "paroxysmal AF on Apixaban 5mg BD. "
        "Cholesterol: 5.8 mmol/L. HbA1c: 48 mmol/mol. "
        "Assessed as likely TIA - urgent neurovascular clinic referral same day. "
        "Aspirin 300mg stat given. Atorvastatin increased to 80mg ON. "
        "BP medication reviewed: Amlodipine increased to 10mg OD. "
        "Advised patient regarding driving (DVLA notification required)."
    ),
    "respiratory": (
        "67-year-old female presents with progressive breathlessness over 6 months. "
        "Dyspnoea now on walking 50 metres on the flat (MRC grade 3). "
        "Persistent productive cough with clear/white sputum. "
        "Two infective exacerbations requiring antibiotics in the past year. "
        "Spirometry performed today: FEV1 1.4L (58% predicted), FVC 2.2L, "
        "FEV1/FVC ratio 0.64 - obstructive pattern, GOLD grade 2. "
        "CXR: hyperinflation, flattened diaphragms, no consolidation. "
        "Sats at rest: 94% on air. Exercise sats: 88% after 2 min walk. "
        "Ex-smoker, 40 pack-years, stopped 5 years ago. "
        "Known alpha-1 antitrypsin deficiency (ZZ genotype). "
        "FBC: Hb 162 g/L (secondary polycythaemia). "
        "Impression: COPD with possible accelerated decline due to alpha-1 AT deficiency. "
        "Respiratory outpatient referral submitted for full assessment and pulmonary rehab. "
        "Increased Tiotropium, added Formoterol/Budesonide inhaler."
    ),
    "endocrinology": (
        "46-year-old male presents with a 3-month history of polydipsia, polyuria, "
        "and significant unintentional weight loss of 8 kg. "
        "Reports fatigue and blurred vision. No nausea, vomiting, or ketotic symptoms. "
        "HbA1c performed 2 weeks ago: 96 mmol/mol - confirmed on repeat today. "
        "Random blood glucose today: 18.4 mmol/L. "
        "Urine dipstick: glycosuria 3+, no ketones, protein 1+. "
        "Urine ACR: 42 mg/mmol (elevated - possible early nephropathy). "
        "eGFR: 62 mL/min. Total cholesterol: 7.1 mmol/L. TSH: 3.2 mIU/L (normal). "
        "Background: hypothyroidism (Levothyroxine 75mcg), hypertension (Lisinopril 10mg). "
        "Mother has type 2 diabetes. "
        "Impression: newly diagnosed type 2 diabetes mellitus, poorly controlled, "
        "possible early complications. "
        "Urgent endocrinology referral submitted. "
        "Metformin 500mg OD commenced (to uptitrate). Dietary advice given. "
        "Ophthalmology referral for retinal screening. Foot check arranged."
    ),
    "haematology": (
        "58-year-old female presents with progressive fatigue and malaise over 2 months. "
        "Reports drenching night sweats requiring change of nightclothes and "
        "6 kg unintentional weight loss. "
        "On examination: multiple enlarged cervical lymph nodes bilaterally, "
        "largest approximately 3 cm. Mild splenomegaly. No hepatomegaly. "
        "FBC: Hb 92 g/L, WCC 2.8 x10^9/L (leucopenia), Plts 88 x10^9/L (low), "
        "Lymphocytes 1.1 x10^9/L. Pancytopenia on peripheral blood. "
        "LDH: 480 IU/L (markedly elevated). "
        "Beta-2 microglobulin: 4.2 mg/L (elevated). "
        "CT neck, chest, abdomen: mediastinal and inguinal lymphadenopathy. No liver lesions. "
        "Blood film: atypical lymphocytes present, no blast cells seen. "
        "Impression: likely lymphoma - urgent haematology referral submitted today. "
        "Bone marrow biopsy will be arranged by haematology. "
        "Patient counselled regarding findings; very anxious. Support provided."
    ),
}

_DIAGNOSIS_ENC: dict[str, str] = {
    "lung": (
        "MDT review following CT-PET scan. "
        "CT chest: 3.8 cm right upper lobe mass with mediastinal lymphadenopathy (N2). "
        "PET-CT: FDG-avid mass consistent with primary lung malignancy, "
        "no distant metastases. "
        "Bronchoscopy: endobronchial biopsy confirms non-small cell lung carcinoma, "
        "adenocarcinoma type. EGFR mutation: negative. ALK: negative. PD-L1: 45%. "
        "Stage: IIIa (T2N2M0). "
        "Discussed at lung MDT - recommended concurrent chemoradiotherapy. "
        "Patient commenced on Carboplatin/Paclitaxel. "
        "Discussed diagnosis fully with patient and family. Lung CNS allocated. "
        "Performance status: ECOG 1."
    ),
    "colorectal": (
        "Colonoscopy performed: 4.5 cm irregular, ulcerated lesion in the sigmoid colon "
        "at 25 cm - biopsied. Multiple polyps removed elsewhere. "
        "Histology: invasive moderately differentiated adenocarcinoma of sigmoid colon. "
        "Staging CT chest, abdomen, pelvis: no distant metastases. "
        "MRI pelvis: sigmoid tumour, no mesorectal involvement. "
        "Stage: T3N1M0 (Stage IIIB). "
        "Presented at colorectal MDT: recommended laparoscopic sigmoid colectomy "
        "followed by adjuvant FOLFOX chemotherapy. "
        "Pre-operative assessment completed. Surgery planned within 4 weeks. "
        "Stoma nurse assessment completed. Patient counselled fully."
    ),
    "breast": (
        "One-stop breast clinic attendance. Triple assessment completed. "
        "Clinical examination: confirmed 2 cm mass upper outer quadrant right breast. "
        "Mammogram and ultrasound: 2.2 cm spiculated lesion, highly suspicious "
        "(R5/U5), one axillary lymph node with cortical thickening. "
        "Core biopsy: Grade 2 invasive ductal carcinoma. ER positive (8/8), "
        "PR positive, HER2 negative. Ki67 15%. "
        "Sentinel node biopsy: 1 of 3 nodes positive (micrometastasis). "
        "Stage: T2N1M0 (Stage IIa). "
        "Breast MDT: recommended wide local excision + axillary clearance "
        "followed by radiotherapy and Tamoxifen. "
        "Breast care nurse support initiated. Genetic counselling referral made "
        "(BRCA testing offered given age)."
    ),
    "prostate": (
        "Urology outpatient review. Repeat PSA: 19.1 ng/ml. "
        "MRI prostate: large T3 lesion right peripheral zone extending to seminal vesicle. "
        "PI-RADS 5 lesion. "
        "Transperineal template biopsy: Grade Group 4 (Gleason 4+4=8) adenocarcinoma, "
        "12 of 20 cores positive. "
        "Staging CT chest, abdomen, pelvis: no lymphadenopathy, no bone metastases. "
        "Bone scan: no suspicious uptake. "
        "Stage: T3aN0M0 (High-risk localised). "
        "Prostate MDT: recommended radical prostatectomy with bilateral lymph node dissection "
        "vs radical radiotherapy + long-term ADT. Patient counselled regarding both options. "
        "Chose robotic-assisted prostatectomy. Listed for surgery. "
        "Continence and erectile function discussed; patient referred to specialist nurse."
    ),
    "upper_gi": (
        "Upper GI endoscopy performed under IV sedation. "
        "Large circumferential lesion at 32-38 cm from incisors, involving the "
        "oesophago-gastric junction. Biopsied x6. "
        "Histology: poorly differentiated adenocarcinoma of the gastro-oesophageal junction "
        "(Siewert type II). HER2: negative. "
        "CT staging: T3 tumour, perigastric lymph nodes involved, no distant metastases. "
        "PET-CT: no occult metastatic disease. Staging laparoscopy: no peritoneal deposits. "
        "Stage: T3N2M0 (Stage IIIA). "
        "Upper GI MDT: recommended perioperative FLOT chemotherapy "
        "followed by oesophago-gastrectomy. "
        "Pre-operative nutrition: NG feeding commenced given dysphagia and malnutrition. "
        "Dietitian and upper GI specialist nurse involved in care."
    ),
    "skin": (
        "Dermatology assessment at rapid access pigmented lesion clinic. "
        "Dermoscopy: atypical pigment network, irregular globules, regression structures. "
        "Wide local excision performed: 15 mm asymmetric nodular melanoma, "
        "Breslow thickness 2.8 mm, Clark level IV, ulcerated. "
        "Histology: malignant melanoma, nodular subtype. "
        "Sentinel lymph node biopsy: positive (1/3 nodes, 0.4 mm deposit). "
        "Stage: pT3bN1a (Stage IIIA). "
        "Melanoma MDT: completion lymph node dissection performed "
        "followed by 12 months adjuvant Pembrolizumab immunotherapy. "
        "Discussed hereditary melanoma - CDKN2A testing offered. "
        "Melanoma specialist nurse allocated. 3-monthly surveillance planned. "
        "Patient and family fully counselled regarding prognosis and treatment intent."
    ),
}

_BENIGN_CLOSURE_ENC = (
    "Patient reviewed following completion of 2WW pathway investigations. "
    "All investigations including scope / imaging / biopsy as appropriate have been "
    "reviewed at the relevant MDT. "
    "Outcome: no evidence of malignancy identified. "
    "Findings attributed to benign pathology - full details in clinic letter. "
    "Patient counselled and reassured. Discharged back to GP care with safety-net advice. "
    "GP advised to re-refer if new or worsening symptoms develop. "
    "Follow-up plan: GP review in 6 weeks."
)

_SYMPTOMS_ENC: dict[str, str] = {
    "lung": (
        "Patient attends for routine review. Mentions persistent cough now present for "
        "6 weeks. Initially dry, now occasionally productive. "
        "Also reports one episode of blood-tinged sputum last week - small amount. "
        "Significant smoking history (30 pack-years). "
        "On examination: reduced air entry right base, no wheeze. "
        "CXR requested - to report within 5 working days. "
        "Patient advised to return immediately if further haemoptysis. "
        "Safety net: A&E if large volume haemoptysis."
    ),
    "colorectal": (
        "Patient presents reporting rectal bleeding on three occasions over the past month. "
        "Blood mixed with stool (not on paper only). No haemorrhoids on previous examination. "
        "Changed bowel habit - looser stools, occasional urgency. "
        "Abdominal examination: mild left iliac fossa tenderness. No mass palpable. "
        "FIT test given today - result expected in 2 weeks. "
        "FBC requested: results pending. "
        "Patient advised to avoid delay in returning if symptoms worsen."
    ),
    "breast": (
        "Patient self-referred - discovered lump in right breast in shower 3 days ago. "
        "Lump feels firm. No pain initially but mild discomfort now. "
        "Menstrual cycle regular. No family history of breast cancer. "
        "Examination: confirmed irregular lump approximately 2 cm in upper outer quadrant "
        "right breast. Skin puckering overlying the area. No discharge from nipple. "
        "Left breast: normal. Lymph nodes: no palpable axillary lymphadenopathy. "
        "Referred urgently for urgent breast clinic assessment. "
        "Patient counselled; understands she will be seen within 2 weeks."
    ),
    "prostate": (
        "Patient presents complaining of urinary problems - difficulty starting stream, "
        "poor flow, waking twice nightly. Symptoms gradually worsening over past 3 months. "
        "IPSS questionnaire completed: score 18 (moderate-severe). "
        "No haematuria. No back pain or bone pain. "
        "PSA blood test requested today. "
        "DRE arranged for next appointment when results available. "
        "Advised to reduce fluid intake before bed. "
        "Discussed alpha-blocker therapy - to review once PSA result known."
    ),
    "upper_gi": (
        "Patient returns 6 weeks after initial consultation reporting no improvement "
        "in swallowing difficulties. Now struggling with soft foods. "
        "Weight loss continues - down a further 3 kg since last seen. "
        "Patient looks cachectic. Pallor noted. "
        "Upper GI symptoms clearly progressive. "
        "Blood results today show Hb 102, albumin 30, ALP mildly elevated. "
        "Impression: progressive dysphagia and malnutrition - urgent 2WW referral indicated. "
        "H. pylori test requested pending. Nutritional supplement prescribed."
    ),
    "skin": (
        "Patient booked appointment following advice from spouse who noticed lesion "
        "on the patient's left shoulder had changed colour. "
        "Patient had dismissed it but agrees it has changed recently. "
        "On examination: 12 mm pigmented lesion, asymmetric, irregular irregular margin, "
        "variegated colour (brown, black with darker central area). "
        "7-point weighted checklist: scores 4 (major: change in size 2, irregular border 2). "
        "2WW pigmented lesion referral submitted today. "
        "Patient advised not to use fake tan or sun cream on lesion. "
        "Follow-up: 2WW appointment expected within 2 weeks."
    ),
}

_BLOOD_ENC = (
    "Patient attends for routine blood tests as part of annual review and ongoing monitoring. "
    "Full blood count: Hb within normal range, mild lymphocytosis noted - to monitor. "
    "Inflammatory markers: CRP mildly elevated at 18 mg/L. "
    "Renal profile: eGFR stable. Electrolytes normal. "
    "Liver function: mildly abnormal ALP - repeat in 3 months. "
    "HbA1c: 52 mmol/mol - borderline. Dietary advice reinforced. "
    "Bone profile: calcium and phosphate normal. "
    "Full results filed. Patient to be contacted with results within 5 working days. "
    "Plan: repeat FBC in 6 weeks given lymphocytosis. Review in 3 months."
)

# ---------------------------------------------------------------------------
# Narrative referral letter prose per pathway (appended to existing DRs)
# ---------------------------------------------------------------------------

_NARRATIVE_REFERRAL: dict[str, str] = {
    "lung": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent 2WW Referral - Suspected Lung Cancer\n\n"
        "Thank you for seeing this patient who I am referring urgently under the two-week "
        "wait pathway for suspected lung cancer.\n\n"
        "This patient presents with a 6-week history of haemoptysis and persistent dry cough. "
        "They have a significant 30 pack-year smoking history and a background of COPD. "
        "Chest X-ray performed this week demonstrates a right hilar opacity with a possible "
        "mass lesion - the radiologist has suggested urgent CT chest.\n\n"
        "On examination today the patient is haemodynamically stable with oxygen saturations "
        "of 96% on air. There are reduced breath sounds at the right base. "
        "There is no clinical evidence of distant metastatic disease.\n\n"
        "I would be grateful for urgent assessment and investigation to exclude malignancy. "
        "The patient is fully aware of the reason for referral and consents to being seen.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "colorectal": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent 2WW Referral - Suspected Colorectal Cancer\n\n"
        "I am writing to refer this patient urgently under the two-week wait pathway "
        "for suspected colorectal cancer.\n\n"
        "The patient has a 10-week history of fresh rectal bleeding with a concurrent "
        "change in bowel habit to looser stools with increased frequency. "
        "FIT test result: 45 micrograms of haemoglobin per gram - significantly elevated. "
        "Blood tests show iron deficiency anaemia (Hb 108 g/L, ferritin 8 ng/ml). "
        "Family history: father diagnosed with colorectal cancer at age 62.\n\n"
        "The combination of symptoms, elevated FIT, and family history makes me significantly "
        "concerned about the possibility of colorectal malignancy. "
        "I would be grateful for urgent colonoscopy and further assessment.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "breast": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent 2WW Referral - Suspected Breast Cancer\n\n"
        "I am referring this patient urgently for assessment at the one-stop breast clinic "
        "under the two-week wait pathway.\n\n"
        "The patient presents with a 4-week history of a lump in the right breast. "
        "On clinical examination I found a 2 cm firm, irregular, non-tender mass in the "
        "upper outer quadrant of the right breast with overlying skin puckering. "
        "There is no palpable axillary lymphadenopathy. "
        "The features of the mass are concerning for malignancy.\n\n"
        "The patient has not had a mammogram in the past 3 years. "
        "I would be grateful for urgent triple assessment.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "prostate": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent 2WW Referral - Suspected Prostate Cancer\n\n"
        "I am referring this patient urgently to urology under the two-week wait pathway "
        "for investigation of suspected prostate cancer.\n\n"
        "This patient presents with a 3-month history of lower urinary tract symptoms "
        "including hesitancy, poor stream, and nocturia x3. On digital rectal examination "
        "the prostate is hard and irregular bilaterally with significant enlargement. "
        "PSA today: 18.2 ng/ml (age-specific threshold 4.0 ng/ml). "
        "Previous PSA 2 years ago: 6.8 ng/ml - showing progressive rise.\n\n"
        "The combination of a markedly elevated PSA and an abnormal DRE makes me very "
        "concerned about prostate malignancy. I would be grateful for urgent assessment.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "upper_gi": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent 2WW Referral - Suspected Upper GI Cancer\n\n"
        "I am referring this patient urgently under the two-week wait pathway for "
        "investigation of suspected upper gastrointestinal malignancy.\n\n"
        "The patient presents with a 6-week history of progressive dysphagia, initially "
        "to solids and now extending to soft foods. There has been significant unintentional "
        "weight loss of 8 kg over the past 2 months. Associated epigastric pain is present.\n\n"
        "Blood tests show Hb 102 g/L with a microcytic pattern, albumin 30 g/L, "
        "mildly raised ALP, and CRP 64 mg/L. H. pylori breath test is positive. "
        "I am very concerned about oesophageal or gastric malignancy.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "skin": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent 2WW Referral - Suspected Melanoma\n\n"
        "I am referring this patient urgently to the pigmented lesion clinic under "
        "the two-week wait pathway for assessment of a suspicious skin lesion.\n\n"
        "The patient has a changing pigmented lesion on the left shoulder. "
        "On examination this is a 12 mm asymmetric lesion with irregular borders "
        "and variegated colouration (brown and black). The patient reports visible "
        "increase in size over the past 8 weeks. "
        "Weighted 7-point checklist score: 4 (major criteria: change in size, "
        "irregular border). "
        "I am concerned about the possibility of melanoma.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "cardiology": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent Cardiology Referral - Suspected Angina / ACS\n\n"
        "Thank you for seeing this patient who I am referring for urgent cardiology review.\n\n"
        "This patient has a 3-month history of exertional chest tightness radiating to "
        "the left arm, relieved by rest within 5 minutes. Significant risk factors include "
        "hypertension, type 2 diabetes, and a 20 pack-year smoking history. "
        "Today's ECG shows ST depression in V4-V6 during an episode of pain. "
        "Troponin is negative. Echocardiogram shows mildly impaired LV function (EF 45%). "
        "Cholesterol is elevated at 6.2 mmol/L.\n\n"
        "I have commenced aspirin 75mg and atorvastatin 40mg and prescribed GTN. "
        "I would be grateful for urgent outpatient review and consideration of angiography.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "urology": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent Urology Referral - Haematuria\n\n"
        "I am referring this patient urgently for urology assessment of painless "
        "visible haematuria.\n\n"
        "The patient has had two episodes of macroscopic haematuria over the past 6 weeks. "
        "MSU has excluded urinary tract infection. Urine cytology shows atypical cells "
        "which the reporting cytologist states cannot exclude high-grade urothelial carcinoma. "
        "eGFR is 68 mL/min, PSA 2.1 ng/ml. CT KUB is pending.\n\n"
        "Given the haematuria and concerning cytology result I would be grateful for "
        "urgent cystoscopy and further assessment.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "gastroenterology": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent Gastroenterology Referral - Suspected IBD\n\n"
        "I am referring this patient urgently for gastroenterology assessment.\n\n"
        "This patient has a 4-month history of diarrhoea (5-6 times daily with urgency "
        "and rectal bleeding), lower abdominal pain, and 5 kg unintentional weight loss. "
        "Faecal calprotectin is markedly elevated at 820 mcg/g. "
        "Bloods: Hb 104 g/L, CRP 42 mg/L, albumin 28 g/L - significant systemic inflammation. "
        "Mother has Crohn's disease.\n\n"
        "The clinical picture is strongly suggestive of inflammatory bowel disease. "
        "I would be grateful for urgent assessment and colonoscopy.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "rheumatology": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent Rheumatology Referral - Suspected Early RA\n\n"
        "I am writing to refer this patient urgently for rheumatology assessment.\n\n"
        "This patient has a 3-month history of symmetrical small joint swelling and "
        "pain affecting the hands and wrists, with morning stiffness lasting over 1 hour. "
        "Anti-CCP is strongly positive (140 U/ml). Rheumatoid factor is positive (64 IU/ml). "
        "CRP is elevated at 38 mg/L. X-ray hands show periarticular osteopenia "
        "but no erosions as yet.\n\n"
        "I believe this patient has early seropositive rheumatoid arthritis and that "
        "early DMARD therapy is indicated. I would be grateful for urgent assessment.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "neurology": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent Neurology Referral - TIA\n\n"
        "I am referring this patient urgently following a high-risk TIA today.\n\n"
        "The patient experienced sudden onset right arm weakness and slurred speech "
        "lasting 20 minutes this morning before fully resolving. ABCD2 score is 5. "
        "CT head shows no acute changes. ECG is sinus rhythm; the patient is on "
        "Apixaban for known paroxysmal AF. Carotid Doppler: 40% right ICA stenosis. "
        "Blood pressure today: 162/94 mmHg despite treatment.\n\n"
        "I have given aspirin 300mg and increased the statin dose. "
        "I would be grateful for urgent neurovascular clinic assessment today.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "respiratory": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Respiratory Referral - Progressive COPD / Alpha-1 Antitrypsin Deficiency\n\n"
        "I am referring this patient for respiratory outpatient assessment.\n\n"
        "This patient has progressive breathlessness (MRC grade 3), persistent productive "
        "cough, and two infective exacerbations requiring antibiotics in the past year. "
        "Spirometry confirms moderate airflow obstruction (FEV1 58% predicted, FEV1/FVC 0.64). "
        "The patient has known alpha-1 antitrypsin deficiency (ZZ genotype) "
        "and a 40 pack-year smoking history. "
        "FBC shows secondary polycythaemia (Hb 162 g/L). Sats drop to 88% on exertion.\n\n"
        "I would be grateful for full assessment including consideration of augmentation "
        "therapy, pulmonary rehabilitation, and long-term oxygen assessment.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "endocrinology": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent Endocrinology Referral - New Poorly-Controlled Type 2 Diabetes\n\n"
        "I am referring this patient urgently for endocrinology review.\n\n"
        "This patient has newly diagnosed type 2 diabetes with markedly elevated HbA1c "
        "of 96 mmol/mol on two occasions. Random glucose today: 18.4 mmol/L. "
        "There are potential early complications: urine ACR 42 mg/mmol and eGFR 62 mL/min "
        "suggest possible early diabetic nephropathy. "
        "Total cholesterol is elevated at 7.1 mmol/L.\n\n"
        "I have commenced metformin and referred for retinal screening and foot assessment. "
        "I would be grateful for specialist input into optimising glycaemic control "
        "and managing the cardiovascular risk.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
    "haematology": (
        "Dear Colleague,\n\n"
        "Re: [DEMO] Urgent Haematology Referral - Suspected Lymphoma\n\n"
        "I am referring this patient urgently for haematology assessment.\n\n"
        "This patient has a 2-month history of progressive fatigue, drenching night sweats, "
        "and 6 kg unintentional weight loss ('B symptoms'). On examination there are "
        "multiple enlarged cervical lymph nodes and mild splenomegaly. "
        "FBC reveals pancytopenia (Hb 92, WCC 2.8, Plts 88). "
        "LDH is markedly elevated at 480 IU/L. CT imaging confirms mediastinal and "
        "inguinal lymphadenopathy. Blood film shows atypical lymphocytes.\n\n"
        "The overall picture is highly concerning for lymphoma and I would be "
        "grateful for urgent assessment, biopsy, and staging.\n\n"
        "Yours sincerely,\nDr Demo GP\nDemo Medical Centre"
    ),
}

# ---------------------------------------------------------------------------
# Outpatient clinic response letters (secondary care -> GP)
# ---------------------------------------------------------------------------

_CLINIC_LETTER: dict[str, str] = {
    "lung": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Thoracic Oncology Outpatient Review\n\n"
        "Thank you for referring this patient who attended our thoracic oncology clinic today. "
        "I have reviewed the imaging and performed a full clinical assessment.\n\n"
        "CT chest confirms a 3.8 cm right upper lobe mass with mediastinal lymphadenopathy. "
        "We have arranged PET-CT scan and bronchoscopy with EBUS. "
        "Provisional staging is at least stage II-III NSCLC pending full results.\n\n"
        "The patient has been counselled regarding the possibility of lung cancer and the "
        "forthcoming investigations. They are coping well and have family support. "
        "Lung cancer specialist nurse has been allocated.\n\n"
        "We will discuss at our weekly lung MDT once all results are available. "
        "I will write again with the MDT outcome and treatment plan.\n\n"
        "Yours sincerely,\nDr Demo Thoracic Oncologist\nDemo Hospital Trust"
    ),
    "colorectal": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Colorectal Surgery Outpatient Review\n\n"
        "Thank you for this urgent 2WW referral. I reviewed this patient in clinic today "
        "and proceeded directly to diagnostic colonoscopy under the one-stop pathway.\n\n"
        "Colonoscopy: A 4.5 cm ulcerated lesion was found in the sigmoid colon. "
        "Multiple biopsies taken. "
        "CT staging has been arranged for this week.\n\n"
        "Pending histology, this is highly likely to represent colorectal adenocarcinoma. "
        "We will discuss at the colorectal MDT as soon as histology is confirmed. "
        "The patient has been informed that we suspect cancer and will be contact with "
        "a treatment plan.\n\n"
        "Colorectal cancer nurse specialist allocated.\n\n"
        "Yours sincerely,\nDr Demo Colorectal Surgeon\nDemo Hospital Trust"
    ),
    "breast": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - One-Stop Breast Clinic Review\n\n"
        "Thank you for this prompt 2WW referral. I saw this patient today in our "
        "one-stop breast clinic.\n\n"
        "Triple assessment was completed: "
        "Clinical examination confirmed an irregular 2 cm mass upper outer quadrant right breast. "
        "Mammogram and ultrasound both graded R5/U5 (highly suspicious of malignancy). "
        "Core biopsy was performed - result expected within 5 working days.\n\n"
        "We have counselled the patient that the clinical and radiological findings "
        "are concerning and we are awaiting histological confirmation. "
        "Breast care nurse has been allocated. "
        "Results review appointment booked in 7 days.\n\n"
        "Yours sincerely,\nDr Demo Breast Surgeon\nDemo Hospital Trust"
    ),
    "cardiology": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Cardiology Outpatient Review\n\n"
        "Thank you for referring this patient with exertional chest pain and ECG changes. "
        "I reviewed them in outpatient clinic today.\n\n"
        "History is consistent with stable angina. Risk factors include hypertension, "
        "T2DM, and previous smoking history. "
        "Repeat ECG shows persisting ST changes. "
        "I have arranged exercise tolerance test and CT coronary angiography.\n\n"
        "I have added Bisoprolol 2.5mg OD and Isosorbide mononitrate 30mg OD. "
        "Please ensure blood pressure and diabetes are optimally controlled. "
        "If symptoms escalate or the patient develops chest pain at rest, "
        "please send directly to the cardiology assessment unit.\n\n"
        "Yours sincerely,\nDr Demo Cardiologist\nDemo Hospital Trust"
    ),
    "urology": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Urology Outpatient Review\n\n"
        "Thank you for referring this patient with painless haematuria and concerning "
        "urine cytology. I reviewed them in our haematuria clinic today.\n\n"
        "Flexible cystoscopy performed: papillary lesion seen at the right lateral wall "
        "of the bladder approximately 1.5 cm. Biopsied. "
        "CT urogram confirms this lesion with no upper tract filling defects. "
        "Histology pending - we are proceeding to TURBT under GA next week.\n\n"
        "Patient consented and listed. "
        "Please note they should not take anticoagulants for 5 days pre-procedure.\n\n"
        "Yours sincerely,\nDr Demo Urologist\nDemo Hospital Trust"
    ),
    "gastroenterology": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Gastroenterology Outpatient Review\n\n"
        "Thank you for this urgent referral for suspected inflammatory bowel disease. "
        "I reviewed the patient in clinic today.\n\n"
        "Colonoscopy has been arranged for next week as an urgent procedure. "
        "In the interim I have started mesalazine 2.4g daily empirically given the "
        "clinical picture and elevated inflammatory markers.\n\n"
        "I have also arranged MRI small bowel and stool culture to exclude infection. "
        "Please ensure iron supplementation continues. "
        "If the patient deteriorates with high stool frequency, rectal bleeding, "
        "or systemic features please admit directly.\n\n"
        "Yours sincerely,\nDr Demo Gastroenterologist\nDemo Hospital Trust"
    ),
    "rheumatology": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Rheumatology Outpatient Review\n\n"
        "Thank you for this prompt referral. I reviewed this patient in our early "
        "inflammatory arthritis clinic today.\n\n"
        "Examination confirms bilateral synovitis affecting MCP and PIP joints "
        "and both wrists. Combined with the strongly positive anti-CCP and raised "
        "CRP, the diagnosis of seropositive rheumatoid arthritis is confirmed.\n\n"
        "I have commenced methotrexate 10mg weekly with folic acid 5mg weekly. "
        "Prescribing initiated - please ensure baseline FBC, LFTs, and renal function "
        "are checked in 4 weeks and monthly thereafter. "
        "Patient counselled regarding DMARD monitoring. Hydoxychloroquine added. "
        "DAS28 score documented for NICE monitoring purposes.\n\n"
        "Yours sincerely,\nDr Demo Rheumatologist\nDemo Hospital Trust"
    ),
    "neurology": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Neurovascular / TIA Clinic Review\n\n"
        "Thank you for this urgent same-day referral following a high-risk TIA. "
        "I assessed the patient in our rapid access TIA clinic today.\n\n"
        "Examination: no focal neurological signs. NIHSS 0. "
        "MRI brain (DWI): single small acute ischaemic lesion in left corona radiata "
        "consistent with small vessel disease. "
        "Echocardiogram: normal LV function, no thrombus. In sinus rhythm today.\n\n"
        "Diagnosis: minor ischaemic stroke (not TIA as MRI positive). "
        "Dual antiplatelet for 21 days then switch to single agent. "
        "Apixaban continued for AF. Blood pressure target <130/80 - referred to "
        "hypertension clinic. DVLA notified. "
        "Secondary prevention fully established.\n\n"
        "Yours sincerely,\nDr Demo Neurologist\nDemo Hospital Trust"
    ),
    "respiratory": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Respiratory Outpatient Review\n\n"
        "Thank you for referring this patient with progressive COPD and known "
        "alpha-1 antitrypsin deficiency.\n\n"
        "Full pulmonary function tests confirm severe fixed airflow obstruction "
        "(FEV1 52% predicted post-bronchodilator). "
        "DLCO reduced at 58% - consistent with emphysema. "
        "High resolution CT: extensive bilateral panacinar emphysema, "
        "consistent with alpha-1 AT deficiency pattern.\n\n"
        "I have referred to the national alpha-1 AT centre for augmentation therapy assessment. "
        "Long-term oxygen therapy assessment has been arranged. "
        "Enrolled in 8-week pulmonary rehabilitation programme. "
        "Influenza and pneumococcal vaccinations up to date.\n\n"
        "Yours sincerely,\nDr Demo Respiratory Physician\nDemo Hospital Trust"
    ),
    "endocrinology": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Endocrinology Outpatient Review\n\n"
        "Thank you for referring this patient with newly diagnosed poorly controlled "
        "type 2 diabetes.\n\n"
        "I reviewed this patient today. HbA1c remains 96 mmol/mol. "
        "I have uptitrated metformin to 1g BD and added Empagliflozin 10mg OD "
        "for its cardiorenal protective effects given the CKD stage 3a. "
        "Linagliptin added to the regimen.\n\n"
        "Diabetic nephropathy is confirmed - I have referred to renal clinic. "
        "Please ensure ACE inhibitor is optimised. "
        "Fenofibrate added for dyslipidaemia. "
        "Ophthalmology has confirmed background diabetic retinopathy - annual review. "
        "Structured diabetes education programme referral made.\n\n"
        "Yours sincerely,\nDr Demo Endocrinologist\nDemo Hospital Trust"
    ),
    "haematology": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Haematology Outpatient Review\n\n"
        "Thank you for this urgent referral. I reviewed this patient in our haematology "
        "day unit today.\n\n"
        "Examination confirms significant bilateral cervical lymphadenopathy "
        "and splenomegaly. B symptoms confirmed. "
        "Excision biopsy of right cervical node performed under LA today. "
        "Histology pending - expected within 5 working days.\n\n"
        "Bone marrow trephine biopsy arranged for later this week. "
        "Staging CT confirms mediastinal, para-aortic, and inguinal nodal disease. "
        "No CNS involvement on MRI.\n\n"
        "Provisional diagnosis: likely diffuse large B-cell lymphoma (DLBCL) "
        "pending histology. R-CHOP chemotherapy likely first-line treatment. "
        "MDT discussion this Thursday.\n\n"
        "Yours sincerely,\nDr Demo Haematologist\nDemo Hospital Trust"
    ),
    "prostate": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Urology / Prostate Cancer Outpatient Review\n\n"
        "Thank you for this urgent 2WW referral. I reviewed this patient in our "
        "rapid access prostate clinic today.\n\n"
        "MRI prostate has been arranged as a priority. "
        "Repeat PSA today confirms persistent elevation at 19.1 ng/ml. "
        "On examination, prostate is hard and nodular bilaterally.\n\n"
        "I have counselled the patient that prostate cancer is likely given the "
        "PSA and DRE findings. "
        "Transperineal template biopsy will be arranged pending MRI. "
        "Bone and CT staging to follow once histology confirmed.\n\n"
        "Prostate cancer specialist nurse allocated. "
        "I will write again once full staging is complete.\n\n"
        "Yours sincerely,\nDr Demo Urologist\nDemo Hospital Trust"
    ),
    "upper_gi": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Upper GI Surgery Outpatient Review\n\n"
        "Thank you for this urgent 2WW referral for dysphagia and weight loss.\n\n"
        "I reviewed this patient today and arranged urgent OGD which was performed "
        "same day. Large circumferential lesion found at the gastro-oesophageal junction. "
        "Multiple biopsies taken. CT staging and PET-CT arranged urgently.\n\n"
        "Nutritional support is paramount - I have started high-calorie nutritional "
        "supplements and referred to our specialist dietitian. "
        "Given the severity of dysphagia and malnutrition, consideration will be "
        "given to NG feeding pending treatment planning.\n\n"
        "The patient is aware that the finding is very likely to represent cancer. "
        "Upper GI specialist nurse allocated.\n\n"
        "Yours sincerely,\nDr Demo Upper GI Surgeon\nDemo Hospital Trust"
    ),
    "skin": (
        "Dear Dr Demo,\n\n"
        "Re: [DEMO] Clinic Letter - Dermatology / Pigmented Lesion Clinic Review\n\n"
        "Thank you for this urgent 2WW referral for a suspicious pigmented lesion.\n\n"
        "I reviewed the patient today and performed dermoscopy. "
        "The lesion has features of a high-risk melanocytic lesion: "
        "atypical pigment network, irregular globules, and regression structures. "
        "Wide local excision was performed today under local anaesthetic with 2 mm margins. "
        "Histology expected within 7 days.\n\n"
        "Depending on Breslow thickness, sentinel lymph node biopsy may be required. "
        "Patient counselled: aware we are concerned about melanoma. "
        "Melanoma specialist nurse contact details provided. "
        "I will write again once histology is available.\n\n"
        "Yours sincerely,\nDr Demo Dermatologist\nDemo Hospital Trust"
    ),
}

# ---------------------------------------------------------------------------
# Discharge summaries for cancer patients (001-035)
# ---------------------------------------------------------------------------

_DISCHARGE_SUMMARY: dict[str, str] = {
    "lung": (
        "INPATIENT DISCHARGE SUMMARY - [DEMO] Thoracic Oncology\n\n"
        "Admission diagnosis: Non-small cell lung cancer (adenocarcinoma), Stage IIIa, "
        "right upper lobe, T2N2M0.\n\n"
        "Admission for: Cycle 1 concurrent chemoradiotherapy (Carboplatin/Paclitaxel "
        "with 60 Gy in 30 fractions).\n\n"
        "Inpatient course: First cycle of concurrent CRT administered without major "
        "complications. Mild nausea managed with ondansetron. Fatigue expected. "
        "Haemoglobin maintained. No febrile neutropenia.\n\n"
        "Radiological response: Interim CT at week 4 shows partial response.\n\n"
        "Discharge medications: Dexamethasone 4mg TDS (reducing), Ondansetron 8mg PRN, "
        "Omeprazole 20mg OD, Cotrimoxazole prophylaxis.\n\n"
        "Follow-up: Oncology outpatient 2 weeks, Lung CNS contact provided.\n"
        "Emergency contact: Acute Oncology Service 24-hour line.\n\n"
        "Discharge diagnosis: NSCLC adenocarcinoma Stage IIIa - active treatment commenced."
    ),
    "colorectal": (
        "INPATIENT DISCHARGE SUMMARY - [DEMO] Colorectal Surgery\n\n"
        "Admission diagnosis: Adenocarcinoma sigmoid colon, T3N1M0 (Stage IIIB).\n\n"
        "Procedure: Laparoscopic sigmoid colectomy + D3 lymph node dissection.\n\n"
        "Inpatient course: Uncomplicated laparoscopic resection. "
        "R0 resection confirmed - clear margins. "
        "Enhanced recovery pathway: mobilising day 1, tolerating soft diet day 2. "
        "No anastomotic leak. No post-operative ileus. Wound healing well.\n\n"
        "Histology confirmed: pT3pN1 (2/15 nodes positive). No lymphovascular invasion. "
        "MSI stable. RAS wild-type (eligible for anti-EGFR therapy if required).\n\n"
        "Discharge medications: Paracetamol, Ibuprofen, Codeine PRN, Enoxaparin for 28 days.\n\n"
        "Follow-up: Colorectal MDT to confirm FOLFOX adjuvant chemotherapy. "
        "Oncology outpatient 2 weeks. Nurse specialist contact provided. "
        "CEA surveillance initiated.\n\n"
        "Discharge diagnosis: pT3pN1 sigmoid adenocarcinoma - R0 resection, "
        "adjuvant chemotherapy planned."
    ),
    "breast": (
        "INPATIENT DISCHARGE SUMMARY - [DEMO] Breast Surgery\n\n"
        "Admission: Elective admission for wide local excision right breast and "
        "axillary lymph node clearance.\n\n"
        "Procedure: Wide local excision (35mm excision, 15mm margins) + "
        "axillary lymph node clearance (Level II).\n\n"
        "Inpatient course: Day case procedure. No operative complications. "
        "Drain inserted - removed day 1. Pain well controlled. "
        "Post-operative exercises taught by physiotherapist.\n\n"
        "Final histology: Grade 2 IDC, 18mm, R0 (3mm clearance). "
        "ER 8/8, PR positive, HER2 negative. Ki67 15%. "
        "Axillary clearance: 1/12 nodes positive (micrometastasis 0.4mm). "
        "Staged: ypT2pN1mi.\n\n"
        "Follow-up: Oncology outpatient 3 weeks to plan radiotherapy and hormonal therapy. "
        "Tamoxifen to be commenced. Breast care nurse contact provided. "
        "BRCA test result pending - genetic clinic appointment made.\n\n"
        "Discharge medications: Paracetamol, Diclofenac, Tamoxifen 20mg OD commenced."
    ),
    "upper_gi": (
        "INPATIENT DISCHARGE SUMMARY - [DEMO] Upper GI Surgery\n\n"
        "Admission: Oesophago-gastric adenocarcinoma GEJ (Siewert II), T3N2M0, Stage IIIA.\n\n"
        "Procedure: Ivor-Lewis oesophagectomy with two-field lymph node dissection "
        "following completion of 4 cycles perioperative FLOT chemotherapy.\n\n"
        "Inpatient course: Complex post-operative course. Anastomotic leak day 5 "
        "managed conservatively with drain and IV antibiotics. "
        "Chest physiotherapy. Dietitian input - jejunostomy feeding maintained. "
        "Discharged day 18 with jejunostomy in situ.\n\n"
        "Histology: ypT2N1 - pathological partial response to FLOT chemotherapy. "
        "R0 resection achieved.\n\n"
        "Follow-up: Upper GI clinic 2 weeks. Oncology for 4 further cycles FLOT. "
        "Dietitian ongoing - target weight restoration. "
        "Jejunostomy team to review feeding at home.\n\n"
        "Discharge diagnosis: OGJ adenocarcinoma - R0 resection achieved, "
        "adjuvant chemotherapy planned."
    ),
    "skin": (
        "INPATIENT DISCHARGE SUMMARY - [DEMO] Melanoma / Plastic Surgery\n\n"
        "Admission: Malignant melanoma left shoulder, pT3b (Breslow 2.8mm, ulcerated), "
        "sentinel node positive (pN1a).\n\n"
        "Procedure: Wide re-excision (2 cm margins) + completion left axillary "
        "lymph node dissection.\n\n"
        "Inpatient course: Uncomplicated. Primary closure achieved. "
        "Drain removed day 2. No seroma. Wound healed well.\n\n"
        "Final histology: Completion dissection - 0/14 further nodes positive. "
        "No residual melanoma in re-excision specimen. "
        "Staged: pT3bN1a (Stage IIIA) - eligible for adjuvant immunotherapy.\n\n"
        "Treatment plan: Adjuvant Pembrolizumab 200mg q3w for 12 months. "
        "First infusion planned 3 weeks post-surgery.\n\n"
        "Follow-up: Melanoma MDT reviewed. Oncology to arrange Pembrolizumab. "
        "Dermatology / melanoma nurse specialist surveillance every 3 months. "
        "CDKN2A genetic testing offered.\n\n"
        "Discharge diagnosis: Melanoma Stage IIIA - R0 resection, "
        "adjuvant Pembrolizumab planned."
    ),
    "prostate": (
        "INPATIENT DISCHARGE SUMMARY - [DEMO] Robotic Urology\n\n"
        "Admission: Prostate adenocarcinoma Gleason 4+4=8 (Grade Group 4), T3aN0M0.\n\n"
        "Procedure: Robotic-assisted laparoscopic radical prostatectomy (RALRP) + "
        "bilateral extended pelvic lymph node dissection.\n\n"
        "Inpatient course: Uncomplicated procedure. Estimated blood loss 150 mL. "
        "Urethral catheter in situ - to be removed 10 days post-operatively. "
        "Mobilising day 1, tolerating diet day 1. Discharged day 2.\n\n"
        "Final histology: pT3aN0 (positive surgical margin at apex - under review). "
        "0/14 lymph nodes involved. "
        "MDT to review regarding adjuvant radiotherapy to the prostate bed.\n\n"
        "Follow-up: Urology outpatient 2 weeks (catheter removal). "
        "PSA 6 weeks post-op (target <0.1 ng/ml). "
        "Continence nurse contact provided. ED management discussed.\n\n"
        "Discharge diagnosis: Prostate cancer pT3aN0M0 - R1 resection, "
        "adjuvant radiotherapy under consideration."
    ),
    "breast_alt": (  # spare template for cycling
        "INPATIENT DISCHARGE SUMMARY - [DEMO] Breast Surgery\n\n"
        "Admission: Elective day case mastectomy and immediate implant reconstruction.\n\n"
        "Procedure: Skin-sparing mastectomy right breast + immediate subpectoral "
        "implant reconstruction.\n\n"
        "Inpatient course: Procedure performed under general anaesthetic. "
        "No complications. Two wound drains in situ at discharge. "
        "Patient given drain care instructions. Pain well controlled.\n\n"
        "Final histology: Grade 3 IDC 28mm. ER negative, PR negative, HER2 positive. "
        "No axillary involvement (sentinel node negative).\n\n"
        "Follow-up: Breast clinic 7 days for wound check and drain removal. "
        "Oncology to plan anthracycline + taxane + Herceptin chemotherapy regimen. "
        "Breast care nurse allocated.\n\n"
        "Discharge diagnosis: HER2-positive breast cancer pT2N0M0 - "
        "targeted therapy planned."
    ),
}

_DISCHARGE_FALLBACK = (
    "INPATIENT DISCHARGE SUMMARY - [DEMO] Oncology\n\n"
    "Admission: Confirmed malignancy - treatment initiated.\n\n"
    "Inpatient course: First cycle of systemic treatment administered. "
    "Patient tolerated treatment with grade 1-2 toxicities only. "
    "Nausea managed with antiemetics. Adequate performance status maintained.\n\n"
    "Discharged with supportive medications and 24-hour oncology helpline number.\n\n"
    "Follow-up: Oncology outpatient in 3 weeks. Specialist nurse allocated. "
    "Emergency contact: Acute Oncology Service.\n\n"
    "Discharge diagnosis: Active malignancy - systemic treatment commenced."
)

# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def _chunk_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _make_chunk_id(dr: str, ordinal: int, sha: str) -> str:
    return hashlib.sha256(f"{dr}:{ordinal}:{sha}".encode()).hexdigest()[:32]


def _clinic_dr_id(idx: int) -> str:
    return f"demo-clinic-{idx:03d}:leo-clinic-bundle"


def _discharge_dr_id(idx: int) -> str:
    return f"demo-discharge-{idx:03d}:leo-discharge-bundle"


# ---------------------------------------------------------------------------
# Step 1 - Update encounter text
# ---------------------------------------------------------------------------

def _encounter_text(milestone: str, pathway: str, cancer_type: str | None) -> str:
    key = cancer_type or pathway
    if milestone == "referral":
        return _REFERRAL_ENC.get(key, _REFERRAL_ENC.get(pathway, ""))
    if milestone == "diagnosis":
        return _DIAGNOSIS_ENC.get(key, _DISCHARGE_FALLBACK)
    if milestone == "symptoms":
        return _SYMPTOMS_ENC.get(key, _SYMPTOMS_ENC.get(pathway, ""))
    if milestone == "benign_closure":
        return _BENIGN_CLOSURE_ENC
    if milestone == "blood":
        return _BLOOD_ENC
    return ""


def _update_encounter_text(client: PatientGraphClient) -> int:
    # Load all demo encounters with milestone type and episode cancer type
    rows = client.run(
        "MATCH (p:Patient {source:'demo'})-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE e.id STARTS WITH 'demo-' "
        "OPTIONAL MATCH (e)-[r:IS_PART_OF]->(ep:EpisodeOfCare) "
        "RETURN e.id AS enc_id, r.milestone_type AS milestone, "
        "       ep.cancer_type AS cancer_type"
    )

    # Also load pathway from referral request for each patient
    rr_rows = client.run(
        "MATCH (rr:ReferralRequest {source:'demo'})-[:FOR_PATIENT]->(p) "
        "RETURN p.id AS patient_id, rr.specialty AS specialty"
    )
    patient_specialty = {r["patient_id"]: r["specialty"] for r in rr_rows}

    # specialty -> pathway key mapping
    _sp_to_pathway = {
        "2WW": None,  # use cancer_type
        "Cardiology": "cardiology",
        "Urology": "urology",
        "Gastroenterology": "gastroenterology",
        "Rheumatology": "rheumatology",
        "Neurology": "neurology",
        "Respiratory": "respiratory",
        "Endocrinology": "endocrinology",
        "Haematology": "haematology",
    }

    updated = 0
    for row in rows:
        enc_id: str = row["enc_id"]
        milestone: str = row.get("milestone") or ""
        cancer_type: str | None = row.get("cancer_type")

        # derive patient index from enc_id: "demo-enc-001-referral"
        parts = enc_id.split("-")
        patient_id = f"demo-patient-{parts[2]}"
        specialty = patient_specialty.get(patient_id, "2WW")
        pathway_key = _sp_to_pathway.get(specialty) or cancer_type or "lung"

        # infer milestone from enc_id suffix if not in IS_PART_OF
        if not milestone:
            milestone = parts[-1]

        text = _encounter_text(milestone, pathway_key, cancer_type)
        if not text:
            continue

        client.run(
            "MATCH (e:Encounter {id: $enc_id}) SET e.text = $text",
            enc_id=enc_id,
            text=text,
        )
        updated += 1
    return updated


# ---------------------------------------------------------------------------
# Step 2 - Add narrative referral letter chunk to existing DRs
# ---------------------------------------------------------------------------

def _add_narrative_chunks(client: PatientGraphClient) -> int:
    rr_rows = client.run(
        "MATCH (rr:ReferralRequest {source:'demo'})-[:HAS_DOCUMENT]->(dr) "
        "MATCH (rr)-[:FOR_PATIENT]->(p) "
        "RETURN rr.id AS rr_id, dr.id AS dr_id, p.id AS patient_id, "
        "       rr.specialty AS specialty"
    )

    _sp_to_pathway = {
        "2WW": None,
        "Cardiology": "cardiology",
        "Urology": "urology",
        "Gastroenterology": "gastroenterology",
        "Rheumatology": "rheumatology",
        "Neurology": "neurology",
        "Respiratory": "respiratory",
        "Endocrinology": "endocrinology",
        "Haematology": "haematology",
    }

    # Load episode cancer types
    ep_rows = client.run(
        "MATCH (p:Patient {source:'demo'})-[:HAS_EPISODE_OF_CARE]->(ep) "
        "RETURN p.id AS patient_id, ep.cancer_type AS cancer_type"
    )
    patient_cancer = {r["patient_id"]: r["cancer_type"] for r in ep_rows}

    added = 0
    for row in rr_rows:
        specialty = row["specialty"] or "2WW"
        pathway = _sp_to_pathway.get(specialty) or patient_cancer.get(
            row["patient_id"]
        ) or "lung"
        letter = _NARRATIVE_REFERRAL.get(pathway, "")
        if not letter:
            continue

        dr_id = row["dr_id"]
        # Find max ordinal for this DR
        ord_rows = client.run(
            "MATCH (dr:DocumentReference {id: $dr_id})-[r:HAS_CHUNK]->(:Chunk) "
            "RETURN max(r.ordinal) AS max_ord",
            dr_id=dr_id,
        )
        max_ord = (ord_rows[0].get("max_ord") or 0) if ord_rows else 0
        new_ord = max_ord + 1

        sha = _chunk_sha(letter)
        cid = _make_chunk_id(dr_id, new_ord, sha)

        # Skip if already added (idempotent by chunk_id)
        exists = client.run(
            "MATCH (c:Chunk {id: $cid}) RETURN count(c) AS n", cid=cid
        )
        if exists and exists[0].get("n", 0) > 0:
            continue

        char_start = 0
        client.run(
            "MATCH (dr:DocumentReference {id: $dr_id}) "
            "MERGE (c:Chunk {id: $cid}) "
            "SET c.document_reference_id = $dr_id, c.text = $text, "
            "    c.sha256 = $sha, c.char_start = $cs, c.char_end = $ce, "
            "    c.ordinal = $ordinal, c.source = $src, "
            "    c.updated_at = datetime(), "
            "    c.created_at = coalesce(c.created_at, datetime()) "
            "MERGE (dr)-[r:HAS_CHUNK]->(c) "
            "SET r.ordinal = $ordinal, r.char_start = $cs, r.char_end = $ce",
            dr_id=dr_id, cid=cid, text=letter, sha=sha,
            cs=char_start, ce=len(letter), ordinal=new_ord,
            src=_SOURCE_TAG,
        )
        added += 1
    return added


# ---------------------------------------------------------------------------
# Step 3 - Clinic response letters
# ---------------------------------------------------------------------------

def _seed_clinic_letters(client: PatientGraphClient) -> int:
    rr_rows = client.run(
        "MATCH (rr:ReferralRequest {source:'demo'})-[:FOR_PATIENT]->(p) "
        "RETURN rr.id AS rr_id, p.id AS patient_id, rr.specialty AS specialty"
    )
    _sp_to_pathway = {
        "2WW": None,
        "Cardiology": "cardiology",
        "Urology": "urology",
        "Gastroenterology": "gastroenterology",
        "Rheumatology": "rheumatology",
        "Neurology": "neurology",
        "Respiratory": "respiratory",
        "Endocrinology": "endocrinology",
        "Haematology": "haematology",
    }
    ep_rows = client.run(
        "MATCH (p:Patient {source:'demo'})-[:HAS_EPISODE_OF_CARE]->(ep) "
        "RETURN p.id AS patient_id, ep.cancer_type AS cancer_type"
    )
    patient_cancer = {r["patient_id"]: r["cancer_type"] for r in ep_rows}

    added = 0
    for row in rr_rows:
        idx = int(row["patient_id"].split("-")[-1])
        dr_id = _clinic_dr_id(idx)

        # Skip if already seeded
        exists = client.run(
            "MATCH (dr:DocumentReference {id: $id}) RETURN count(dr) AS n",
            id=dr_id,
        )
        if exists and exists[0].get("n", 0) > 0:
            continue

        specialty = row["specialty"] or "2WW"
        pathway = _sp_to_pathway.get(specialty) or patient_cancer.get(
            row["patient_id"]
        ) or "lung"
        letter = _CLINIC_LETTER.get(pathway, "")
        if not letter:
            continue

        # Create DocumentReference
        client.run(
            "MERGE (dr:DocumentReference {id: $id}) "
            "ON CREATE SET dr.title = $title, dr.type = 'clinic-letter', "
            "  dr.category = 'outpatient_letter', dr.source = $src, "
            "  dr.created_at = datetime()",
            id=dr_id,
            title=f"DEMO Clinic Letter - {specialty}",
            src=_SOURCE_TAG,
        )
        # Link to patient
        client.run(
            "MATCH (p:Patient {id: $pid}), (dr:DocumentReference {id: $dr_id}) "
            "MERGE (p)-[:HAS_DOCUMENT_REFERENCE]->(dr)",
            pid=row["patient_id"], dr_id=dr_id,
        )
        # Link from ReferralRequest
        client.run(
            "MATCH (rr:ReferralRequest {id: $rr_id}), (dr:DocumentReference {id: $dr_id}) "
            "MERGE (rr)-[:HAS_DOCUMENT]->(dr)",
            rr_id=row["rr_id"], dr_id=dr_id,
        )
        # Single chunk with the full letter
        sha = _chunk_sha(letter)
        cid = _make_chunk_id(dr_id, 1, sha)
        client.run(
            "MATCH (dr:DocumentReference {id: $dr_id}) "
            "MERGE (c:Chunk {id: $cid}) "
            "SET c.document_reference_id = $dr_id, c.text = $text, "
            "    c.sha256 = $sha, c.char_start = 0, c.char_end = $ce, "
            "    c.ordinal = 1, c.source = $src, "
            "    c.updated_at = datetime(), "
            "    c.created_at = coalesce(c.created_at, datetime()) "
            "MERGE (dr)-[r:HAS_CHUNK]->(c) "
            "SET r.ordinal = 1, r.char_start = 0, r.char_end = $ce",
            dr_id=dr_id, cid=cid, text=letter, sha=sha,
            ce=len(letter), src=_SOURCE_TAG,
        )
        added += 1
    return added


# ---------------------------------------------------------------------------
# Step 4 - Discharge summaries (cancer patients 001-035)
# ---------------------------------------------------------------------------

def _cancer_key_for_discharge(cancer_type: str | None, idx: int) -> str:
    if not cancer_type:
        return "lung"
    # breast has two templates - alternate
    if cancer_type == "breast" and idx % 2 == 0:
        return "breast_alt"
    return cancer_type


def _seed_discharge_summaries(client: PatientGraphClient) -> int:
    ep_rows = client.run(
        "MATCH (p:Patient {source:'demo'})-[:HAS_EPISODE_OF_CARE]->(ep) "
        "WHERE ep.inferred_outcome = 'cancer' "
        "RETURN p.id AS patient_id, ep.cancer_type AS cancer_type"
    )
    added = 0
    for row in ep_rows:
        idx = int(row["patient_id"].split("-")[-1])
        dr_id = _discharge_dr_id(idx)

        # Skip if already seeded
        exists = client.run(
            "MATCH (dr:DocumentReference {id: $id}) RETURN count(dr) AS n",
            id=dr_id,
        )
        if exists and exists[0].get("n", 0) > 0:
            continue

        key = _cancer_key_for_discharge(row["cancer_type"], idx)
        summary = _DISCHARGE_SUMMARY.get(key, _DISCHARGE_FALLBACK)

        client.run(
            "MERGE (dr:DocumentReference {id: $id}) "
            "ON CREATE SET dr.title = $title, dr.type = 'discharge-summary', "
            "  dr.category = 'inpatient_summary', dr.source = $src, "
            "  dr.created_at = datetime()",
            id=dr_id,
            title=f"DEMO Discharge Summary - {row['cancer_type'] or 'oncology'}",
            src=_SOURCE_TAG,
        )
        client.run(
            "MATCH (p:Patient {id: $pid}), (dr:DocumentReference {id: $dr_id}) "
            "MERGE (p)-[:HAS_DOCUMENT_REFERENCE]->(dr)",
            pid=row["patient_id"], dr_id=dr_id,
        )
        sha = _chunk_sha(summary)
        cid = _make_chunk_id(dr_id, 1, sha)
        client.run(
            "MATCH (dr:DocumentReference {id: $dr_id}) "
            "MERGE (c:Chunk {id: $cid}) "
            "SET c.document_reference_id = $dr_id, c.text = $text, "
            "    c.sha256 = $sha, c.char_start = 0, c.char_end = $ce, "
            "    c.ordinal = 1, c.source = $src, "
            "    c.updated_at = datetime(), "
            "    c.created_at = coalesce(c.created_at, datetime()) "
            "MERGE (dr)-[r:HAS_CHUNK]->(c) "
            "SET r.ordinal = 1, r.char_start = 0, r.char_end = $ce",
            dr_id=dr_id, cid=cid, text=summary, sha=sha,
            ce=len(summary), src=_SOURCE_TAG,
        )
        added += 1
    return added


# ---------------------------------------------------------------------------
# Guard / teardown
# ---------------------------------------------------------------------------

def _already_seeded(client: PatientGraphClient) -> bool:
    rows = client.run(
        "MATCH (e:Encounter {id: 'demo-enc-001-referral'}) "
        "WHERE e.text STARTS WITH '62-year-old' RETURN count(e) AS n"
    )
    return bool(rows and rows[0].get("n", 0) > 0)


def _teardown(client: PatientGraphClient) -> None:
    # Reset encounter text
    client.run(
        "MATCH (e:Encounter) WHERE e.id STARTS WITH 'demo-enc-' "
        "AND e.source = 'demo' "
        "SET e.text = 'Demo encounter'"
    )
    # Remove narrative chunks and new DRs
    client.run(
        "MATCH (c:Chunk {source: $src}) DETACH DELETE c",
        src=_SOURCE_TAG,
    )
    client.run(
        "MATCH (dr:DocumentReference {source: $src}) DETACH DELETE dr",
        src=_SOURCE_TAG,
    )
    print("  [OK] Clinical text content removed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    force = "--force" in sys.argv
    teardown_only = "--teardown" in sys.argv

    client = PatientGraphClient()
    try:
        if teardown_only:
            print("Removing clinical text content...")
            _teardown(client)
            return

        if _already_seeded(client):
            if not force:
                print(
                    "Clinical text already seeded. "
                    "Use --force to re-seed or --teardown to remove."
                )
                return
            print("--force: removing existing clinical text content...")
            _teardown(client)

        print(f"\n{'='*60}")
        print("ADDING FREE-TEXT CLINICAL CONTENT")
        print(f"{'='*60}")

        n = _update_encounter_text(client)
        print(f"  [OK] Step 1: {n} encounter notes updated")

        n = _add_narrative_chunks(client)
        print(f"  [OK] Step 2: {n} narrative referral letter chunks added")

        n = _seed_clinic_letters(client)
        print(f"  [OK] Step 3: {n} outpatient clinic response letters created")

        n = _seed_discharge_summaries(client)
        print(f"  [OK] Step 4: {n} discharge summaries created")

    finally:
        client.close()

    print(f"\n{'='*60}")
    print("DONE - clinical text layers seeded")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
