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
];

export default config;
