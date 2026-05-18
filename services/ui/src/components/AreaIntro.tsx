/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import { IntroCard, isRole, type Role } from "@leo/design-system";

import { AREA_INTRO_COPY, type AreaKey } from "@/lib/areaCopy";
import { useAuth } from "@/lib/authContext";

export interface AreaIntroProps {
  area: AreaKey;
}

function resolveRole(selectedRole: string | null): Role | null {
  return selectedRole && isRole(selectedRole) ? selectedRole : null;
}

export default function AreaIntro({ area }: AreaIntroProps) {
  const auth = useAuth();
  const role = resolveRole(auth.session?.selectedRole ?? null);
  return (
    <IntroCard
      screenId={"area-" + area}
      copy={AREA_INTRO_COPY[area]}
      role={role}
    />
  );
}
