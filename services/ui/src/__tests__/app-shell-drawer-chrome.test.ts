/**
 * App shell menu rail -- midnight navy structural chrome.
 * Cosmetic. Brand dark surfaces use white wordmarks.
 */
import fs from "fs";
import path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("AppShell drawer chrome", () => {
  const shell = readFile("services/ui/src/components/AppShell.tsx");
  const chrome = readFile("services/ui/src/components/app-shell/drawerChrome.ts");

  it("uses midnight navy paper and press-scale on rail items", () => {
    expect(chrome).toMatch(/color\.brand\.primaryDark/);
    expect(chrome).toMatch(/scale\(0\.97\)/);
    expect(shell).toMatch(/drawerPaperSx/);
    expect(shell).toMatch(/railButtonSx\(isActive\)/);
  });

  it("uses dark wordmarks on the nav rail", () => {
    expect(shell).toMatch(/LeoO size=\{26\} variant="dark"/);
    expect(shell).toMatch(/LeoLogo height=\{28\} variant="dark"/);
    expect(shell).not.toMatch(/LeoO[\s\S]{0,40}variant="light"/);
  });
});
