# Episode Fragmentation - Pre-Fix Snapshot

Captured: 2026-04-16
Graph: dev patient graph (`neo4j+s://c38426e1.databases.neo4j.io`)
Purpose: baseline metrics for verifying the 4-phase episode-builder fix
(DI-LEO-AI-136, DI-LEO-AI-137, DI-LEO-AI-138).

---

## Headline issue

The NCDA audit dashboard reports 91 confirmed cancer episodes in 2025, of
which only 16 (17.6%) have a documented 2WW referral milestone. Real-world
2WW rates across UK primary care are ~50-60% per NCDA national data. The
gap is a combination of episode over-fragmentation and strict referral
site-matching (see DI-LEO-AI-136, DI-LEO-AI-137).

---

## All-time graph totals

| Metric | Value |
|---|---|
| Total `EpisodeOfCare` nodes | 399 |
| Distinct patients with any episode | 101 |
| `status = completed` | 179 |
| `status = merged` | 29 |
| `status = stale_no_diagnosis` | 34 |
| `status = in_progress` | 26 |

## 2025 `referral_date` cohort (any status)

| Metric | Value |
|---|---|
| Episodes | 235 |
| Distinct patients | 91 |
| `status = completed` | 92 |
| `status = completed AND NOT letter_inferred_benign` | 92 |

## 2025 canonical confirmed cancer cohort

Per `confirmed_cancer_where` helper (completed + not benign + has
diagnosis/diagnosis_confirmed milestone encounter):

| Metric | Value |
|---|---|
| Canonical confirmed episodes | 91 |
| Distinct patients behind those 91 | 60 |
| Episodes per patient (mean) | 1.52 |
| With documented 2WW referral milestone | 16 |
| 2WW rate | 17.6% |

### 2025 episodes-per-patient distribution (fragmentation indicator)

| Eps per patient | Patients |
|---|---|
| 1 | 39 |
| 2 | 13 |
| 3 | 6 |
| 4 | 2 |

21 of 60 patients (35%) have more than one canonical confirmed-cancer
episode in 2025. Most of these are over-fragmentation artefacts, not
genuine multi-primary cancers.

### 2025 by cancer_type

| Cancer type | n |
|---|---|
| breast | 22 |
| unknown | 10 |
| melanoma | 8 |
| bladder | 7 |
| head_and_neck | 6 |
| colorectal | 5 |
| sarcoma | 5 |
| leukaemia | 4 |
| non_site_specific | 4 |
| lymphoma | 3 |
| liver | 3 |
| prostate | 3 |
| myeloma | 2 |
| endometrial | 2 |
| ovarian | 2 |
| cervical | 1 |
| oesophageal | 1 |
| renal | 1 |
| upper_gi | 1 |
| lung | 1 |

### 2025 per month

| Month | Total | Via 2WW |
|---|---|---|
| 2025-01 | 10 | 2 |
| 2025-02 | 8 | 2 |
| 2025-03 | 9 | 1 |
| 2025-04 | 6 | 1 |
| 2025-05 | 11 | 1 |
| 2025-06 | 13 | 4 |
| 2025-07 | 11 | 4 |
| 2025-08 | 11 | 1 |
| 2025-09 | 4 | 0 |
| 2025-10 | 3 | 0 |
| 2025-11 | 2 | 0 |
| 2025-12 | 3 | 0 |

## 2024 canonical confirmed cancer cohort (secondary baseline)

| Metric | Value |
|---|---|
| Canonical confirmed episodes | 84 |
| Distinct patients | 46 |
| Episodes per patient (mean) | 1.83 |
| With documented 2WW referral milestone | 17 |
| 2WW rate | 20.2% |

---

## Fragmentation evidence

Cross-check classification of the 91 confirmed-cancer 2025 episodes:

| Classification | Count |
|---|---|
| Has referral milestone on this episode | 16 |
| No referral milestone on this episode, but patient has one on a different episode | 61 |
| Patient has no referral milestone on any episode | 14 |

Of the 14 "genuinely unreferred", 7 (50%) are breast - consistent with
the known tight `breast` regex missing triple-assessment / fibroadenoma
follow-up language.

## Post-fix expected ranges (to be verified in Phase 5)

- Canonical confirmed episodes 2025: 91 -> 60-70
- Episodes per patient (mean) 2025: 1.52 -> ~1.05
- Via 2WW 2025: 16 -> 40-55 (44-60% rate)
- Breast-specific unreferred (14 of 91): 7 breast subset should drop to
  2-3 genuine cases after marker broadening.
