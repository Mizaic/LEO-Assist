/**
 * ============================================================================
 * FILE HEADER TEMPLATE FOR ISO 13485 TRACEABILITY
 * ============================================================================
 * 
 * Copy this header to the top of implementation files.
 * Replace placeholders with actual values.
 * 
 * Required for Safety Class B and C components.
 * Recommended for Safety Class A components.
 */

// ============================================================================
// Copyright Healthcare CoPilot, a Mizaic Company
// Project: {{PROJECT_NAME}}
// DI: {{DESIGN_INPUT_IDS}} - {{BRIEF_DESCRIPTION}}
// DO: {{FILE_PATH}}
// Safety Class: {{SAFETY_CLASS}}
// ============================================================================

/**
 * PLACEHOLDER VALUES:
 * 
 * {{PROJECT_NAME}}      - e.g., "Clinical eForms Platform"
 * {{DESIGN_INPUT_IDS}}  - e.g., "DI-EFORMS-024" or "DI-EFORMS-024, DI-EFORMS-025"
 * {{BRIEF_DESCRIPTION}} - e.g., "Validation service for form fields"
 * {{FILE_PATH}}         - e.g., "src/lib/form-engine/validation-service.ts"
 * {{SAFETY_CLASS}}      - "A", "B", or "C" per IEC 62304
 * 
 * SAFETY CLASS DEFINITIONS (IEC 62304):
 * 
 * Class A: No injury or damage to health is possible
 *          - UI components, styling, non-clinical features
 *          - Basic documentation required
 * 
 * Class B: Non-serious injury is possible
 *          - Form validation, data processing, clinical workflows
 *          - Detailed documentation, full test coverage required
 * 
 * Class C: Death or serious injury is possible
 *          - Critical clinical decision support, medication dosing
 *          - Extensive documentation, formal verification required
 */

// ============================================================================
// EXAMPLES
// ============================================================================

/**
 * Example 1: Safety Class A Component
 */
// ============================================================================
// Copyright Healthcare CoPilot, a Mizaic Company
// Project: Clinical eForms Platform
// DI: DI-EFORMS-022 - Step navigation UI component
// DO: src/components/form-completion/StepNavigator.tsx
// Safety Class: A
// ============================================================================

/**
 * Example 2: Safety Class B Service
 */
// ============================================================================
// Copyright Healthcare CoPilot, a Mizaic Company
// Project: Clinical eForms Platform
// DI: DI-EFORMS-024 - Form field validation service
// DO: src/lib/form-engine/validation-service.ts
// Safety Class: B
// Risks Mitigated: R-EFORMS-001
// ============================================================================

/**
 * Example 3: Safety Class B with Multiple DIs
 */
// ============================================================================
// Copyright Healthcare CoPilot, a Mizaic Company
// Project: Clinical eForms Platform
// DI: DI-EFORMS-014, DI-EFORMS-021 - Conditional logic and form completion
// DO: src/lib/form-engine/form-completion-engine.ts
// Safety Class: B
// Risks Mitigated: R-EFORMS-004, R-EFORMS-001
// ============================================================================

/**
 * Example 4: Test File Header
 */
// ============================================================================
// Copyright Healthcare CoPilot, a Mizaic Company
// Project: Clinical eForms Platform
// VT: VT-EFORMS-024 - Validation service verification
// DI: DI-EFORMS-024
// Safety Class: B
// ============================================================================


