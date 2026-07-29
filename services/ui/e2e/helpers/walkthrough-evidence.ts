/**
 * Sequential screenshot evidence for guided walkthroughs.
 * Every user click / typed value should get a named frame showing
 * what was done and the outcome on screen.
 */
import type { Page } from "@playwright/test";
import fs from "fs";
import path from "path";

export type Evidence = {
  /** Capture the current viewport as the next numbered frame. */
  shot: (slug: string) => Promise<string>;
  /** How many frames have been written. */
  count: () => number;
};

/** Wipe and recreate the pack directory, then return a numbered shot(). */
export function createWalkthroughEvidence(
  page: Page,
  screenshotDir: string,
): Evidence {
  fs.rmSync(screenshotDir, { recursive: true, force: true });
  fs.mkdirSync(screenshotDir, { recursive: true });
  let n = 0;
  return {
    shot: async (slug: string) => {
      n += 1;
      const name = `${String(n).padStart(3, "0")}-${slug}`;
      await page.screenshot({
        path: path.join(screenshotDir, `${name}.png`),
        fullPage: false,
      });
      return name;
    },
    count: () => n,
  };
}
