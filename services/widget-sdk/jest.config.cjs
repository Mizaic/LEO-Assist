/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: "jsdom",
  roots: ["<rootDir>/src"],
  transform: {
    "^.+\\.tsx?$": [
      "ts-jest",
      {
        tsconfig: {
          target: "ES2020",
          module: "commonjs",
          moduleResolution: "node",
          esModuleInterop: true,
          jsx: "react-jsx",
          strict: true,
          isolatedModules: true,
          skipLibCheck: true,
          paths: {
            "@/*": ["<rootDir>/src/*"],
            "@leo/sbar-types": [
              "<rootDir>/../ui/src/components/sbar-final/SbarFinalView",
            ],
          },
        },
        diagnostics: false,
      },
    ],
  },
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    "^@leo/sbar-types$": "<rootDir>/../ui/src/components/sbar-final/SbarFinalView",
  },
  testMatch: ["**/__tests__/**/*.test.ts?(x)"],
  moduleFileExtensions: ["ts", "tsx", "js", "json"],
};
