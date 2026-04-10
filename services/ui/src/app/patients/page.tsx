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
