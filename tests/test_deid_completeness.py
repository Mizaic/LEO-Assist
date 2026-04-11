"""De-identification completeness assessment — multicultural PII corpus.

Quantifies the residual PII rate of the regex-based de-identification engine
against a synthetic corpus of NHS-realistic clinical text containing names and
identifiers drawn from diverse cultural backgrounds commonly seen in UK
primary care.

Two de-id modules are tested:
  - libs.utils.deidentify.deidentify_text  (LLM-submission path — GAP-008)
  - libs.deid.deidentify                   (NER-preprocessing path)

The test corpus is structured so that each entry contains exactly one PII item
embedded in realistic clinical narrative.  Tests are separated into:

  1. MUST-CATCH   — patterns the regex engine is designed to handle
  2. KNOWN-GAPS   — patterns that require NER or are structurally undetectable
  3. EDGE-CASES   — unusual but valid PII formats

Results are reported as a residual-rate metric at the end of the test run.

Threat coverage (DC-TM-SEC-002):
  GAP-008    Incomplete de-identification before LLM submission
  TODO:MANUAL De-identification completeness assessment
"""

from __future__ import annotations

import pytest

from libs.utils.deidentify import deidentify_text

# ============================================================================
# CORPUS: Names in SystmOne CAPS,Forename format — MUST be caught
# ============================================================================

SYSTMONE_NAMES = [
    # South Asian
    (
        "PATEL, Rajesh (Medical Secretary Access Role)",
        "South Asian male — SystmOne role format",
    ),
    (
        "BEGUM, Senuara (Admin/Clinical Support Access Role)",
        "South Asian female — SystmOne role",
    ),
    ("KHAN, Mohammed (Clerical Access Role)", "South Asian male — common surname"),
    ("AGARWAL, Priya (Dr)", "South Asian female — title format"),
    ("CHOWDHURY, Abdul (Mr)", "South Asian male — title format"),
    ("SHARMA, Deepa (Mrs)", "South Asian female — title format"),
    # East Asian
    ("WONG, Wei (Admin Access Role)", "Chinese male — SystmOne role"),
    ("CHEN, Mei-Ling (Clinical Access Role)", "Chinese female — hyphenated forename"),
    ("LEE, Min-Ji (Dr)", "Korean female — hyphenated forename"),
    ("TANAKA, Yuki (Ms)", "Japanese female — title format"),
    ("NGUYEN, Thanh (Mr)", "Vietnamese male — title format"),
    ("KIM, Soo-Yeon (Mrs)", "Korean female — hyphenated forename"),
    # African
    ("OKAFOR, Chidi (Clinical Access Role)", "Nigerian male — Igbo"),
    ("MENSAH, Kofi (Admin Access Role)", "Ghanaian male — Akan"),
    ("ABDI, Fatima (Clerical Access Role)", "Somali female"),
    ("OKONKWO, Adaeze (Dr)", "Nigerian female — Igbo title"),
    ("NKOMO, Tendai (Mr)", "Zimbabwean male — Shona"),
    # Middle Eastern
    ("AL-RASHID, Omar (Clinical Access Role)", "Arabic male — hyphenated prefix"),
    ("HUSSAIN, Aisha (Mrs)", "Arabic female — title format"),
    ("NOURI, Layla (Ms)", "Persian female — title format"),
    ("YILMAZ, Mehmet (Mr)", "Turkish male"),
    # Eastern European
    ("KOWALSKI, Agnieszka (Clerical Access Role)", "Polish female"),
    ("PETROV, Anastasia (Clinical Access Role)", "Russian female"),
    ("NOVAK, Jana (Mrs)", "Czech female — title format"),
    ("SZABO, Istvan (Mr)", "Hungarian male"),
    # Western European
    ("MULLER, Hans (Dr)", "German male — title format"),
    ("DUBOIS, Sophie (Ms)", "French female"),
    ("ROSSI, Marco (Mr)", "Italian male"),
    # Celtic / Irish
    ("O'SULLIVAN, Siobhan (Clinical Access Role)", "Irish female — apostrophe surname"),
    ("O'BRIEN, Aoife (Dr)", "Irish female — apostrophe + title"),
    ("MACLEOD, Calum (Mr)", "Scottish male — Mac prefix"),
    ("MACLEOD-BROWN, Alice (Mrs)", "Scottish female — hyphenated surname"),
    # Caribbean / mixed heritage
    ("CAMPBELL-DALEY, Marcia (Admin Access Role)", "Caribbean female — double-barrel"),
    ("BAPTISTE, Jean-Pierre (Mr)", "Caribbean male — hyphenated forename"),
]


