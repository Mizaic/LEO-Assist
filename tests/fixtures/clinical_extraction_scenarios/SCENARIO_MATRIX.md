# Clinical Extraction Scenario Matrix

Traceability: UN-89E2AE36, VAL-87173594, VT-29880CC8.

This matrix tracks the template-backed V1 Markdown corpus for phrase-level extraction validation.
All cases are synthetic, de-identified, and marked draft_for_clinician_approval until a clinician signs off the Markdown and expected strings.

## Coverage Summary

- Total cases: `97`
- Rendered referral templates: `20`

### Formats

- `email_request`: 10
- `referral_form_markdown`: 41
- `referral_letter`: 26
- `semi_structured_note`: 20

### Sites

- `brain_cns`: 5
- `breast`: 6
- `gynaecology`: 6
- `haematology`: 6
- `head_and_neck`: 7
- `lower_gi`: 21
- `lung`: 9
- `non_site_specific`: 11
- `prostate`: 4
- `sarcoma`: 4
- `skin`: 6
- `upper_gi`: 6
- `urology`: 6

### Difficulty Tags

- `abbreviation`: 12
- `age_context`: 1
- `ambiguous_phrase`: 3
- `boilerplate_footer`: 3
- `checkbox_field_label`: 17
- `dense_paragraph`: 9
- `family_history_context`: 1
- `fit_surface_form_variant`: 14
- `historical_context`: 1
- `incomplete_form`: 2
- `lab_vitals_row`: 9
- `negative_phrase`: 17
- `ng12_investigation_bundle`: 4
- `ng12_table_row`: 15
- `pathway_split`: 1
- `placeholder_noise`: 3
- `planned_cancelled_context`: 2
- `repeated_phrase`: 4
- `simple_sentence`: 3
- `staging_scale`: 1
- `surface_form_gap`: 4
- `template_dense_form`: 17

### Scenario Template Sources

- `20230523_eoe_usc_proforma_lower_gi_final_v6_1.md`: 1
- `20250319_eoe_usc_proforma_ugi_002.md`: 2
- `2ww_non_site_specific_systmone.md`: 10
- `brain_cns_cancer_referral_form_no_merge_fields_v3_feb_2026.md`: 5
- `breast_cancer_referral_forms1_v3_5.md`: 6
- `eoe_ca_gynae_referral_form_feb_25.md`: 1
- `eoe_skin_usc_proforma_final_2024.md`: 5
- `final_eoe_lung_usc_referral_form_21_05_25.md`: 8
- `haematological_cancer_referral_form_s1s.md`: 6
- `headandneckcancerreferralform_v6.md`: 7
- `lowergi_cancer_referral_form_v6.md`: 21
- `lungcancerreferralforms1_v3_0.md`: 1
- `sarcoma_referral_form_v3_0.md`: 4
- `skin_cancer_suspected_referral_form_devon_v4_1_1_s1.md`: 1
- `upper_gi_cancers_referral_form_s1s.md`: 4
- `urologicalcancerreferralform_v5_0.md`: 10
- `uscp_gynaecology_referral_form_v8.md`: 5

### Evidence Source Kinds

- `ng12`: 24
- `surface_forms`: 32
- `template`: 47

## Case Matrix

