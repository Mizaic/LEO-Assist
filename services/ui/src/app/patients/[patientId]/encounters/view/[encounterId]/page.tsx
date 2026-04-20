/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
import { redirect } from "next/navigation";

interface Props {
  params: {
    patientId: string;
    encounterId: string;
  };
}

// DI-LEO-AI-220: the legacy /encounters/view/{id} route is retired
// alongside the EncounterCodedView page.  Redirect to the modern
// patient encounters tab so the reviewer can re-open the shared
// GoldLabelEditorDialog from the timeline.
export default function LegacyEncounterCodedPage({ params }: Props) {
  const patientId = encodeURIComponent(params.patientId);
  const encounterId = encodeURIComponent(params.encounterId);
  redirect(
    `/care/patients?patient=${patientId}&tab=encounters&encounter=${encounterId}`,
  );
}
