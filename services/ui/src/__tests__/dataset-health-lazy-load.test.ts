import fs from "fs";
import path from "path";

const PANEL_PATH = path.resolve(
  __dirname,
  "..",
  "components",
  "gold-dataset",
  "DatasetHealthPanel.tsx",
);

describe("DatasetHealthPanel lazy diagnostics", () => {
  let source: string;

  beforeAll(() => {
    source = fs.readFileSync(PANEL_PATH, "utf8");
  });

  it("does not run corpus-wide diagnostics while collapsed", () => {
    expect(source).toMatch(/const \[expanded, setExpanded\] = useState\(false\)/);
    expect(source).toMatch(/if \(!expanded\) return;/);
    expect(source).toContain("Open to run checks");
  });
});
