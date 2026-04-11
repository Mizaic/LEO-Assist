import zipfile, xml.etree.ElementTree as ET

docx = "external_content/NCDA2018_19_Woodbrook_report.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"

with zipfile.ZipFile(docx) as z:
    with z.open("word/document.xml") as f:
        tree = ET.parse(f)

body = tree.getroot().find(f"{{{W}}}body")
paragraphs = list(body)

window_text = []
for elem in paragraphs:
    text = "".join(n.text or "" for n in elem.findall(f".//{{{W}}}t"))
    rids = [
        b.get(f"{{{R}}}embed")
        for b in elem.findall(f".//{{{PIC}}}blipFill/{{{A}}}blip")
    ]
    rids = [r for r in rids if r]
    if text.strip():
        window_text.append(text.strip())
        if len(window_text) > 5:
            window_text.pop(0)
    if rids:
        ctx = " | ".join(window_text[-4:])
        if "nvestig" in ctx or "nvestig" in text:
            print(f"Image rIds: {rids}")
            print(f"  Context: {ctx[:200]}")
            print()
