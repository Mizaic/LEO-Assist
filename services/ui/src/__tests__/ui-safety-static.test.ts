/**
 * Static analysis tests for VT-LEO-AI-036 cases TC-012 through TC-018.
 *
 * These tests read source files and assert structural properties that
 * cannot be verified through component rendering (contrast values,
 * absence of banned patterns, file existence, CSS rules, etc.).
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");

function readSource(relativePath: string): string {
  const fullPath = path.join(ROOT, relativePath);
  return fs.readFileSync(fullPath, "utf-8");
}

function readUISrc(relativePath: string): string {
  return fs.readFileSync(path.join(UI_SRC, relativePath), "utf-8");
}

function collectTsxFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory() && entry.name !== "__tests__" && entry.name !== "node_modules") {
      results.push(...collectTsxFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".tsx") && !entry.name.endsWith(".test.tsx")) {
      results.push(full);
    }
  }
  return results;
}

// -- VT-036-TC-012: Skip navigation link -------------------------------------

describe("VT-036-TC-012: Skip navigation link", () => {
  const layout = readUISrc("app/layout.tsx");
  const css = readUISrc("app/globals.css");

  it("layout.tsx contains skip link targeting #main-content", () => {
    expect(layout).toContain('href="#main-content"');
    expect(layout).toContain("skip-link");
    expect(layout).toContain("Skip to main content");
  });

  it("globals.css hides skip-link off-screen by default", () => {
    expect(css).toContain(".skip-link");
    expect(css).toMatch(/top:\s*-\d+px/);
  });

  it("globals.css reveals skip-link on :focus", () => {
    expect(css).toContain(".skip-link:focus");
    expect(css).toMatch(/\.skip-link:focus\s*\{[\s\S]*?top:\s*0/);
  });
});

// -- VT-036-TC-013: Colour contrast meets AA --------------------------------

describe("VT-036-TC-013: Colour contrast meets AA", () => {
  const theme = readUISrc("theme.ts");

  function hexToRgb(hex: string): [number, number, number] {
    const h = hex.replace("#", "");
    return [
      parseInt(h.substring(0, 2), 16),
      parseInt(h.substring(2, 4), 16),
      parseInt(h.substring(4, 6), 16),
    ];
  }

  function relativeLuminance([r, g, b]: [number, number, number]): number {
    const [rs, gs, bs] = [r, g, b].map((c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
  }

  function contrastRatio(fg: string, bg: string): number {
    const l1 = relativeLuminance(hexToRgb(fg));
    const l2 = relativeLuminance(hexToRgb(bg));
    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  }

  it("caption colour #6B7280 meets 4.5:1 on white", () => {
    expect(theme).toContain("#6B7280");
    const ratio = contrastRatio("#6B7280", "#FFFFFF");
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it("body2/text.secondary #596577 meets 4.5:1 on white", () => {
    expect(theme).toContain("#596577");
    const ratio = contrastRatio("#596577", "#FFFFFF");
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it("primary text #0F172A has high contrast on white", () => {
    const ratio = contrastRatio("#0F172A", "#FFFFFF");
    expect(ratio).toBeGreaterThanOrEqual(7);
  });
});

// -- VT-036-TC-015: Filter chips have aria-pressed ---------------------------

describe("VT-036-TC-015: Filter chips have aria-pressed", () => {
  const reviewSection = readUISrc("components/operations/ReviewSection.tsx");

  it("filter chips include aria-pressed attribute", () => {
    const pressedCount = (reviewSection.match(/aria-pressed/g) || []).length;
    expect(pressedCount).toBeGreaterThanOrEqual(2);
  });

  it("filter chip group has role='group' and aria-label", () => {
    expect(reviewSection).toContain('role="group"');
    expect(reviewSection).toContain('aria-label="Review filters"');
  });
});

// -- VT-036-TC-016: No window.confirm or alert calls ------------------------

describe("VT-036-TC-016: No native dialog calls in UI source", () => {
  const allTsxFiles = collectTsxFiles(UI_SRC);

  it("found UI source files to scan", () => {
    expect(allTsxFiles.length).toBeGreaterThan(20);
  });

  it("no window.confirm() calls", () => {
    const violations: string[] = [];
    for (const file of allTsxFiles) {
      const content = fs.readFileSync(file, "utf-8");
      const rel = path.relative(UI_SRC, file);
      if (/ConfirmDialog\.tsx$/.test(rel) || /\.test\./.test(rel)) continue;
      if (/window\.confirm\s*\(/.test(content)) {
        violations.push(rel);
      }
    }
    expect(violations).toEqual([]);
  });

  it("no window.alert() calls", () => {
    const violations: string[] = [];
    for (const file of allTsxFiles) {
      const content = fs.readFileSync(file, "utf-8");
      const rel = path.relative(UI_SRC, file);
      if (/\.test\./.test(rel)) continue;
      if (/window\.alert\s*\(/.test(content)) {
        violations.push(rel);
      }
    }
    expect(violations).toEqual([]);
  });
});

// -- VT-036-TC-017: AppShell uses Next.js Link -------------------------------

describe("VT-036-TC-017: AppShell uses Next.js Link", () => {
  const appShell = readUISrc("components/AppShell.tsx");

  it("imports Link from next/link", () => {
    expect(appShell).toMatch(/import\s+Link\s+from\s+["']next\/link["']/);
  });

  it("ListItemButton uses component={Link} and href", () => {
    expect(appShell).toContain("component={Link}");
    expect(appShell).toContain("href={item.path}");
  });
});

// -- VT-036-TC-018: Cursor rule exists and covers all standards --------------

describe("VT-036-TC-018: Cursor safety rule exists", () => {
  const rulePath = path.join(ROOT, ".cursor/rules/ui-safety.mdc");

  it("ui-safety.mdc file exists", () => {
    expect(fs.existsSync(rulePath)).toBe(true);
  });

  it("rule targets services/ui/src/**/*.tsx", () => {
    const content = fs.readFileSync(rulePath, "utf-8");
    expect(content).toContain("services/ui/src/**/*.tsx");
  });

  it("rule covers ConfirmDialog requirement", () => {
    const content = fs.readFileSync(rulePath, "utf-8");
    expect(content).toContain("ConfirmDialog");
  });

  it("rule covers heading requirement", () => {
    const content = fs.readFileSync(rulePath, "utf-8");
    expect(content).toMatch(/heading/i);
  });

  it("rule covers aria-label requirement", () => {
    const content = fs.readFileSync(rulePath, "utf-8");
    expect(content).toContain("aria-label");
  });

  it("rule bans native dialogs", () => {
    const content = fs.readFileSync(rulePath, "utf-8");
    expect(content).toMatch(/window\.confirm|alert\(\)/);
  });

  it("rule covers contrast", () => {
    const content = fs.readFileSync(rulePath, "utf-8");
    expect(content).toMatch(/contrast/i);
  });
});

// -- VT-036-TC-008 (supplementary): Error boundary files exist ---------------

describe("VT-036-TC-008: Error boundary files exist", () => {
  const appDir = path.join(UI_SRC, "app");

  it("global-error.tsx exists with recovery UI", () => {
    const content = readUISrc("app/global-error.tsx");
    expect(content).toContain("Try again");
    expect(content).toContain("Go to Dashboard");
    expect(content).toContain('component="h1"');
  });

  it("error.tsx exists with error message and recovery", () => {
    const content = readUISrc("app/error.tsx");
    expect(content).toContain("Try again");
    expect(content).toContain("error.message");
  });

  it("not-found.tsx exists with navigation back", () => {
    const content = readUISrc("app/not-found.tsx");
    expect(content).toContain("Page not found");
    expect(content).toContain("Go to Dashboard");
  });

  it("loading.tsx exists with accessible spinner", () => {
    const content = readUISrc("app/loading.tsx");
    expect(content).toContain("CircularProgress");
    expect(content).toContain("aria-label");
  });
});