class TestSystmOneNameFormat:
    """Names in CAPS, Forename (Role/Title) format — regex MUST catch these."""

    @pytest.mark.parametrize(
        "name,description", SYSTMONE_NAMES, ids=[d for _, d in SYSTMONE_NAMES]
    )
    def test_systmone_name_redacted(self, name, description):
        text = f"Encounter recorded by {name} on clinic day."
        result = deidentify_text(text)
        assert name not in result, f"LEAKED: {name} ({description})"
        assert "[PERSON]" in result


# ============================================================================
# CORPUS: Honorific + Surname format — MUST be caught
# ============================================================================

HONORIFIC_NAMES = [
    ("Dr Patel", "South Asian — Dr"),
    ("Dr Agarwal", "South Asian — Dr"),
    ("Dr Chen", "Chinese — Dr"),
    ("Dr Okafor", "Nigerian — Dr"),
    ("Dr Al-Rashid", "Arabic — Dr hyphenated"),
    ("Dr Hussain", "Arabic — Dr"),
    ("Dr Kowalski", "Polish — Dr"),
    ("Dr Muller", "German — Dr"),
    ("Dr O'Sullivan", "Irish — Dr apostrophe"),
    ("Dr MacLeod", "Scottish — Dr Mac"),
    ("Mr Wong", "Chinese — Mr"),
    ("Mrs Begum", "South Asian — Mrs"),
    ("Ms Nguyen", "Vietnamese — Ms"),
    ("Miss Abdi", "Somali — Miss"),
    ("Prof Tanaka", "Japanese — Prof"),
    ("Dr Rodriguez", "Hispanic — Dr"),
    ("Mrs Fernandez", "Hispanic — Mrs"),
    ("Dr Nakamura", "Japanese — Dr"),
    ("Mr Kwame", "Ghanaian — Mr"),
    ("Dr Svenson", "Scandinavian — Dr"),
]


class TestHonorificNameFormat:
    """Title + Surname format — regex MUST catch these."""

    @pytest.mark.parametrize(
        "name,description", HONORIFIC_NAMES, ids=[d for _, d in HONORIFIC_NAMES]
    )
    def test_honorific_name_redacted(self, name, description):
        text = f"Referral letter from {name} received today."
        result = deidentify_text(text)
        assert name not in result, f"LEAKED: {name} ({description})"
        assert "[PERSON]" in result


# ============================================================================
# CORPUS: ALL-CAPS SURNAME, Forename (bare — no role/title suffix)
# ============================================================================

CAPS_BARE_NAMES = [
    ("PATEL, Rajesh", "South Asian male"),
    ("KHAN, Mohammed", "South Asian male"),
    ("WONG, Wei", "Chinese male — short forename"),
    ("CHEN, Mei", "Chinese female — short forename"),
    ("OKAFOR, Chidi", "Nigerian male — Igbo"),
    ("ABDI, Fatima", "Somali female"),
    ("YILMAZ, Mehmet", "Turkish male"),
    ("KOWALSKI, Agnieszka", "Polish female"),
    ("O'NEILL, Siobhan", "Irish female — apostrophe"),
    ("GARCIA, Maria", "Hispanic female"),
    ("PETROV, Anastasia", "Russian female"),
    ("NAKAMURA, Haruki", "Japanese male"),
    ("OSEI-BONSU, Kwame", "Ghanaian male — hyphenated"),
    ("MACLEOD, Fiona", "Scottish female"),
]


class TestCapsBareName:
    """ALL-CAPS SURNAME, Forename without role/title — regex MUST catch."""

    @pytest.mark.parametrize(
        "name,description", CAPS_BARE_NAMES, ids=[d for _, d in CAPS_BARE_NAMES]
    )
    def test_caps_bare_name_redacted(self, name, description):
        text = f"Clinical note by {name} regarding follow-up."
        result = deidentify_text(text)
        assert name not in result, f"LEAKED: {name} ({description})"
        assert "[PERSON]" in result


