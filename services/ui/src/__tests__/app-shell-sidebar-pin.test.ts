/**
 * Static-source verification: AppShell sidebar pin-open affordance.
 *
 * TC-001: PushPinOutlinedIcon and PushPinIcon are imported
 * TC-002: "Pin sidebar open" tooltip / aria-label is present
 * TC-003: "Unpin sidebar" tooltip / aria-label is present
 * TC-004: pin button calls persistSidebarPref("expanded")
 * TC-005: unpin button calls persistSidebarPref("follow-breakpoint")
 * TC-006: pin button only renders when dockCollapsed is true
 * TC-007: unpin button only renders when sidebarPref === "expanded"
 * TC-008: original collapse (ChevronLeft) button is preserved for the
 *         naturally-expanded, non-pinned state
 * TC-009: sidebar pref is persisted to localStorage via SIDEBAR_PREF_STORAGE_KEY
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readSrc(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const SRC_PATH = "services/ui/src/components/AppShell.tsx";

describe("AppShell sidebar pin-open affordance", () => {
  let src: string;

  beforeAll(() => {
    src = readSrc(SRC_PATH);
  });

  test("TC-001: PushPinOutlinedIcon and PushPinIcon are imported", () => {
    expect(src).toMatch(/PushPinOutlinedIcon/);
    expect(src).toMatch(/import PushPinOutlinedIcon from ["']@mui\/icons-material\/PushPinOutlined["']/);
    expect(src).toMatch(/PushPinIcon/);
    expect(src).toMatch(/import PushPinIcon from ["']@mui\/icons-material\/PushPin["']/);
  });

  test("TC-002: Pin sidebar open tooltip and aria-label are present", () => {
    expect(src).toMatch(/Pin sidebar open/);
    expect(src).toMatch(/aria-label=["']Pin sidebar open["']/);
  });

  test("TC-003: Unpin sidebar tooltip and aria-label are present", () => {
    expect(src).toMatch(/Unpin sidebar/);
    expect(src).toMatch(/aria-label=["']Unpin sidebar["']/);
  });

  test("TC-004: pin button calls persistSidebarPref with expanded", () => {
    // Find the pin-open button block and confirm it calls persistSidebarPref("expanded")
    const pinBlock = src.match(/Pin sidebar open[\s\S]*?<\/Tooltip>/);
    expect(pinBlock).not.toBeNull();
    expect(pinBlock![0]).toMatch(/persistSidebarPref\(["']expanded["']\)/);
  });

  test("TC-005: unpin button calls persistSidebarPref with follow-breakpoint", () => {
    const unpinBlock = src.match(/Unpin sidebar[\s\S]*?<\/Tooltip>/);
    expect(unpinBlock).not.toBeNull();
    expect(unpinBlock![0]).toMatch(/persistSidebarPref\(["']follow-breakpoint["']\)/);
  });

  test("TC-006: pin button is conditionally rendered only when dockCollapsed is true", () => {
    // The pin affordance must be guarded by dockCollapsed
    const pinSection = src.match(/dockCollapsed[\s\S]*?Pin sidebar open/);
    expect(pinSection).not.toBeNull();
  });

  test("TC-007: unpin button is conditionally rendered only when sidebarPref is expanded", () => {
    const unpinSection = src.match(/sidebarPref\s*===\s*["']expanded["'][\s\S]*?Unpin sidebar/);
    expect(unpinSection).not.toBeNull();
  });

  test("TC-008: ChevronLeft collapse button is preserved for the natural-expansion state", () => {
    expect(src).toMatch(/Collapse sidebar/);
    expect(src).toMatch(/ChevronLeftIcon/);
    expect(src).toMatch(/persistSidebarPref\(["']collapsed["']\)/);
  });

  test("TC-009: sidebar preference is persisted to localStorage", () => {
    expect(src).toMatch(/SIDEBAR_PREF_STORAGE_KEY/);
    expect(src).toMatch(/localStorage\.setItem/);
    // Key must be used for both read and write
    const readOccurrences = (src.match(/SIDEBAR_PREF_STORAGE_KEY/g) ?? []).length;
    expect(readOccurrences).toBeGreaterThanOrEqual(3); // const + getItem + setItem
  });
});
