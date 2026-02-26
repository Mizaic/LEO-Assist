# NCDA Measure Pipeline Field Ownership

Fields used by the no-code measure builder and their data sources.

## CancerEpisode Properties

| Property | Source | Status |
|----------|--------|--------|
| cancer_type | Episode builder | Available |
| status | Episode builder | Available |
| referral_date | Episode builder | Available |
| diagnosis_date | Episode builder | Available |
| first_presentation_date | Episode builder | Available |
| referral_route | Pipeline extraction | In progress |
| place_of_presentation | Pipeline extraction | In progress |
| safety_netting_recorded | Pipeline extraction | In progress |
| cancer_stage | PHE COSD (external) | Requires data feed |

## Patient Properties

| Property | Source | Status |
|----------|--------|--------|
| gender | FHIR Patient | Available |
| birthDate | FHIR Patient | Available |
| ethnicity | Registry / GP data | Pending |

## Derived (computed in Cypher)

| Field | Formula |
|-------|---------|
| age_band_at_diagnosis | duration.between(birthDate, diagnosis_date) -> bands 0-24, 25-49, 50-64, 65-74, 75-84, 85+ |
| primary_care_interval_days | first_presentation_date to referral_date |
| diagnostic_interval_days | first_presentation_date to diagnosis_date |

## Non-automatable (NCDA audit form)

- Multiple consultation reasons
- Emergency referral sub-categories (0-7)
- Avoidable delays (GP hindsight assessment)
