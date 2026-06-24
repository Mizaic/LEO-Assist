import fs from "node:fs";
import path from "node:path";

const ATLAS_ENV_KEYS = [
  "ATLAS_VALIDATION_RUNS_BASE_URL",
  "ATLAS_ORGANIZATION_ID",
  "QMS_SERVICE_TOKEN",
] as const;

export function loadPlaywrightEnv(): void {
  const candidates = [
    path.resolve(process.cwd(), ".env.local"),
    path.resolve(process.cwd(), "../../secrets/.env.secrets"),
  ];
  for (const envPath of candidates) {
    loadEnvFile(envPath);
  }
}

function loadEnvFile(envPath: string): void {
  if (!fs.existsSync(envPath)) {
    return;
  }
  const contents = fs.readFileSync(envPath, "utf8");
  for (const line of contents.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const separator = trimmed.indexOf("=");
    if (separator === -1) {
      continue;
    }
    const key = trimmed.slice(0, separator).trim();
    const rawValue = trimmed.slice(separator + 1).trim();
    const value = rawValue.replace(/^["']|["']$/g, "");
    process.env[key] ??= value;
  }
}

export function isAtlasValidationConfigured(): boolean {
  return ATLAS_ENV_KEYS.every((name) => Boolean(process.env[name]?.trim()));
}

export function atlasValidationSkipReason(): string | undefined {
  const missing = ATLAS_ENV_KEYS.filter((name) => !process.env[name]?.trim());
  if (missing.length === 0) {
    return undefined;
  }
  return `Missing Atlas validation env: ${missing.join(", ")}`;
}
