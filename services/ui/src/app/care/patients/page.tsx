/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EBF0B124
 *   Also implements: DO-146D93D0
 *   DI: DI-0ADA35BF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EBF0B124")
 */
import { Suspense } from "react";
import PatientListPage from "@/components/patients/PatientListPage";

export default function CarePatientListPage() {
  return (
    <Suspense>
      <PatientListPage />
    </Suspense>
  );
}
