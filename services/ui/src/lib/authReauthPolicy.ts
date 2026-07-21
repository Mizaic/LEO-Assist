/**
 * Shared flag so API clients defer OAuth reauth while the role picker is open.
 *
 * Without this, a 401 from dashboard analytics calls during multi-role login
 * triggers triggerReauth() and sends the user back through Microsoft login
 * before they can PATCH /auth/session/role.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
let needsRoleChoice = false;

export function setAuthReauthPolicy(opts: { needsRoleChoice: boolean }): void {
  needsRoleChoice = opts.needsRoleChoice;
}

export function shouldDeferReauth(): boolean {
  return needsRoleChoice;
}