# ============================================================================
# KNOWN GAPS: Free-text first names — regex CANNOT catch these
# These tests DOCUMENT the gap and measure the residual rate.
# They are marked xfail so they don't block CI but DO report if NER fixes them.
# ============================================================================

FREETEXT_NAMES = [
    ("Rajesh", "South Asian male first name"),
    ("Mohammed", "Arabic male first name"),
    ("Siobhan", "Irish female first name"),
    ("Fatima", "Somali/Arabic female first name"),
    ("Wei", "Chinese male first name"),
    ("Priya", "South Asian female first name"),
    ("Chidi", "Nigerian male first name"),
    ("Agnieszka", "Polish female first name"),
    ("Mei-Ling", "Chinese female hyphenated first name"),
    ("Anastasia", "Russian female first name"),
    ("Aoife", "Irish female first name"),
    ("Kwame", "Ghanaian male first name"),
    ("Haruki", "Japanese male first name"),
    ("Layla", "Arabic/Persian female first name"),
    ("Mehmet", "Turkish male first name"),
    ("Adaeze", "Nigerian female first name"),
    ("Soo-Yeon", "Korean female first name"),
    ("Jean-Pierre", "Caribbean/French male first name"),
    ("Thanh", "Vietnamese male first name"),
    ("Istvan", "Hungarian male first name"),
]


class TestFreeTextFirstNames:
    """First names in free clinical narrative — regex CANNOT catch.

    These are xfail(strict=False): they pass if NER is enabled, fail otherwise.
    The test documents the known gap and will start passing once NER is deployed.
    """

    @pytest.mark.parametrize(
        "name,description", FREETEXT_NAMES, ids=[d for _, d in FREETEXT_NAMES]
    )
    @pytest.mark.xfail(
        reason="GAP-008: regex cannot catch bare first names; requires NER pass",
        strict=False,
    )
    def test_freetext_name_redacted(self, name, description):
        text = f"Discussed treatment plan with {name} who reports improvement."
        result = deidentify_text(text)
        assert name not in result, f"LEAKED in free text: {name} ({description})"


# ============================================================================
# NER SECOND PASS — multicultural name detection with spaCy
# ============================================================================


def _spacy_available(model: str) -> bool:
    try:
        import spacy

        spacy.load(model, disable=["tagger", "parser", "lemmatizer"])
        return True
    except Exception:
        return False


# Names that en_core_web_lg detects as PERSON (19/20 — empirically verified)
NER_LG_CATCHES = [
    ("Rajesh", "South Asian male"),
    ("Mohammed", "Arabic male"),
    ("Siobhan", "Irish female"),
    ("Fatima", "Somali/Arabic female"),
    ("Wei", "Chinese male"),
    ("Priya", "South Asian female"),
    ("Agnieszka", "Polish female"),
    ("Mei-Ling", "Chinese female"),
    ("Anastasia", "Russian female"),
    ("Aoife", "Irish female"),
    ("Kwame", "Ghanaian male"),
    ("Haruki", "Japanese male"),
    ("Layla", "Arabic/Persian female"),
    ("Mehmet", "Turkish male"),
    ("Adaeze", "Nigerian female"),
    ("Soo-Yeon", "Korean female"),
    ("Jean-Pierre", "Caribbean/French male"),
    ("Thanh", "Vietnamese male"),
    ("Istvan", "Hungarian male"),
]

# Names that en_core_web_lg misclassifies (1/20 — Chidi classified as ORG)
NER_LG_MISSES = [
    ("Chidi", "Nigerian male — Igbo (misclassified as ORG by en_core_web_lg)"),
]

# Names that en_core_web_sm misclassifies (10/20 — significant multicultural bias)
NER_SM_MISSES = [
    ("Rajesh", "classified as PRODUCT"),
    ("Siobhan", "classified as GPE"),
    ("Priya", "classified as NORP"),
    ("Agnieszka", "classified as GPE"),
    ("Aoife", "classified as GPE"),
    ("Layla", "not recognised"),
    ("Mehmet", "classified as ORG"),
    ("Adaeze", "classified as GPE"),
    ("Soo-Yeon", "classified as ORG"),
    ("Istvan", "classified as GPE"),
]


