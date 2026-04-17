/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: "jsdom",
  roots: ["<rootDir>/src"],
  moduleDirectories: ["node_modules", "<rootDir>/node_modules"],
  transform: {
    "^.+\\.tsx?$": [
      "ts-jest",
      {
        tsconfig: "tsconfig.json",
        jsx: "react-jsx",
      },
    ],
  },
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    "^@leo/design-system$": "<rootDir>/../design-system/src/index.ts",
    "^@leo/design-system/(.*)$": "<rootDir>/../design-system/src/$1",
    "^react$": "<rootDir>/node_modules/react",
    "^react/(.*)$": "<rootDir>/node_modules/react/$1",
    "^react-dom$": "<rootDir>/node_modules/react-dom",
    "^react-dom/(.*)$": "<rootDir>/node_modules/react-dom/$1",
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    "\\.(png|jpg|jpeg|gif|svg|webp)$": "<rootDir>/src/__mocks__/fileMock.ts",
  },
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  testMatch: ["**/__tests__/**/*.test.ts?(x)"],
  transformIgnorePatterns: [
    "/node_modules/(?!(@mui|@emotion|recharts|d3-|internmap|delaunator|robust-predicates)/)",
  ],
  collectCoverageFrom: [
    "src/**/*.{ts,tsx}",
    "!src/**/*.d.ts",
    "!src/app/**/layout.tsx",
    "!src/app/**/loading.tsx",
  ],
};
