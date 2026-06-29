"""Status and outcome enumerations for enhanced guideline leaf kinds.

Atlas trace:
  DO: DO-0EC3A9CB
  DI: DI-2199E670

These enums define the exact vocabulary the evaluator uses when matching
MEDICATION, ALLERGY, and TREATMENT_HISTORY leaves. Each enum value carries
a fail-closed rule: unknown or absent data must NEVER cause a rule to fire.

Fail-closed rule (applies to all three enums):
  - Only explicitly positive values (active / failed / not_tolerated) cause
    a rule match.
  - Any unknown, absent, stopped, planned, or resolved value fails closed.
  - This is enforced in the evaluator, not just in these definitions.
"""

from enum import Enum


class MedicationStatus(str, Enum):
    """Current status of a patient medication fact.

    Match rule: ONLY active passes a MEDICATION leaf.
    All other statuses fail closed.
    """

    active = "active"
    # Currently prescribed and on repeat or documented as current.

    stopped = "stopped"
    # Documented as stopped or discontinued. Does NOT match.

    planned = "planned"
    # Intended but not yet started. Does NOT match.

    historical = "historical"
    # Past use, no longer current. Does NOT match.

    unknown = "unknown"
    # Status not recorded. Fails closed. Does NOT match.


class AllergyStatus(str, Enum):
    """Current status of a patient allergy fact.

    Match rule: ONLY active passes an ALLERGY leaf.
    nkda and unknown are different: nkda is a documented negative
    (patient told the clinician they have no known drug allergies);
    unknown means no allergy information at all. Both fail closed
    for specific allergy leaves but produce different reason strings.
    """

    active = "active"
    # Current, documented allergy. MATCHES.

    resolved = "resolved"
    # Previously recorded, now resolved. Does NOT match.

    nkda = "nkda"
    # Documented "no known drug allergies". Does NOT match.
    # Reason: "documented no known drug allergies -- fail closed".

    unknown = "unknown"
    # No allergy information at all. Fails closed. Does NOT match.
    # Reason: "no allergy information available -- fail closed".
    # NOTE: nkda and unknown must produce different diagnostic reasons.


class TreatmentOutcome(str, Enum):
    """Outcome of a patient treatment history event.

    Match rule for "tried and failed" leaves:
      ONLY failed and not_tolerated pass a TREATMENT_HISTORY leaf.
    All other outcomes fail closed.
    """

    failed = "failed"
    # Tried and not effective. MATCHES a "tried and failed" rule.

    not_tolerated = "not_tolerated"
    # Stopped due to side effects. MATCHES a "tried and failed" rule.

    completed = "completed"
    # Course completed; outcome not separately recorded. Does NOT match.

    ongoing = "ongoing"
    # Currently receiving this treatment. Does NOT match.

    planned = "planned"
    # Not yet started. Does NOT match.

    unknown = "unknown"
    # Outcome not recorded. Fails closed. Does NOT match.
