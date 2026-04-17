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
