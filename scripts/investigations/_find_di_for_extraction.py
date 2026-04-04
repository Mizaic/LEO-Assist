import glob, re

for f in sorted(glob.glob("design-controls/design-inputs/DI-LEO-AI-0*.yaml")):
    txt = open(f, encoding="utf-8").read()
    if any(k in txt.lower() for k in ["extraction", "abbreviat", "prompt", "llm", "ambig"]):
        ids = re.findall(r'id:\s*"(DI-LEO-AI-\d+)"', txt)
        titles = re.findall(r'title:\s*"([^"]+)"', txt)
        print(f'{ids[0] if ids else "?"}: {titles[0] if titles else "?"} [{f}]')
