/**
 * PortEdge barrel -- preserves the existing import path
 * `@/components/pathway/edges/PortEdge` while the implementation
 * lives in the `PortEdge/` subdirectory (Phase 6b-vi decomposition,
 * DI-LEO-AI-165 / DO-LEO-AI-164 / VT-LEO-AI-163).
 */

export { PortEdge } from "./PortEdge/index";
