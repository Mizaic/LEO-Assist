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
    },
  },
];

export default config;
