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
  };
}

export default function LegacyCarePatientRoute({ params }: Props) {
  const patientId = encodeURIComponent(params.patientId);
  redirect(`/care/patients?patient=${patientId}&tab=encounters`);
}
