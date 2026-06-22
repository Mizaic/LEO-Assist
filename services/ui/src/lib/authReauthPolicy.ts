/**
 * Shared flag so API clients defer OAuth reauth while the role picker is open.
 *
 * Without this, a 401 from dashboard analytics calls during multi-role login
 * triggers triggerReauth() and sends the user back through Microsoft login
 * before they can PATCH /auth/session/role.
 */

let needsRoleChoice = false;

export function setAuthReauthPolicy(opts: { needsRoleChoice: boolean }): void {
  needsRoleChoice = opts.needsRoleChoice;
}

export function shouldDeferReauth(): boolean {
  return needsRoleChoice;
}
