/**
 * SettingsTab — kept for reference but NOT used in production.
 *
 * The node configuration wizard now opens as a Dialog (MUI Dialog + Stepper)
 * directly from page.tsx, using the full ActionConfigurator which contains:
 * - SubgraphSettingsPanel (model preset picker, post-process layers, terminology sliders, etc.)
 * - PromptPicker (dropdown of all available prompts)
 * - SchemaAlignmentPanel (field-level wiring)
 * - Temperature slider (hidden when NER-only preset selected)
 *
 * The stub text fields for Prompt config ID and Model preset ID that appeared
 * here were removed in favour of the proper picker components.
 */
export {};
