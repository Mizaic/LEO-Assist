/**
 * Consumer-grade EPR patient shell.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import { PatientShell } from "@/components/patients/PatientShell";

interface Props {
  params: Promise<{ patientId: string }>;
}

export default function PatientShellPage({ params }: Props) {
  const router = useRouter();
  const { patientId: rawId } = use(params);
  const patientId = decodeURIComponent(rawId);

  return (
    <Box sx={{ height: { xs: "calc(100dvh - 48px)", sm: "100dvh" } }}>
      <PatientShell
        patientId={patientId}
        onBack={() => router.push("/care/patients")}
      />
    </Box>
  );
}