@pytest.mark.skipif(
    not _spacy_available("en_core_web_lg"),
    reason="en_core_web_lg not installed — skip NER accuracy tests",
)
class TestNerLargeModelAccuracy:
    """Verify en_core_web_lg catches multicultural names the regex misses.

    Model choice matters: en_core_web_sm catches only 10/20 multicultural
    names while en_core_web_lg catches 19/20. Deployments MUST use the
    large model for adequate multicultural PII coverage.
    """

    @pytest.mark.parametrize(
        "name,description", NER_LG_CATCHES, ids=[d for _, d in NER_LG_CATCHES]
    )
    def test_ner_lg_catches_name(self, name, description):
        import os

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("DEIDENTIFY_NER_MODEL", "en_core_web_lg")
            import libs.utils.deidentify as deid_mod

            deid_mod._NER_NLP = None
            deid_mod._NER_MODEL = None
            text = f"Discussed treatment plan with {name} who reports improvement."
            result = deidentify_text(text, ner=True)
        assert name not in result, f"NER(lg) MISSED: {name} ({description})"
        assert "[PERSON]" in result

    @pytest.mark.parametrize(
        "name,description", NER_LG_MISSES, ids=[d for _, d in NER_LG_MISSES]
    )
    @pytest.mark.xfail(
        reason="en_core_web_lg misclassifies this name; known gap", strict=False
    )
    def test_ner_lg_known_miss(self, name, description):
        import os

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("DEIDENTIFY_NER_MODEL", "en_core_web_lg")
            import libs.utils.deidentify as deid_mod

            deid_mod._NER_NLP = None
            deid_mod._NER_MODEL = None
            text = f"Discussed treatment plan with {name} who reports improvement."
            result = deidentify_text(text, ner=True)
        assert name not in result, f"NER(lg) MISSED: {name} ({description})"


@pytest.mark.skipif(
    not _spacy_available("en_core_web_sm"),
    reason="en_core_web_sm not installed",
)
class TestNerSmallModelBias:
    """Document en_core_web_sm multicultural bias — 10/20 names misclassified.

    This class exists to quantify WHY en_core_web_lg must be used in production.
    All tests here are xfail: they demonstrate the small model's failures.
    """

    @pytest.mark.parametrize(
        "name,description", NER_SM_MISSES, ids=[d for _, d in NER_SM_MISSES]
    )
    @pytest.mark.xfail(
        reason="en_core_web_sm has multicultural name bias; use en_core_web_lg",
        strict=False,
    )
    def test_sm_model_misclassifies(self, name, description):
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("DEIDENTIFY_NER_MODEL", "en_core_web_sm")
            import libs.utils.deidentify as deid_mod

            deid_mod._NER_NLP = None
            deid_mod._NER_MODEL = None
            text = f"Discussed treatment plan with {name} who reports improvement."
            result = deidentify_text(text, ner=True)
        assert name not in result, f"NER(sm) expected to MISS: {name} ({description})"


# ============================================================================
# NHS NUMBERS — MUST be caught
# ============================================================================

NHS_NUMBERS = [
    ("943 476 5919", "spaced format"),
    ("9434765919", "contiguous format"),
    ("943-476-5919", "hyphen format"),
    ("123 456 7890", "spaced format — different number"),
    ("999 888 7777", "spaced format — another"),
]


class TestNhsNumbers:

    @pytest.mark.parametrize(
        "nhs,description", NHS_NUMBERS, ids=[d for _, d in NHS_NUMBERS]
    )
    def test_nhs_number_redacted(self, nhs, description):
        text = f"Patient NHS number is {nhs} and needs follow-up."
        result = deidentify_text(text)
        assert nhs not in result, f"LEAKED: NHS {nhs} ({description})"


# ============================================================================
# UK POSTCODES — MUST be caught
# ============================================================================

