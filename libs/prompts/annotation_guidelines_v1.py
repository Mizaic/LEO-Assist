"""Shared annotation guidelines for reviewer and LLM alignment.

Atlas trace:
  DO: DO-54397CCD
  Also implements: DO-8620A68B
  DI: DI-5A802C83, DI-6EFD68D0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-54397CCD")
"""

from __future__ import annotations

ANNOTATION_GUIDELINES_V1 = """\
## Shared annotation guidelines

Objective: keep human review, extraction, and verification labels clinically
consistent without changing the caller's output schema.

Priorities: preserve approved gold labels first; keep clinical state in the
assertion field; use only the approved labels and relation types below.

Apply these rules when reviewing, extracting, or checking any annotation.
Lines starting with >> show real gold-verified span examples:
"text" | label | assertion | SNOMED code.

1) Use the assertion field to show clinical state - not a different label.
   The label type tells you WHAT something is. The assertion tells you
   whether it happened, was planned, is absent, or is uncertain.
   Same procedure - two different assertions. The label stays the same.
   >> biopsy | procedure | planned | SNOMED: 86273004
   >> biopsy | procedure | absent | SNOMED: 86273004

2) Medical actions stay "procedure" even if they did not happen.
   If a phrase names something a doctor does or orders, use "procedure".
   It does not matter if it was planned, historical, or never happened.
   >> colonoscopy | procedure | planned | SNOMED: 73761001
   >> Mammogram | procedure | absent | SNOMED: 71651007
   >> chemo/ | procedure | historical | SNOMED: 367336001
   >> Liver function tests (XE28K) | procedure | present | SNOMED: 26958001
   >> Magnetic resonance imaging of lumbar spine (X70pF) | procedure | present | SNOMED: 241648005
   >> MRI of prostate (X70or) | procedure | present | SNOMED: 75691003
   >> Wide local excision of breast lesion (X40EC) | procedure | present | SNOMED: 237371007

3) Use "situation" for clinical context, suspicion, and family history.
   If a phrase describes a patient's status, suspected diagnosis, or
   family background rather than a direct action, use "situation".
   >> suspected lower GI cancer | situation | present | SNOMED: 315274008
   >> FH of breast cancer | situation | present | SNOMED: 429740004
   >> no cancer present | situation | present | SNOMED: 395100000

4) Keep all labels when a phrase has more than one correct label.
   Fast-track cancer referrals name both an action and a clinical status.
   They are correctly labelled as both "procedure" and "situation".
   Measured clinical parameters often have both observable_entity and procedure.
   >> Fast track referral for suspected lower GI cancer | procedure | present | SNOMED: 892201000000106
   >> suspected lower GI cancer | situation | present | SNOMED: 315274008
   >> blood pressure reading (246..)108/69 | observable_entity | present | SNOMED: 75367002
   >> blood pressure | procedure | present | SNOMED: 46973005
   >> pulse rate (242..) 67 bpm | observable_entity | present | SNOMED: 78564009
   >> pulse rate (242..) | procedure | present | SNOMED: 65653002
   >> temperature (XaBzA) 36.9 degC | observable_entity | present | SNOMED: 386725007
   >> temperature (XaBzA) | procedure | present | SNOMED: 56342008
   >> Body mass index 17.68 Kg/m | observable_entity | present | SNOMED: 60621009
   >> Body mass index | procedure | present | SNOMED: 698094009

5) Always keep labels that a gold reviewer has already approved.
   If a reviewer signed off a dual label or an unusual choice, trust it.
   Example: "Fast track referral for suspected head and neck cancer"
   was gold-approved as both procedure (280521000000108)
   and situation (315277001). Keep both labels as approved.

6) Common treatment words are usually "procedure".
   Chemo, chemotherapy, and radiotherapy normally get "procedure".
   Use "regime_therapy" only when the phrase names a specific therapy
   class or regimen - not just a single treatment mention.
   >> chemo/ | procedure | historical | SNOMED: 367336001
   >> radiotherapy | procedure | historical | SNOMED: 1287742003
   >> slgt2 | regime_therapy | present | SNOMED: 2570481000000109

7) Negation and tense do not change the label type.
   If something is negated, in the past, or uncertain, keep the same
   label type. Only the assertion field changes.
   >> Mammogram | procedure | absent | SNOMED: 71651007
   >> chest pain | finding | absent | SNOMED: 29857009
   >> aggressive bone cancers | disorder | absent | SNOMED: 94222008

8) Only use approved relation types. Do not create new ones.
   Findings and procedures can link to body structures via "finding_site".
   Qualifiers link to the thing they describe via "qualifies".
   Keep all valid body-site links even when there are several.
   Example: "breast lump" (finding/89164003) links via finding_site
   to "Left breast" (body_structure/80248007).
   Example: "benign" (qualifier_value/30807003) links via qualifies
   to "seborrhoeic keratosis" (disorder/394726009).
   >> sweating | finding | present | SNOMED: 415690000
      relates via "qualifies" to "with physical exertion"
   >> increased internal temperature | finding | present | SNOMED: 105723007
      relates via "qualifies" to "with physical exertion"

9) Lab results above or below the reference range get two spans: the
   measured value (observable_entity) and the interpretation (finding).
   >> Mean cell volume (42A..) 100 fL | observable_entity | present | SNOMED: 1022491000000106
   >> Mean cell volume (42A..) 100 fL [80 - 99] - Outside reference range | finding | present | SNOMED: 165454002
   >> Mean cell haemoglobin level (XE2pb) 32.1 pg | observable_entity | present | SNOMED: 1022471000000107
   >> Mean cell haemoglobin level (XE2pb) 32.1 pg [27 - 32] - Outside reference range | finding | present | SNOMED: 165442002

10) Smoking and lifestyle status are "finding", not "situation".
    Smoking status, vaping, BMI range interpretation, and similar
    lifestyle findings use label "finding" with assertion "present".
    >> Ex-smoker | finding | present | SNOMED: 8517006
    >> Vapes | finding | present | SNOMED: 35361000087100
    >> Never Smoked | finding | present | SNOMED: 266919005
    >> overweight | finding | present | SNOMED: 238131007
    Smoking assessments and weighing procedures stay "procedure".
    >> Smoking History | procedure | present | SNOMED: 196771000000101
    >> Smoking assessment | procedure | present | SNOMED: 196771000000101
    Numeric weight, height, and BMI results are "observable_entity",
    not procedure. Put the name, value, and unit on one observable.
    >> Current weight | observable_entity | present | value=67 unit=kg
    >> Height | observable_entity | present | value=1.67 unit=m
    >> BMI | observable_entity | present | value=24.0 unit=kg/m2
"""
