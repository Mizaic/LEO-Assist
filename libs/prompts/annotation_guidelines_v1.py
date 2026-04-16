"""Shared annotation guidelines for reviewer and LLM alignment."""

from __future__ import annotations

ANNOTATION_GUIDELINES_V1 = """\
## Shared annotation guidelines

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

3) Use "situation" for clinical context, suspicion, and family history.
   If a phrase describes a patient's status, suspected diagnosis, or
   family background rather than a direct action, use "situation".
   >> suspected lower GI cancer | situation | present | SNOMED: 315274008
   >> FH of breast cancer | situation | absent | SNOMED: 429740004
   >> no cancer present | situation | present | SNOMED: 395100000

4) Keep all labels when a phrase has more than one correct label.
   Fast-track cancer referrals name both an action and a clinical status.
   They are correctly labelled as both "procedure" and "situation".
   >> Fast track referral for suspected lower GI cancer | procedure | present | SNOMED: 892201000000106
   >> suspected lower GI cancer | situation | present | SNOMED: 315274008

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
"""
