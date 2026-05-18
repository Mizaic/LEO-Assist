/**
 * PortEdge barrel -- preserves the existing import path
 * `@/components/pathway/edges/PortEdge` while the implementation
 * lives in the `PortEdge/` subdirectory (Phase 6b-vi decomposition,
 * DI-LEO-AI-165 / DO-LEO-AI-164 / VT-LEO-AI-163).
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
export { PortEdge } from "./PortEdge/index";
