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

// DI-LEO-AI-220: the dedicated EncounterCodedView page is retired in
// favour of the shared GoldLabelEditorDialog launched inline from the
// patient encounters tab.  Any deep links that still hit this route
// land on the patient page so the reviewer can re-open the encounter
// from the timeline (and the dialog opens against live + de-id text).
export default function EncounterPage({ params }: Props) {
  const patientId = encodeURIComponent(params.patientId);
  const encounterId = encodeURIComponent(params.encounterId);
  redirect(
    `/care/patients?patient=${patientId}&tab=encounters&encounter=${encounterId}`,
  );
}
