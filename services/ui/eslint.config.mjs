import jsxA11y from "eslint-plugin-jsx-a11y";
import tsParser from "@typescript-eslint/parser";

/**
 * Flat ESLint config focused on the accessibility baseline enforced
 * by DI-LEO-AI-120 / VT-LEO-AI-115. The Next.js rules continue to run
 * through `next lint`; this file is what `npx eslint` picks up for
 * direct invocations, including CI.
 */
const config = [
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "test-results/**",
      "playwright-report/**",
    ],
  },
  {
    ...jsxA11y.flatConfigs.recommended,
    files: ["src/**/*.{ts,tsx,js,jsx}"],
    languageOptions: {
      ...jsxA11y.flatConfigs.recommended.languageOptions,
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      "jsx-a11y/label-has-associated-control": [
        "warn",
        { required: { some: ["nesting", "id"] } },
      ],
      // DI-LEO-AI-140 / VT-LEO-AI-136 TC-004: forbid raw hex / rgb /
      // rgba / hsl colour literals inside an MUI `sx` prop. Colour
      // decisions must go through tokens in @leo/design-system or
      // theme.palette.*, so designers can re-theme without hunting
      // strings across the repo. Token literals themselves live in
      // services/design-system/src/tokens/color.ts and
      // services/ui/src/theme/tokens.ts, both of which sit outside
      // the sx context so this rule does not fire on them.
      // Warn rather than error: legacy violations remain across the
      // tree (tracked for cleanup) but every new PR now gets the
      // feedback loop. Flip to "error" once the tracked backlog hits
      // zero.
      "no-restricted-syntax": [
        "warn",
        {
          selector:
            "JSXAttribute[name.name='sx'] Literal[value=/^#[0-9a-fA-F]{3,8}$/]",
          message:
            "Use a colour token from @leo/design-system or theme.palette.* instead of a hex literal inside sx.",
        },
        {
          selector:
            "JSXAttribute[name.name='sx'] Literal[value=/^(?:rgb|rgba|hsl|hsla)\\(/]",
          message:
            "Use a colour token from @leo/design-system or theme.palette.* instead of an rgb/hsl literal inside sx.",
        },
      ],
    },
  },
  // DI-LEO-AI-165 / VT-LEO-AI-163 (Phase 6b-vi cleanup): the pathway
  // canvas should consume design-system primitives, not raw MUI. The
  // editor still relies on MUI for a few container components (Drawer,
  // dialogs that ship from upstream Wave D) so this rule is currently
  // a "warn" rather than an "error". Flip to "error" once the legacy
  // MUI imports under pathway/** are migrated to @leo/design-system.
  {
    files: ["src/components/pathway/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "warn",
        {
          patterns: [
            {
              group: ["@mui/*"],
              message:
                "Pathway components should use @leo/design-system primitives instead of raw MUI imports.",
            },
          ],
        },
      ],
    },
  },
  // DI-LEO-AI-176 / VT-LEO-AI-171 (Wave E Phase 7): the Knowledge tab
  // shell at /admin/knowledge should consume @leo/design-system
  // primitives (KnowledgePageLayout, StatHero, ToolbarActions,
  // FilterBar, PromptEditorCard, ReviewListCard, DataGridCard,
  // MetricTile, NudgeStrip) rather than reach into raw MUI. The
  // wrapper page still uses MUI Tabs/Tab as transitional infrastructure
  // so this is a "warn" -- flip to "error" once the eight tab bodies
  // are fully migrated to design-system primitives.
  {
    files: ["src/app/admin/knowledge/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "warn",
        {
          patterns: [
            {
              group: ["@mui/*"],
              message:
                "Knowledge tabs should use @leo/design-system primitives instead of raw MUI imports.",
            },
          ],
        },
      ],
    },
  },
];

export default config;
