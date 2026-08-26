/**
 * Extra detect rules for 2WW letters: form name, sites, vitals, ECOG.
 *
 * Atlas trace: DI-26546721, DI-A0E69E38
 */
import type { FormSchemaItem, FormSchemaSection, SectionType } from "./formSchemaDetector";

const SITE_ENTITY: Record<string, string> = {
  cervix: "Cervical cancer suspected",
  ovary: "Ovarian cancer suspected",
  endometrium: "Endometrial cancer suspected",
  vagina: "Vaginal cancer suspected",
  vulva: "Vulval cancer suspected",
};

export function detectFormName(text: string): string {
  const lines = text
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.replace(/[#|*]/g, " ").trim())
    .filter(Boolean);
  const title = lines.find((line) =>
    /urgent\s+suspected\s+cancer|gynaecolog(?:ical|y).{0,40}(malignancy|2ww|referral)/i.test(
      line,
    ),
  );
  if (title) {
    return title.replace(/\s+/g, " ").slice(0, 120);
  }
  return "Referral form";
}

export function clinicalEntityText(label: string): string {
  const key = label.trim().toLowerCase().replace(/[^a-z]/g, "");
  return SITE_ENTITY[key] || label.trim();
}

export function observableItems(lines: string[]): FormSchemaItem[] {
  const items: FormSchemaItem[] = [];
  for (const raw of lines) {
    const line = raw.replace(/\s+/g, " ").trim();
    pushObservable(items, line, /\bBMI\b[:\s]*([\d.]+)?/i, "BMI", "Body mass index");
    pushObservable(items, line, /\bBP\b[:\s]*(\d+\s*\/\s*\d+)?/i, "BP", "Blood pressure");
    pushObservable(
      items,
      line,
      /\b(?:HR|heart rate)\b[:\s]*(\d+)?/i,
      "HR",
      "Heart rate",
    );
  }
  return items;
}

export function classifyNamedSection(label: string, body: string[]): SectionType | null {
  if (/minimum dataset/i.test(label)) {
    return observableItems(body).length ? "observable" : "admin";
  }
  if (/^bmi\b/i.test(label)) return "observable";
  if (/ecog/i.test(label)) return "scale";
  if (/pmb|awareness|holiday/i.test(label)) return "checkbox_multi";
  return null;
}

export function extraNamedHeaders(line: string): string | null {
  const stripped = line.replace(/^\s*[#|]+\s*/, "").trim();
  if (
    /^(pmb primary care(?:\s+pathway)?|patient awareness|blood results|bmi)\b/i.test(
      stripped,
    )
  ) {
    return stripped;
  }
  if (/\becog\b/i.test(stripped) && !/^section\s+/i.test(stripped)) {
    return stripped;
  }
  return null;
}

export function withSplitScales(sections: FormSchemaSection[]): FormSchemaSection[] {
  if (sections.some((item) => /ecog/i.test(item.label))) return sections;
  return sections;
}

export function withBmiSection(
  sections: FormSchemaSection[],
  lines: string[],
): FormSchemaSection[] {
  if (sections.some((section) => section.items.some((item) => /bmi/i.test(item.pattern)))) {
    return sections;
  }
  const items = observableItems(lines).filter((item) => /bmi/i.test(item.pattern));
  if (!items.length) return sections;
  return [
    ...sections,
    {
      section_id: "BMI",
      section_type: "observable",
      label: "BMI",
      start_pattern: "(?i)bmi",
      items,
    },
  ];
}

function pushObservable(
  items: FormSchemaItem[],
  line: string,
  pattern: RegExp,
  name: string,
  entity: string,
): void {
  if (!pattern.test(line)) return;
  if (items.some((item) => item.pattern === name)) return;
  items.push({
    pattern: name,
    entity_text: entity,
    semantic_tag: "observable_entity",
    assertion: "present",
  });
}
