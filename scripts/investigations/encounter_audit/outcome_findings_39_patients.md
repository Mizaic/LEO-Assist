# Outcome Findings -- 39 All-Open Patients
# Manual encounter review completed 2026-04-06

## Summary Counts

| Category | Count | Patients |
|----------|-------|---------|
| Cancer confirmed -- episode should close | 3 | 4300102074, 4920262426, 6517334858 (2025 BCC) |
| Benign outcome -- 395100000 not yet coded | 12 | see table below |
| Benign outcome -- already partially coded, episode logic gap | 5 | 6519337463, 6268086643, 4245139757, 4246627143, 4983118659 (ep2) |
| Declined / DNA -- episode should close | 2 | 6263830379, 7326304955 |
| Genuinely open -- awaiting results | 2 | 4866772573, 7322946243 |
| No outcome in GP record (letter not ingested) | 9 | 4202339649, 4247682105, 4622879921, 4998540637, 6509504022, 7011988319, 7028414914, 4926887169, 6507904570 |
| Complex / episode site wrong | 6 | see episode-site table |

---

## A -- Cancer Confirmed (need diagnosis anchor to link to episode)

| Patient | Site | Diagnosis | Key evidence phrase |
|---------|------|-----------|---------------------|
| 4300102074 | breast | Malignant breast mass | "features of tethered malignant L inner breast mass with associated microcalcifications"; Letrozole started |
| 4920262426 | breast | DCIS left breast | "Intraductal carcinoma in situ of breast (X78WW) - Left" |
| 6517334858 | skin | Basal cell carcinoma (2025-05-13) | "Basal cell carcinoma (morphologic abnormality)" -- also older skin 2WW (2020) no histology in records |

**Root cause to investigate**: The diagnosis concepts are coded in Neo4j but not detected as `diagnosis` type anchors by the anchor_detector. Likely a domain ValueSet IS_A expansion gap (DCIS, BCC, specific breast malignancy subtypes not descended from the parent concept).

---

## B -- Benign Outcome: 395100000 Not Coded (need write-back)

| Patient | Site | Referral date | Encounter date for write-back | Key outcome phrase |
|---------|------|---------------|-------------------------------|-------------------|
| 4621680811 | haematological | 2025-05-30 | 2025-07-08 | "seen by haem- nil concerns raised about malig ... will likely be discharged" |
| 7343840665 | children's tumour | 2024-09-16 | 2024-11-20 | "Was seen on 2WW, nad so safe to administer live vaccine" |
| 7330683205 | upper_gi | 2025-07-28 | 2025-08-04 | "has had OGD - shows small hiatus hernia only" |
| 4883794091 | upper_gi | 2025-07-11 | 2025-07-17 | "Had endoscopy yearday which was normal. Paper report seen." |
| 4866803525 | head_and_neck | 2025-02-18 | 2025-03-13 | "Presbyacusis" + ENT discharge; no malignancy found |
| 4808735946 | lower_gi | 2025-04-15 | 2025-05-27 | "Tubular adenoma - colonic - excised 01/05/25" (non-malignant) |
| 6519712760 | lower_gi | 2024-11-18 | 2024-12-29 | "Haemorrhoid" confirmed on colonoscopy (non-malignant bleeding cause) |
| 7319972905 | head_and_neck | 2025-06-12 | 2025-06-25 | "US scan of neck - NAD" + "US scan of thyroid - mildly enlarged, otherwise NAD" |
| 4983118659 | upper_gi | 2025-02-04 | 2025-03-06 | "no dysplasia or malignancy" (ICE result for OGD biopsy) |
| 7321643565 (haem ep) | haematological | 2025-03-18 | 2025-03-22 | "colonoscopy - polyp removed but no cancer" |
| 4246428337 | lower_gi | 2025-07-30 | 2025-08-11 | "Ulcerative colitis" (alternative benign diagnosis from colonoscopy) |
| 4185994966 | head_and_neck | 2024-12-04 | 2025-01-24 | "Seen in fast track H&N clinic" -- globus/thyroid, no malignancy; also breast pathway -> "Fibroadenoma" |

