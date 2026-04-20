/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
"use client";

import { Suspense } from "react";
import MissionControl from "@/components/mission-control/MissionControl";

export default function PatientsPage() {
  return (
    <Suspense>
      <MissionControl />
    </Suspense>
  );
}
