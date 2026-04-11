"""Explore demographics section of Woodbrook NCDA report."""

import zipfile
import xml.etree.ElementTree as ET


def get_paras_with_images(docx_path):
    with zipfile.ZipFile(docx_path) as z:
        xml_data = z.read("word/document.xml")
    root = ET.fromstring(xml_data)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for para in root.iter(ns + "p"):
        texts = [t.text or "" for t in para.iter(ns + "t")]
        text = "".join(texts).strip()
        images = []
        for blip in para.iter(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
        ):
            embed = blip.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed",
                "",
            )
            if embed:
                images.append(embed)
        paragraphs.append({"text": text, "images": images})
    return paragraphs


paras = get_paras_with_images("external_content/NCDA2018_19_Woodbrook_report.docx")

print("=== DEMOGRAPHICS SECTION (lines 325-420) ===")
for i in range(325, 420):
    if i >= len(paras):
        break
    p = paras[i]
    if p["text"] or p["images"]:
        txt = p["text"][:120]
        imgs = p["images"]
        print(f"[{i}] {txt}  | imgs={imgs}")
