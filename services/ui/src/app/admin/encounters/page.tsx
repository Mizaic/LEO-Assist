/**
 * Encounters page (admin area).
 *
 * Encounters moved from /care/encounters to /admin/encounters so that
 * the Care nav focuses on clinical workflows and the Admin nav covers
 * data-management views. Legacy /care/encounters routes redirect here.
 *
 * Atlas trace:
 *   DO: DO-F78C84A6
 *   DI: DI-D0FC22FE
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-F78C84A6")
 */
import EncounterMissionControl from "@/components/mission-control/EncounterMissionControl";

export default EncounterMissionControl;
