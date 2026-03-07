"""Few-shot example library for the episode builder and consolidation prompts.

Each example has:
  input       -- coded summary / episode summaries fed to the prompt
  output      -- expected JSON result
  category    -- pattern demonstrated
  model_scope -- "any" | "aws" | "azure"
  description -- short human-readable label for the Admin UI

Category taxonomy:
  episode:confirmed          -- cancer diagnosis confirmed with clear evidence
  episode:confirmed-inferred -- cancer inferred from treatment (no explicit diagnosis text)
  episode:excluded           -- cancer ruled out via negative investigation
  episode:inconclusive       -- insufficient evidence; ambiguous pathway
  consolidation:merge        -- two episodes are the same cancer journey (should_merge=true)
  consolidation:no-merge     -- episodes represent genuinely separate cancers (should_merge=false)
"""

from __future__ import annotations

EPISODE_BUILDER_EXAMPLES: list[dict] = [
    # ── Episode: confirmed ────────────────────────────────────────────────────
    {
        "category": "episode:confirmed",
        "model_scope": "any",
        "description": "Biopsy confirms breast cancer with treatment started",
        "input": (
            "Episode ID: ep-001\nCancer type: breast\nEntry type: referral\n"
            "Entry date: 2023-04-10\n\n"
            "Coded data:\n"
            "- 2023-04-10 (enc-01): Fast track referral for suspected breast cancer\n"
            "- 2023-05-02 (enc-04): Biopsy confirmed invasive ductal carcinoma\n"
            "- 2023-05-14 (enc-06): Started letrozole"
        ),
        "output": '{"status": "confirmed", "confidence": 95, "reasoning": "Biopsy on 2023-05-02 confirmed invasive ductal carcinoma; letrozole started 2023-05-14 confirms treatment.", "diagnosis_date": "2023-05-02", "treatment_date": "2023-05-14"}',
    },
    {
        "category": "episode:confirmed",
        "model_scope": "any",
        "description": "MDT outcome confirms colorectal cancer",
        "input": (
            "Episode ID: ep-007\nCancer type: colorectal\nEntry type: referral\n"
            "Entry date: 2022-09-05\n\n"
            "Coded data:\n"
            "- 2022-09-05 (enc-01): 2WW referral to lower GI surgery — change in bowel habit\n"
            "- 2022-10-18 (enc-05): Colonoscopy: T3 adenocarcinoma sigmoid colon\n"
            "- 2022-10-25 (enc-06): MDT outcome: sigmoid colectomy planned\n"
            "- 2022-11-10 (enc-08): Sigmoid colectomy performed"
        ),
        "output": '{"status": "confirmed", "confidence": 98, "reasoning": "Colonoscopy on 2022-10-18 confirmed T3 adenocarcinoma; MDT decision and surgical treatment on 2022-11-10 corroborate.", "diagnosis_date": "2022-10-18", "treatment_date": "2022-11-10"}',
    },

    # ── Episode: confirmed-inferred ───────────────────────────────────────────
    {
        "category": "episode:confirmed-inferred",
        "model_scope": "any",
        "description": "Cancer inferred from cancer-specific chemotherapy (no explicit diagnosis text)",
        "input": (
            "Episode ID: ep-012\nCancer type: haematological\nEntry type: referral\n"
            "Entry date: 2021-11-20\n\n"
            "Coded data:\n"
            "- 2021-11-20 (enc-01): 2WW referral to haematology — lymphadenopathy\n"
            "- 2022-01-08 (enc-05): Letter from haematology filed\n"
            "- 2022-01-15 (enc-06): First cycle CHOP chemotherapy commenced\n"
            "- 2022-03-10 (enc-09): Ongoing CHOP — cycle 4"
        ),
        "output": '{"status": "confirmed", "confidence": 82, "reasoning": "No explicit diagnosis text present, but CHOP chemotherapy is cancer-specific treatment indicating confirmed haematological malignancy. Diagnosis inferred at earliest treatment encounter.", "diagnosis_date": "2022-01-08", "treatment_date": "2022-01-15"}',
    },

    # ── Episode: excluded ─────────────────────────────────────────────────────
    {
        "category": "episode:excluded",
        "model_scope": "any",
        "description": "Benign biopsy result after 2WW referral",
        "input": (
            "Episode ID: ep-021\nCancer type: skin\nEntry type: referral\n"
            "Entry date: 2023-07-03\n\n"
            "Coded data:\n"
            "- 2023-07-03 (enc-01): Fast track referral to dermatology — suspicious pigmented lesion\n"
            "- 2023-07-24 (enc-03): Seen in fast track suspected skin cancer clinic\n"
            "- 2023-08-10 (enc-05): Biopsy result: benign intradermal naevus — no malignancy\n"
            "- 2023-08-10 (enc-05): Discharged from 2WW pathway"
        ),
        "output": '{"status": "excluded", "confidence": 97, "reasoning": "Biopsy on 2023-08-10 confirmed benign intradermal naevus with no malignancy; patient discharged from 2WW pathway.", "diagnosis_date": null, "treatment_date": null}',
    },
    {
        "category": "episode:excluded",
        "model_scope": "any",
        "description": "Colonoscopy NAD after positive FIT",
        "input": (
            "Episode ID: ep-035\nCancer type: colorectal\nEntry type: referral\n"
            "Entry date: 2023-02-14\n\n"
            "Coded data:\n"
            "- 2023-02-14 (enc-01): Positive FIT result — 2WW referral lower GI\n"
            "- 2023-03-20 (enc-04): Colonoscopy — no polyps, no cancer detected, NAD\n"
            "- 2023-03-20 (enc-04): No evidence of colorectal cancer"
        ),
        "output": '{"status": "excluded", "confidence": 94, "reasoning": "Colonoscopy on 2023-03-20 found no polyps or cancer. NAD recorded with explicit no evidence of colorectal cancer.", "diagnosis_date": null, "treatment_date": null}',
    },

    # ── Episode: inconclusive ─────────────────────────────────────────────────
    {
        "category": "episode:inconclusive",
        "model_scope": "any",
        "description": "Awaiting biopsy results - no outcome yet",
        "input": (
            "Episode ID: ep-044\nCancer type: prostate\nEntry type: referral\n"
            "Entry date: 2023-10-05\n\n"
            "Coded data:\n"
            "- 2023-10-05 (enc-01): 2WW referral urology — PSA 18.4\n"
            "- 2023-11-12 (enc-03): Seen in prostate cancer clinic — MRI prostate ordered\n"
            "- 2023-12-01 (enc-05): MRI showed suspicious lesion — TRUS biopsy planned\n"
            "- 2023-12-20 (enc-07): Awaiting biopsy results"
        ),
        "output": '{"status": "inconclusive", "confidence": 35, "reasoning": "Suspicious MRI lesion warrants high suspicion but biopsy results are pending; no confirmed diagnosis or exclusion.", "diagnosis_date": null, "treatment_date": null}',
    },

    # ── Consolidation: merge ──────────────────────────────────────────────────
    {
        "category": "consolidation:merge",
        "model_scope": "any",
        "description": "Urology and lower GI episodes both investigating same renal mass",
        "input": (
            "Patient ep-A has 2 episodes created within 21 days.\n\n"
            "Episode ep-A1: cancer_type=colorectal, status=excluded, confidence=45, "
            "referral_date=2022-08-10, reasoning='Positive FIT triggered lower GI referral. "
            "Colonoscopy NAD. However CT abdomen incidentally found large right renal mass.'\n\n"
            "Episode ep-A2: cancer_type=renal, status=confirmed, confidence=88, "
            "referral_date=2022-08-20, reasoning='Renal mass on CT confirmed as renal cell carcinoma "
            "on biopsy. Nephrectomy planned.'"
        ),
        "output": '{"should_merge": true, "primary_episode_id": "ep-A2", "reasoning": "Both episodes stem from the same FIT-triggered investigation. CT incidentally found the renal tumour; lower GI pathway was a red herring. Renal episode (ep-A2) is the actual cancer site with confirmed histology and planned treatment.", "merged_cancer_type": "renal"}',
    },
    {
        "category": "consolidation:merge",
        "model_scope": "any",
        "description": "Urology refers to haematology during same investigation pathway",
        "input": (
            "Patient ep-B has 2 episodes created within 14 days.\n\n"
            "Episode ep-B1: cancer_type=urology, status=inconclusive, confidence=50, "
            "referral_date=2023-03-01, reasoning='Haematuria referral. Cystoscopy normal. "
            "CT urogram showed retroperitoneal lymphadenopathy. Urology liaised with haematology.'\n\n"
            "Episode ep-B2: cancer_type=haematological, status=confirmed, confidence=91, "
            "referral_date=2023-03-10, reasoning='Lymph node biopsy confirmed diffuse large B-cell lymphoma. "
            "CHOP commenced.'"
        ),
        "output": '{"should_merge": true, "primary_episode_id": "ep-B2", "reasoning": "Urological haematuria referral led to discovery of retroperitoneal lymphadenopathy; urology explicitly referred to haematology. Haematological episode (ep-B2) is the actual cancer with confirmed DLBCL and treatment.", "merged_cancer_type": "haematological"}',
    },

    # ── Consolidation: no-merge ───────────────────────────────────────────────
    {
        "category": "consolidation:no-merge",
        "model_scope": "any",
        "description": "Genuinely separate cancers - skin and lung diagnosed months apart",
        "input": (
            "Patient ep-C has 2 episodes created within 400 days.\n\n"
            "Episode ep-C1: cancer_type=skin, status=confirmed, confidence=96, "
            "referral_date=2021-06-15, reasoning='Melanoma confirmed on biopsy. Wide local excision performed.'\n\n"
            "Episode ep-C2: cancer_type=lung, status=confirmed, confidence=94, "
            "referral_date=2022-07-20, reasoning='New cough and haemoptysis. CT chest: right upper lobe mass. "
            "Bronchoscopy biopsy: squamous cell carcinoma. Referred to thoracic oncology.'"
        ),
        "output": '{"should_merge": false, "primary_episode_id": "ep-C1", "reasoning": "Skin melanoma and lung SCC are anatomically unrelated cancers with independent diagnostic workups 13 months apart. These are separate malignancies with no shared investigation pathway.", "merged_cancer_type": null}',
    },
]