POSTCODES = [
    ("SW1A 1AA", "central London"),
    ("LE11 3TU", "Loughborough"),
    ("M1 1AA", "Manchester — short"),
    ("EC2A 4NE", "City of London"),
    ("B15 2TT", "Birmingham"),
    ("LS1 4AP", "Leeds"),
    ("CF10 1EP", "Cardiff"),
    ("EH1 1RE", "Edinburgh"),
    ("BT1 5GS", "Belfast"),
    ("GIR 0AA", "Girobank special"),
]


class TestPostcodes:

    @pytest.mark.parametrize(
        "postcode,description", POSTCODES, ids=[d for _, d in POSTCODES]
    )
    def test_postcode_redacted(self, postcode, description):
        text = f"Patient address includes {postcode} in their records."
        result = deidentify_text(text)
        assert postcode not in result, f"LEAKED: {postcode} ({description})"


# ============================================================================
# UK PHONE NUMBERS — MUST be caught
# ============================================================================

PHONES = [
    ("07700 900 123", "UK mobile"),
    ("+44 7911 123456", "international mobile"),
    ("01onal 234567", "landline — intentionally mangled to skip"),
    ("01onal234567", "landline — intentionally mangled to skip"),
    ("0116 254 9568", "Leicester landline"),
    ("020 7946 0958", "London landline"),
    ("07700900123", "mobile contiguous"),
]


class TestPhoneNumbers:

    @pytest.mark.parametrize(
        "phone,description",
        [
            ("07700 900 123", "UK mobile"),
            ("+44 7911 123456", "international mobile"),
            ("0116 254 9568", "Leicester landline"),
            ("020 7946 0958", "London landline"),
            ("07700900123", "mobile contiguous"),
        ],
    )
    def test_phone_redacted(self, phone, description):
        text = f"Contact patient on {phone} to arrange appointment."
        result = deidentify_text(text)
        assert phone not in result, f"LEAKED: {phone} ({description})"


# ============================================================================
# EMAIL ADDRESSES — MUST be caught
# ============================================================================

EMAILS = [
    ("rajesh.patel@nhs.net", "NHS email — South Asian"),
    ("mohammed.khan@practice.nhs.uk", "NHS email — Arabic"),
    ("siobhan.osullivan@gmail.com", "personal email — Irish"),
    ("wei.wong@outlook.com", "personal email — Chinese"),
    ("a.kowalski@hospital.pl", "non-UK email — Polish"),
]


class TestEmails:

    @pytest.mark.parametrize("email,description", EMAILS, ids=[d for _, d in EMAILS])
    def test_email_redacted(self, email, description):
        text = f"Patient email is {email} for correspondence."
        result = deidentify_text(text)
        assert email not in result, f"LEAKED: {email} ({description})"


# ============================================================================
# DATES — MUST be caught
# ============================================================================

DATES = [
    ("12/06/1975", "DD/MM/YYYY slash"),
    ("3/1/22", "D/M/YY short"),
    ("12.06.1975", "DD.MM.YYYY dot"),
    ("1975-06-12", "ISO YYYY-MM-DD"),
    ("15 May 2024", "D Month YYYY natural"),
    ("01/01/2000", "DD/MM/YYYY millennium"),
    ("31/12/1999", "DD/MM/YYYY end of year"),
]


class TestDates:

    @pytest.mark.parametrize("date,description", DATES, ids=[d for _, d in DATES])
    def test_date_redacted(self, date, description):
        text = f"Date of birth {date} recorded in notes."
        result = deidentify_text(text)
        assert date not in result, f"LEAKED: {date} ({description})"


# ============================================================================
# STREET ADDRESSES — MUST be caught
# ============================================================================

ADDRESSES = [
    ("44 Carnation Road", "standard Road"),
    ("12 High Street", "standard Street"),
    ("7 Oakwood Avenue", "standard Avenue"),
    ("101 Victoria Lane", "standard Lane"),
    ("3 Willow Close", "standard Close"),
    ("256 Park Drive", "standard Drive"),
]


class TestAddresses:

    @pytest.mark.parametrize(
        "address,description", ADDRESSES, ids=[d for _, d in ADDRESSES]
    )
    def test_address_redacted(self, address, description):
        text = f"Patient lives at {address}, Leicestershire."
        result = deidentify_text(text)
        assert address not in result, f"LEAKED: {address} ({description})"


# ============================================================================
# HEALTHCARE FACILITY NAMES — MUST be caught
# ============================================================================

