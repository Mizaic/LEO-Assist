import { redirect } from "next/navigation";

interface Props {
  params: {
    patientId: string;
    encounterId: string;
  };
}

// DI-LEO-AI-209: the legacy /encounters/view/{id} route is retired
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