---

## C -- Benign Outcome: Partially Coded (episode logic gap)

These patients have benign outcomes coded in the graph (imaging normal, fibroadenoma, etc.) but the episode_builder does not close the episode because `395100000` is not present within the 365-day window, or the benign concept is not in the `no_cancer_discharge` ValueSet.

| Patient | Site | What is coded | Why episode stays open |
|---------|------|---------------|------------------------|
| 6519337463 | breast | "Benign pathology found (situation)", "Fibroadenoma", "Discharge from breast surgery service" | 395100000 may not be coded; episode_builder only looks for 395100000 |
| 6268086643 | breast | "Mammography normal", "US scan of breast normal" | Imaging normal concepts not in benign_closure ValueSet |
| 4245139757 | NSS + lower_gi | "Colonoscopy normal" coded | 395100000 may not be coded in SNOMED |
| 4246627143 | NSS (actually breast) | Breast cyst, aspiration coded | 395100000 not coded; site classification wrong (NSS vs breast) |
| 4983118659 ep2 | NSS (actually breast) | "Mammography normal", "US scan of breast - R - normal" | 395100000 not coded; site wrong (NSS vs breast) |

**Action**: Add these patients to write-back list. Also consider adding "Benign pathology found" and similar concepts to the `no_cancer_discharge` ValueSet.

---

## D -- Declined / DNA (episode should close as declined)

| Patient | Site | Evidence |
|---------|------|---------|
| 6263830379 | urological | "Patient no longer wants the appointment, symptoms have been resolved. Off"; "discharge her from care as declined investigations" |
| 7326304955 | breast | "Patient DNA'd x 2"; "Did not attend fast track suspected cancer clinic: Yes"; referral rejected |

**Action**: These episodes should be closed as `declined` or `closed_patient_withdrew`. The current episode_builder has no `declined` status. Either add this status or annotate these episodes manually.

---

## E -- Genuinely Open (await results)

| Patient | Site | Referral | Why open |
|---------|------|----------|----------|
| 4866772573 | urological | 2025-01-20 | PIRADS 4+3, transperineal biopsies Feb 2025 and Oct 2025 -- no histology result in records yet. Acute retention, catheter Oct 2025. Genuinely awaiting. |
| 7322946243 | breast (NSS) | 2025-03-06 | Excisional biopsy of breast 2025-08-11, no histology phrase in records. |

---

## F -- No Outcome in GP Record

Letters likely in Docman/TIF attachments not ingested as free text. No surface form or write-back can help; records need manual review or letter ingestion.

| Patient | Site | Referral | Evidence |
|---------|------|----------|---------|
| 4202339649 | skin | 2021-06-15 | Seen in 2WW skin clinic 2021-07-06 but letter body not in free text (header only) |
| 4247682105 | breast | 2022-03-02 | Seen in breast clinic 2022-03-16 but no letter body |
| 4622879921 | breast | 2014-09-09 | Letters exist as TIF attachments only |
| 4998540637 | lung | 2025-03-21 | Seen in 2WW lung clinic 2025-03-31 but no result letter body |
| 6509504022 | breast | 2022-07-27 | Seen in clinic 2022-07-29 but no letter body in records |
| 7011988319 | haematological | 2024-12-19 | CT and 2WW seen, no staging result letter body. FBC normal but no lymphoma exclusion phrase |
| 7028414914 | head_and_neck | 2025-03-19 | Seen in 2WW H&N clinic 2025-05-06, maxillofacial letters referenced but no body |
| 4926887169 | lower_gi | 2025-02-14 | CT colonography done 2025-03-14 but no result phrase in records |
| 6507904570 | head_and_neck | 2025-05-30 | Administrative "Discharged From Care" without clinic letter body |

---

## G -- Episode Site Classification Errors