FACILITIES = [
    ("City Hospital", "generic hospital"),
    ("Royal Infirmary", "royal infirmary"),
    ("St Mary's Medical Centre", "apostrophe + Medical Centre"),
    ("Leicester General Hospital", "full name"),
    ("Queen's Health Centre", "apostrophe + Health Centre"),
]


class TestFacilityNames:

    @pytest.mark.parametrize(
        "facility,description", FACILITIES, ids=[d for _, d in FACILITIES]
    )
    def test_facility_redacted(self, facility, description):
        text = f"Patient referred to {facility} for assessment."
        result = deidentify_text(text)
        # Facility names are replaced with [LOCATION] + type keyword
        assert facility not in result, f"LEAKED: {facility} ({description})"
        assert "[LOCATION]" in result


# ============================================================================
# INTEGRATED CLINICAL SCENARIOS — realistic multi-PII encounters
# ============================================================================


class TestIntegratedScenarios:
    """Full clinical encounter text with multiple PII items."""

    def test_south_asian_encounter(self):
        text = (
            "PATEL, Rajesh (Dr) reviewed patient in clinic today. "
            "NHS number 943 476 5919. Lives at 22 High Street, LE11 3TU. "
            "Contact on 0116 254 9568. DOB 15/03/1962. "
            "Email rajesh.patel@nhs.net. Referred to Leicester General Hospital."
        )
        result = deidentify_text(text)
        assert "PATEL" not in result
        assert "Rajesh" not in result
        assert "943 476 5919" not in result
        assert "22 High Street" not in result
        assert "LE11 3TU" not in result
        assert "0116 254 9568" not in result
        assert "15/03/1962" not in result
        assert "rajesh.patel@nhs.net" not in result
        assert "Leicester General" not in result

    def test_east_asian_encounter(self):
        text = (
            "CHEN, Mei-Ling (Clinical Access Role) documented consultation. "
            "Patient DOB 1988-04-22. Contact 07700 900 123. "
            "Address 7 Oakwood Avenue, SW1A 1AA. "
            "Dr Wong reviewed blood results."
        )
        result = deidentify_text(text)
        assert "CHEN, Mei-Ling" not in result
        assert "1988-04-22" not in result
        assert "07700 900 123" not in result
        assert "7 Oakwood Avenue" not in result
        assert "SW1A 1AA" not in result
        assert "Dr Wong" not in result

    def test_african_encounter(self):
        text = (
            "OKAFOR, Chidi (Admin Access Role) added follow-up note. "
            "Patient ABDI, Fatima seen by Dr Mensah. "
            "NHS number 123 456 7890. DOB 08/11/1995. "
            "Lives at 101 Victoria Lane, B15 2TT."
        )
        result = deidentify_text(text)
        assert "OKAFOR, Chidi" not in result
        assert "ABDI, Fatima" not in result
        assert "Dr Mensah" not in result
        assert "123 456 7890" not in result
        assert "08/11/1995" not in result
        assert "101 Victoria Lane" not in result
        assert "B15 2TT" not in result

    def test_middle_eastern_encounter(self):
        text = (
            "AL-RASHID, Omar (Clinical Access Role) recorded assessment. "
            "Mrs Hussain attended for review. NHS 999 888 7777. "
            "Email aisha.hussain@practice.nhs.uk. "
            "Referred to Royal Infirmary."
        )
        result = deidentify_text(text)
        assert "AL-RASHID, Omar" not in result
        assert "Mrs Hussain" not in result
        assert "999 888 7777" not in result
        assert "aisha.hussain@practice.nhs.uk" not in result
        assert "Royal Infirmary" not in result

    def test_irish_celtic_encounter(self):
        text = (
            "O'SULLIVAN, Siobhan (Clinical Access Role) completed notes. "
            "Dr MacLeod reviewed. Patient DOB 25/12/1980. "
            "Lives at 3 Willow Close, CF10 1EP. Contact +44 7911 123456."
        )
        result = deidentify_text(text)
        assert "O'SULLIVAN, Siobhan" not in result
        assert "Dr MacLeod" not in result
        assert "25/12/1980" not in result
        assert "3 Willow Close" not in result
        assert "CF10 1EP" not in result

    def test_eastern_european_encounter(self):
        text = (
            "KOWALSKI, Agnieszka (Clerical Access Role) filed referral. "
            "PETROV, Anastasia seen by Dr Novak. "
            "DOB 02.07.1978. NHS 111 222 3333."
        )
        result = deidentify_text(text)
        assert "KOWALSKI, Agnieszka" not in result
        assert "PETROV, Anastasia" not in result
        assert "02.07.1978" not in result
        assert "111 222 3333" not in result

    def test_clean_clinical_text_preserved(self):
        """Clinical content without PII must pass through unchanged."""
        text = (
            "Patient presents with a 3-week history of persistent cough. "
            "No haemoptysis. Non-smoker. CXR normal. O/E: clear chest, "
            "no lymphadenopathy. Plan: safety-net for 3 weeks, review if "
            "persists. Consider urgent 2WW if red flags develop. "
            "Diagnosis: Acute bronchitis (SNOMED 10509002). "
            "Prescribed amoxicillin 500mg TDS for 5 days."
        )
        result = deidentify_text(text)
        assert result == text, "Clean clinical text was modified by de-identification"


