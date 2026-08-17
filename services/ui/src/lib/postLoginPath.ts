/**
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 */
import { isRole, landingForRole } from "@leo/design-system";

export function postLoginPath(session: {
  selectedRole: string | null;
  isPlatformAdmin: boolean;
}): string {
  if (session.selectedRole && isRole(session.selectedRole)) {
    return landingForRole(session.selectedRole);
  }
  if (session.isPlatformAdmin) {
    return "/admin/knowledge";
  }
  return "/care/dashboard";
}
