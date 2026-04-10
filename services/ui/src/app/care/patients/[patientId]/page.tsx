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