# ============================================================================
# RESIDUAL RATE METRIC — summary statistics
# ============================================================================


class TestResidualRateReport:
    """Calculate and report the residual PII rate for the regex engine.

    This is not a pass/fail test — it measures and logs the current
    detection rate across all PII categories for audit purposes.
    """

    def test_report_residual_rate(self):
        must_catch = {
            "systmone_names": [(n, d) for n, d in SYSTMONE_NAMES],
            "honorific_names": [(n, d) for n, d in HONORIFIC_NAMES],
            "caps_bare_names": [(n, d) for n, d in CAPS_BARE_NAMES],
            "nhs_numbers": [
                ("943 476 5919", ""),
                ("9434765919", ""),
                ("123 456 7890", ""),
                ("999 888 7777", ""),
            ],
            "postcodes": [(p, d) for p, d in POSTCODES],
            "emails": [(e, d) for e, d in EMAILS],
            "dates": [(dt, d) for dt, d in DATES],
            "addresses": [(a, d) for a, d in ADDRESSES],
        }

        results: dict[str, dict] = {}
        total_items = 0
        total_caught = 0
        leaked: list[str] = []

        for category, items in must_catch.items():
            caught = 0
            for pii_value, desc in items:
                total_items += 1
                text = f"Clinical text containing {pii_value} in the record."
                result = deidentify_text(text)
                if pii_value not in result:
                    caught += 1
                    total_caught += 1
                else:
                    leaked.append(f"  {category}: {pii_value} ({desc})")

            results[category] = {
                "total": len(items),
                "caught": caught,
                "rate": caught / len(items) if items else 0,
            }

        overall_rate = total_caught / total_items if total_items else 0

        report_lines = [
            "",
            "=" * 70,
            "DE-IDENTIFICATION COMPLETENESS REPORT (regex-only, no NER)",
            "=" * 70,
        ]
        for cat, r in results.items():
            status = (
                "PASS"
                if r["rate"] == 1.0
                else f"GAPS ({r['total'] - r['caught']} missed)"
            )
            report_lines.append(
                f"  {cat:25s}  {r['caught']:3d}/{r['total']:3d}  ({r['rate']:.0%})  {status}"
            )

        report_lines.append("-" * 70)
        report_lines.append(
            f"  {'OVERALL':25s}  {total_caught:3d}/{total_items:3d}  ({overall_rate:.0%})"
        )

        if leaked:
            report_lines.append("")
            report_lines.append("LEAKED ITEMS:")
            report_lines.extend(leaked)

        report_lines.append("")
        report_lines.append(
            f"Free-text first names (KNOWN GAP): {len(FREETEXT_NAMES)} items — requires NER pass"
        )
        report_lines.append("=" * 70)

        # Print to pytest output
        print("\n".join(report_lines))

        # The must-catch rate should be >= 95% (allows for edge-case formats)
        assert overall_rate >= 0.95, (
            f"Residual PII rate too high: {1 - overall_rate:.1%} leaked "
            f"({total_items - total_caught}/{total_items} items)"
        )
