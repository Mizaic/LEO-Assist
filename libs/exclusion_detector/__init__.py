"""Cancer exclusion detection for post-referral encounters.

Classifies encounters in the 0–100 day window after a 2WW cancer referral
to determine whether cancer was excluded, confirmed, or remains unresolved.

Usage::

    from libs.exclusion_detector.detector import detect_exclusion

    result = detect_exclusion(
        patient_id="4563591157",
        referral_date="2023-06-09",
        referral_cancer_type="skin cancer",
        patient_client=patient_client,
    )
"""