| Case ID | Site | Format | Template Markdown | Phrase classes | Difficulty | Expected strings |
| --- | --- | --- | --- | --- | --- | --- |
| lower_gi_letter_001 | lower_gi | referral_letter | lowergi_cancer_referral_form_v6.md | symptom_or_finding, investigation_result, risk_factor | dense_paragraph | 4 |
| lower_gi_email_001 | lower_gi | email_request | lowergi_cancer_referral_form_v6.md | symptom_or_finding, investigation_result | abbreviation | 3 |
| lower_gi_form_001 | lower_gi | referral_form_markdown | lowergi_cancer_referral_form_v6.md | symptom_or_finding, investigation_result | checkbox_field_label | 3 |
| upper_gi_letter_001 | upper_gi | referral_letter | upper_gi_cancers_referral_form_s1s.md | symptom_or_finding, investigation_result | dense_paragraph | 4 |
| upper_gi_form_001 | upper_gi | referral_form_markdown | upper_gi_cancers_referral_form_s1s.md | symptom_or_finding, procedure_or_referral | checkbox_field_label | 3 |
| lung_letter_001 | lung | referral_letter | final_eoe_lung_usc_referral_form_21_05_25.md | symptom_or_finding, investigation_result | abbreviation | 3 |
| lung_form_001 | lung | referral_form_markdown | final_eoe_lung_usc_referral_form_21_05_25.md | symptom_or_finding, risk_factor | checkbox_field_label | 3 |
| lung_semistructured_001 | lung | semi_structured_note | final_eoe_lung_usc_referral_form_21_05_25.md | symptom_or_finding, investigation_result | repeated_phrase | 3 |
| breast_letter_001 | breast | referral_letter | breast_cancer_referral_forms1_v3_5.md | symptom_or_finding, physical_sign | simple_sentence | 3 |
| breast_semistructured_001 | breast | semi_structured_note | breast_cancer_referral_forms1_v3_5.md | symptom_or_finding, family_history | negative_phrase | 2 |
| urology_letter_001 | urology | referral_letter | urologicalcancerreferralform_v5_0.md | symptom_or_finding, investigation_result | dense_paragraph | 3 |
| urology_form_001 | urology | referral_form_markdown | urologicalcancerreferralform_v5_0.md | symptom_or_finding, procedure_or_referral | checkbox_field_label | 2 |
| prostate_letter_001 | prostate | referral_letter | urologicalcancerreferralform_v5_0.md | investigation_result, symptom_or_finding | lab_vitals_row | 3 |
| prostate_email_001 | prostate | email_request | urologicalcancerreferralform_v5_0.md | investigation_result, family_history | abbreviation | 2 |
| gynaecology_letter_001 | gynaecology | referral_letter | uscp_gynaecology_referral_form_v8.md | symptom_or_finding, investigation_result | dense_paragraph | 3 |
| gynaecology_form_001 | gynaecology | referral_form_markdown | uscp_gynaecology_referral_form_v8.md | symptom_or_finding, risk_factor | checkbox_field_label | 3 |
| skin_letter_001 | skin | referral_letter | eoe_skin_usc_proforma_final_2024.md | symptom_or_finding, physical_sign | simple_sentence | 3 |
| skin_form_001 | skin | referral_form_markdown | eoe_skin_usc_proforma_final_2024.md | physical_sign, risk_factor | checkbox_field_label | 3 |
| head_neck_letter_001 | head_and_neck | referral_letter | headandneckcancerreferralform_v6.md | symptom_or_finding, physical_sign | dense_paragraph | 3 |
| head_neck_form_001 | head_and_neck | referral_form_markdown | headandneckcancerreferralform_v6.md | symptom_or_finding, risk_factor | checkbox_field_label | 3 |
| brain_cns_letter_001 | brain_cns | referral_letter | brain_cns_cancer_referral_form_no_merge_fields_v3_feb_2026.md | symptom_or_finding, physical_sign | dense_paragraph | 3 |
| brain_cns_email_001 | brain_cns | email_request | brain_cns_cancer_referral_form_no_merge_fields_v3_feb_2026.md | symptom_or_finding, investigation_result | abbreviation | 3 |
| haematology_letter_001 | haematology | referral_letter | haematological_cancer_referral_form_s1s.md | symptom_or_finding, investigation_result | lab_vitals_row | 4 |
| haematology_semistructured_001 | haematology | semi_structured_note | haematological_cancer_referral_form_s1s.md | symptom_or_finding, investigation_result | negative_phrase | 3 |
| sarcoma_letter_001 | sarcoma | referral_letter | sarcoma_referral_form_v3_0.md | symptom_or_finding, physical_sign | simple_sentence | 3 |
| sarcoma_form_001 | sarcoma | referral_form_markdown | sarcoma_referral_form_v3_0.md | symptom_or_finding, investigation_result | checkbox_field_label | 3 |
| nss_letter_001 | non_site_specific | referral_letter | 2ww_non_site_specific_systmone.md | symptom_or_finding, investigation_result | dense_paragraph | 3 |
| nss_email_001 | non_site_specific | email_request | 2ww_non_site_specific_systmone.md | symptom_or_finding, comorbidity | ambiguous_phrase | 3 |
| multi_site_semistructured_001 | non_site_specific | semi_structured_note | 2ww_non_site_specific_systmone.md | symptom_or_finding, family_history | dense_paragraph | 3 |
| negative_control_form_001 | lower_gi | referral_form_markdown | lowergi_cancer_referral_form_v6.md | symptom_or_finding | negative_phrase | 1 |
| abbreviation_hardcase_001 | lung | semi_structured_note | final_eoe_lung_usc_referral_form_21_05_25.md | symptom_or_finding, procedure_or_referral | abbreviation | 3 |
| lab_value_hardcase_001 | prostate | semi_structured_note | urologicalcancerreferralform_v5_0.md | investigation_result, observable_entity | lab_vitals_row | 2 |
| ambiguity_hardcase_001 | non_site_specific | referral_letter | 2ww_non_site_specific_systmone.md | symptom_or_finding, investigation_result | ambiguous_phrase | 3 |
| repeated_phrase_hardcase_001 | skin | referral_letter | eoe_skin_usc_proforma_final_2024.md | symptom_or_finding, physical_sign | repeated_phrase | 2 |
| checkbox_hardcase_001 | breast | referral_form_markdown | breast_cancer_referral_forms1_v3_5.md | symptom_or_finding, physical_sign | checkbox_field_label | 2 |
| historical_context_001 | upper_gi | semi_structured_note | upper_gi_cancers_referral_form_s1s.md | symptom_or_finding, treatment | historical_context | 2 |
| family_history_context_001 | gynaecology | referral_letter | uscp_gynaecology_referral_form_v8.md | family_history, symptom_or_finding | family_history_context | 3 |
| planned_cancelled_context_001 | urology | semi_structured_note | urologicalcancerreferralform_v5_0.md | procedure_or_referral, investigation_result | planned_cancelled_context | 2 |
| staging_scale_context_001 | breast | referral_letter | breast_cancer_referral_forms1_v3_5.md | staging_scale, cancer_type_situation | staging_scale | 3 |
| comorbidity_context_001 | head_and_neck | email_request | headandneckcancerreferralform_v6.md | comorbidity, risk_factor, symptom_or_finding | dense_paragraph | 3 |
| nss_systmone_medication_safety_001 | non_site_specific | referral_form_markdown | 2ww_non_site_specific_systmone.md | treatment, comorbidity, risk_factor, observable_entity | template_dense_form, checkbox_field_label | 7 |
| nss_systmone_radiology_safety_001 | non_site_specific | referral_form_markdown | 2ww_non_site_specific_systmone.md | comorbidity, procedure_or_referral, staging_scale | template_dense_form, negative_phrase | 4 |
| nss_incomplete_placeholder_001 | non_site_specific | referral_form_markdown | lowergi_cancer_referral_form_v6.md | symptom_or_finding, investigation_result | incomplete_form, placeholder_noise | 2 |
| eoe_footer_boilerplate_negative_001 | lung | referral_form_markdown | final_eoe_lung_usc_referral_form_21_05_25.md | symptom_or_finding, investigation_result, risk_factor | boilerplate_footer, negative_phrase | 3 |
| lung_pleural_effusion_route_001 | lung | referral_form_markdown | final_eoe_lung_usc_referral_form_21_05_25.md | symptom_or_finding, procedure_or_referral | pathway_split, negative_phrase | 3 |
| lung_spirometry_panel_001 | lung | referral_form_markdown | lungcancerreferralforms1_v3_0.md | observable_entity, procedure_or_referral, investigation_result | lab_vitals_row, surface_form_gap | 5 |
| lung_pre_ct_blood_panel_001 | lung | referral_form_markdown | final_eoe_lung_usc_referral_form_21_05_25.md | investigation_result, observable_entity | lab_vitals_row, template_dense_form | 5 |
| haem_myeloma_bundle_001 | haematology | semi_structured_note | haematological_cancer_referral_form_s1s.md | symptom_or_finding, investigation_result | template_dense_form, ng12_investigation_bundle | 7 |
| haem_lymphoma_bundle_001 | haematology | referral_form_markdown | haematological_cancer_referral_form_s1s.md | symptom_or_finding, physical_sign, investigation_result | template_dense_form | 5 |
| gynae_ca125_ultrasound_001 | gynaecology | referral_form_markdown | eoe_ca_gynae_referral_form_feb_25.md | symptom_or_finding, investigation_result | ng12_table_row, lab_vitals_row | 4 |
| gynae_vaginal_discharge_thrombocytosis_001 | gynaecology | semi_structured_note | uscp_gynaecology_referral_form_v8.md | symptom_or_finding, investigation_result | ng12_table_row | 3 |
| lower_gi_fit_placeholder_001 | lower_gi | referral_form_markdown | lowergi_cancer_referral_form_v6.md | symptom_or_finding, investigation_result | incomplete_form, placeholder_noise | 3 |
| lower_gi_ida_coeliac_001 | lower_gi | referral_form_markdown | 20230523_eoe_usc_proforma_lower_gi_final_v6_1.md | investigation_result, symptom_or_finding | template_dense_form | 4 |
| upper_gi_plymouth_only_negative_001 | upper_gi | referral_form_markdown | upper_gi_cancers_referral_form_s1s.md | symptom_or_finding, procedure_or_referral | boilerplate_footer, negative_phrase | 2 |
| upper_gi_jaundice_001 | upper_gi | referral_letter | 20250319_eoe_usc_proforma_ugi_002.md | symptom_or_finding, investigation_result, procedure_or_referral | ng12_table_row | 3 |
| skin_devon_complexity_001 | skin | referral_form_markdown | skin_cancer_suspected_referral_form_devon_v4_1_1_s1.md | risk_factor, symptom_or_finding, physical_sign, observable_entity | template_dense_form, checkbox_field_label | 5 |
| skin_eoe_photo_requirement_001 | skin | referral_form_markdown | eoe_skin_usc_proforma_final_2024.md | symptom_or_finding, physical_sign, procedure_or_referral | template_dense_form | 3 |
| brain_cns_mri_contraindication_001 | brain_cns | referral_form_markdown | brain_cns_cancer_referral_form_no_merge_fields_v3_feb_2026.md | symptom_or_finding, procedure_or_referral, comorbidity | template_dense_form, negative_phrase | 3 |
| brain_cns_known_primary_001 | brain_cns | referral_letter | brain_cns_cancer_referral_form_no_merge_fields_v3_feb_2026.md | cancer_type_situation, symptom_or_finding, comorbidity | template_dense_form | 4 |
| urology_testicular_penile_001 | urology | referral_form_markdown | urologicalcancerreferralform_v5_0.md | symptom_or_finding, physical_sign | checkbox_field_label | 3 |
| urology_uti_haematuria_001 | urology | semi_structured_note | urologicalcancerreferralform_v5_0.md | symptom_or_finding, investigation_result | negative_phrase | 3 |
| prostate_rockwood_psa_001 | prostate | referral_form_markdown | urologicalcancerreferralform_v5_0.md | investigation_result, physical_sign, staging_scale | surface_form_gap, template_dense_form | 3 |
| prostate_footer_negative_001 | upper_gi | referral_form_markdown | 20250319_eoe_usc_proforma_ugi_002.md | symptom_or_finding | boilerplate_footer, negative_phrase | 2 |
| breast_axillary_lump_001 | breast | referral_letter | breast_cancer_referral_forms1_v3_5.md | symptom_or_finding, physical_sign | ng12_table_row | 3 |
| breast_gynaecomastia_001 | breast | referral_form_markdown | breast_cancer_referral_forms1_v3_5.md | symptom_or_finding, cancer_type_situation | template_dense_form, negative_phrase | 2 |
| head_neck_oral_patch_001 | head_and_neck | referral_form_markdown | headandneckcancerreferralform_v6.md | symptom_or_finding, physical_sign, risk_factor | ng12_table_row | 4 |
| head_neck_thyroid_tft_001 | head_and_neck | referral_form_markdown | headandneckcancerreferralform_v6.md | physical_sign, investigation_result | template_dense_form | 2 |
| sarcoma_paediatric_phone_001 | sarcoma | referral_form_markdown | sarcoma_referral_form_v3_0.md | symptom_or_finding, procedure_or_referral | template_dense_form | 3 |
| sarcoma_ultrasound_lump_001 | sarcoma | email_request | sarcoma_referral_form_v3_0.md | symptom_or_finding, procedure_or_referral | ng12_table_row | 2 |
| ng12_abdominal_mass_fit_001 | lower_gi | semi_structured_note | lowergi_cancer_referral_form_v6.md | physical_sign, investigation_result | ng12_table_row | 2 |
| ng12_splenomegaly_b_symptoms_001 | haematology | referral_letter | haematological_cancer_referral_form_s1s.md | physical_sign, symptom_or_finding | ng12_table_row | 6 |
| ng12_oral_ulcer_001 | head_and_neck | email_request | headandneckcancerreferralform_v6.md | symptom_or_finding, procedure_or_referral | ng12_table_row | 2 |
| ng12_neuro_loss_function_001 | brain_cns | semi_structured_note | brain_cns_cancer_referral_form_no_merge_fields_v3_feb_2026.md | symptom_or_finding, procedure_or_referral | ng12_table_row | 2 |
| ng12_bone_back_pain_myeloma_001 | haematology | semi_structured_note | haematological_cancer_referral_form_s1s.md | symptom_or_finding, investigation_result | ng12_investigation_bundle | 5 |
| ng12_cough_chest_xray_001 | lung | semi_structured_note | final_eoe_lung_usc_referral_form_21_05_25.md | symptom_or_finding, procedure_or_referral | ng12_table_row | 3 |
| ng12_hoarseness_neck_lump_001 | head_and_neck | referral_letter | headandneckcancerreferralform_v6.md | symptom_or_finding, physical_sign | ng12_table_row | 2 |
| ng12_skin_surface_001 | skin | referral_letter | eoe_skin_usc_proforma_final_2024.md | symptom_or_finding, physical_sign | ng12_table_row | 4 |
| ng12_urological_symptoms_001 | urology | semi_structured_note | urologicalcancerreferralform_v5_0.md | symptom_or_finding, investigation_result | ng12_table_row | 3 |
| ng12_children_young_people_001 | non_site_specific | referral_letter | 2ww_non_site_specific_systmone.md | symptom_or_finding, physical_sign | ng12_table_row, age_context | 3 |
| ng12_primary_care_investigations_001 | gynaecology | referral_form_markdown | uscp_gynaecology_referral_form_v8.md | investigation_result, procedure_or_referral | ng12_investigation_bundle, lab_vitals_row | 3 |
| nss_complex_template_noise_001 | non_site_specific | referral_form_markdown | 2ww_non_site_specific_systmone.md | symptom_or_finding, comorbidity, treatment, investigation_result, physical_sign | template_dense_form, checkbox_field_label, placeholder_noise, repeated_phrase | 12 |
| nss_complex_radiology_noise_001 | non_site_specific | referral_form_markdown | 2ww_non_site_specific_systmone.md | symptom_or_finding, procedure_or_referral, investigation_result, physical_sign | template_dense_form, negative_phrase, repeated_phrase | 9 |
| nss_complex_filter_investigations_001 | non_site_specific | referral_form_markdown | 2ww_non_site_specific_systmone.md | symptom_or_finding, investigation_result, observable_entity, risk_factor | template_dense_form, checkbox_field_label, ng12_investigation_bundle, lab_vitals_row | 12 |
| lower_gi_fit_plus_prefix_001 | lower_gi | email_request | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | abbreviation, surface_form_gap, fit_surface_form_variant | 1 |
| lower_gi_fit_plus_suffix_001 | lower_gi | semi_structured_note | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | abbreviation, surface_form_gap, fit_surface_form_variant | 1 |
| lower_gi_fit_pos_abbrev_001 | lower_gi | referral_letter | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | abbreviation, fit_surface_form_variant | 1 |
| lower_gi_fit_positive_exact_001 | lower_gi | referral_form_markdown | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | checkbox_field_label, fit_surface_form_variant | 1 |
| lower_gi_positive_fit_order_001 | lower_gi | email_request | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | abbreviation, fit_surface_form_variant | 1 |
| lower_gi_fit_posotive_typo_001 | lower_gi | semi_structured_note | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | abbreviation, fit_surface_form_variant, ambiguous_phrase | 1 |
| lower_gi_fit_abnormal_001 | lower_gi | referral_form_markdown | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | checkbox_field_label, fit_surface_form_variant | 1 |
| lower_gi_fit_raised_001 | lower_gi | referral_letter | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | fit_surface_form_variant, dense_paragraph | 1 |
| lower_gi_fit_neg_abbrev_001 | lower_gi | semi_structured_note | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | abbreviation, negative_phrase, fit_surface_form_variant | 1 |
| lower_gi_fit_minus_prefix_001 | lower_gi | email_request | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | abbreviation, negative_phrase, fit_surface_form_variant | 1 |
| lower_gi_neg_fit_order_001 | lower_gi | referral_letter | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | abbreviation, negative_phrase, fit_surface_form_variant | 1 |
| lower_gi_fit_minus_suffix_001 | lower_gi | referral_form_markdown | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | checkbox_field_label, negative_phrase, fit_surface_form_variant | 1 |
| lower_gi_fit_below_threshold_001 | lower_gi | referral_form_markdown | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | lab_vitals_row, negative_phrase, fit_surface_form_variant | 1 |
| lower_gi_fit_declined_001 | lower_gi | semi_structured_note | lowergi_cancer_referral_form_v6.md | investigation_result, symptom_or_finding | planned_cancelled_context, fit_surface_form_variant | 1 |
