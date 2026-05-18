/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
export {
  CANONICAL_ROLES,
  ROLE_COPY,
  isRole,
  type NavItem,
  type Role,
  type RoleNavConfig,
  type RoleNavMap,
} from "./types";
export { roleNavMap, landingForRole } from "./navMap";
export {
  RoleContext,
  RoleProvider,
  useRole,
  defaultRoleApi,
  type RoleApi,
  type RoleContextValue,
  type RoleProviderProps,
  type RoleState,
} from "./RoleContext";
export { RoleGate, type RoleGateProps } from "./RoleGate";
export { RolePicker, type RolePickerProps } from "./RolePicker";
export { RoleSwitcher, type RoleSwitcherProps } from "./RoleSwitcher";