| Patient | Recorded site | Actual site | Evidence |
|---------|---------------|-------------|---------|
| 4246627143 | non_site_specific | breast | Entire narrative is breast 2WW (twice) |
| 4983118659 ep1 | lower_gi | upper_gi | OGD / gastric biopsy done, upper GI clinic seen |
| 4983118659 ep2 | non_site_specific | breast | Breast clinic + normal mammogram + normal USS |
| 7313758405 | non_site_specific | breast (then gynae) | Opening activity is breast 2WW Jan 2025, then gynae 2WW Oct 2025 |
| 7321643565 ep1 | breast | lower_gi | Seen in colorectal clinic, colonoscopy, haemorrhoids + adenoma |
| 7322946243 | non_site_specific | breast | Seen in fast track suspected breast cancer clinic; excisional biopsy left breast |
| 6507904570 ep1 | breast | head_and_neck | Thyroid/dysphagia/ENT presentation; breast 2WW code was an error |

**Root cause**: Site classification comes from the anchor_detector's referral concept. Wrong concept coded at referral (e.g. breast 2WW code on a head-and-neck presentation).

---

## H -- Additional Patients Without Complete Review (other episodes from 39)

| Patient | Notes |
|---------|-------|
| 4220526579 | Gynae pathway benign (USS NAD, HPV neg); breast pathway benign (lipoma). Both partially coded. Write-back 395100000 to tie outcomes to episodes. |
| 4245132175 | Gynae pathway: hysteroscopy + endometrial biopsy done, no histology result in records. |
| 6264541699 | PSA surveillance pathway. "Annual PSA check per letter" -- no cancer. Malignant neoplasm suspected concept may have been left as current. |
| 6280880796 | Upper GI: "iron pill gastritis" from biopsy. Benign. Wrong colorectal 2WW "seen" code also present (data integrity issue). Write-back 395100000. |
| 6519337463 | Breast benign (fibroadenoma). Benign pathology found coded but 395100000 missing. |
| 4822890058 | H&N 2WW: endocrine follow-up (thyrotoxicosis), no malignancy found. referral_date missing from EpisodeOfCare node despite ref=2025-01-22. |

---

## New Surface Forms Needed (phrases -> 395100000)

| Phrase | SNOMED target | Source patient(s) |
|--------|---------------|-------------------|
| "no dysplasia or malignancy" | 395100000 | 4983118659 |
| "nil concerns raised about malig" | 395100000 | 4621680811 |
| "no evidence of malignancy found on investigations" | 395100000 | 4245139757 |
| "cancer pathway has been completed with no cancer found" | 395100000 | 4245139757 |
| "reassured that the two-week wait cancer pathway has been completed with no cancer found" | 395100000 | 4245139757 |
| "no cancer found" | 395100000 | multiple |
| "no sinister findings" | 395100000 | 4245139757 |
| "was seen on 2ww, nad" | 395100000 | 7343840665 |
| "nad on 2ww" | 395100000 | 7343840665 |
| "no malignancy found" | 395100000 | general |
| "colonoscopy - polyp removed but no cancer" | 395100000 | 7321643565 |
| "biopsy negative for malignancy" | 395100000 | general |
| "no malignancy on biopsy" | 395100000 | general |
| "small hiatus hernia only" | 395100000 | 7330683205 (context: cancer 2WW) |
| "endoscopy which was normal" | 395100000 | 4883794091 (context: cancer 2WW) |
| "benign pathology found" | 395100000 | 6519337463 |
| "colonoscopy with biopsy - normal" | 395100000 | 7321643565 |
| "biopsy of colon - normal" | 395100000 | 7321643565 |

---

## Prompt Updates Needed

1. **Benign outcome extraction**: When a letter from a secondary care specialist describes a normal investigation result in the context of a cancer referral pathway, extract `No evidence of cancer found` (395100000) even when the exact phrase is not used. Examples: "endoscopy normal", "NAD on 2WW", "no concerns raised about malignancy".

2. **Alternative diagnosis as benign closure**: When the outcome of a cancer 2WW is an alternative benign diagnosis (ulcerative colitis, haemorrhoids, hiatus hernia, presbycusis, adenoma excised), extract `No evidence of cancer found` (395100000) as a co-occurring finding.

3. **OCR / letter attachment text**: When a letter header is present but body is missing, note in the extraction that outcome is unavailable (avoid inventing results).
