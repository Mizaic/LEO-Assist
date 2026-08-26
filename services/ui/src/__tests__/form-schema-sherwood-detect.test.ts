/**
 * Sherwood Forest 2WW gynae letter -- local detect and completeness seed.
 *
 * Atlas trace: DI-26546721, DI-A0E69E38, UN-3B25A20E
 */
import { detectFormName, detectSections } from "../components/operations/formSchemaDetector";
import { seedCompletenessGroups } from "../components/operations/formSchemaCompletenessSeed";

export const SHERWOOD_GYNAE_LETTER = `
Sherwood Forest Hospitals NHS Foundation Trust
URGENT SUSPECTED CANCER REFERRAL FOR SUSPECTED GYNAECOLOGICAL MALIGNANCY

I confirm that the patient is registered at this practice
Hospital number
Patient details
Practice details

Section A: Gynaecological Cancer type suspected
Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]
IF referring a suspected endometrial cancer you MUST have arranged a USC/urgent
transvaginal ultrasound scan (TVUS).
IF ovary suspected MUST arrange Ca125.

Section B: Signs/symptoms for 14-day rule criteria
B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]
B2. Lesion suspicious on vulva | Yes [ ] No [ ]
B3. Palpable pelvic mass | Yes [ ] No [ ]
B4. Ascites | Yes [ ] No [ ]
B5. Postmenopausal bleeding | Yes [ ] No [ ]
B6. Persistent intermenstrual bleeding | Yes [ ] No [ ]
B7. Vulval lump | Yes [ ] No [ ]
B8. Cervical lesion | Yes [ ] No [ ]
B9. Suspicion of ovarian cancer | Yes [ ] No [ ]

PMB primary care pathway
Ultrasound arranged [ ] Yes
Hysteroscopy arranged [ ] Yes
Pipelle biopsy [ ] Yes
Hormone therapy stopped [ ] Yes
If all negative, consider discharge with advice.

Patient awareness
Patient informed this is a suspected cancer referral [ ]
Patient available in next two weeks [ ]
Holiday planned in next two weeks [ ]

Section C: Further Clinical details
BMI: 20.2
Cognitive impairment Yes [ ] No [X]
Vaginal discharge 10/7 yellowish colour. Polyp noted.

Section D: Investigations performed
MANDATORY tests: FBC LFTs UEs Calcium
BLOODS DONE TODAY
CA125
FBC
UE
LFT

Section E: PERFORMANCE STATUS
Clinical Frailty Scale 1. Very Fit [X] 2. Fit [ ] 3. Managing well [ ]
Patient Fitness (ECOG STATUS): 0 [ ] 1 [X] 2 [ ] 3 [ ] 4 [ ]

Minimum Dataset
BP 140/80
HR 70
NHS Number: 718 563 0207

Section F: Allergies and Medication
Allergies: None
Medication: None
`;

describe("detectFormName", () => {
  it("pre-fills the form name from the first clinical title line", () => {
    const name = detectFormName(SHERWOOD_GYNAE_LETTER);
    expect(name.toLowerCase()).toMatch(/gynaecolog|urgent suspected cancer/);
    expect(name).not.toBe("Referral form");
  });
});

describe("detectSections Sherwood 2WW gynae", () => {
  const sections = detectSections(SHERWOOD_GYNAE_LETTER);

  it("does not hide the letter clinical sections", () => {
    const ids = sections.map((s) => s.section_id);
    expect(ids).toEqual(expect.arrayContaining(["A", "B", "C", "D", "E"]));
    expect(sections.some((s) => /pmb/i.test(s.label))).toBe(true);
    expect(sections.some((s) => /awareness/i.test(s.label))).toBe(true);
    expect(sections.some((s) => /ecog/i.test(s.label))).toBe(true);
    expect(sections.some((s) => /minimum dataset/i.test(s.label))).toBe(true);
  });

  it("maps site boxes to clinical entity text", () => {
    const sectionA = sections.find((s) => s.section_id === "A");
    const cervix = sectionA?.items.find((item) => /cervix/i.test(item.pattern));
    expect(cervix?.entity_text).toBe("Cervical cancer suspected");
    expect(cervix?.entity_text).not.toMatch(/checked on referral form/);
  });

  it("captures BMI as an observable field", () => {
    const bmi = sections.find(
      (s) =>
        s.section_type === "observable" &&
        s.items.some((item) => /bmi/i.test(item.pattern)),
    );
    expect(bmi).toBeDefined();
  });

  it("keeps Minimum Dataset BP and HR as observables, not admin skip", () => {
    const dataset = sections.find((s) => /minimum dataset/i.test(s.label));
    expect(dataset).toBeDefined();
    expect(dataset?.section_type).toBe("observable");
    const names = (dataset?.items ?? []).map((item) => item.pattern.toLowerCase());
    expect(names.some((name) => name.includes("bp") || name.includes("blood pressure"))).toBe(
      true,
    );
    expect(names.some((name) => name.includes("hr") || name.includes("heart"))).toBe(true);
  });

  it("detects ECOG as a second scale", () => {
    const ecog = sections.find((s) => /ecog/i.test(s.label));
    expect(ecog?.section_type).toBe("scale");
  });

  it("keeps Section D as ordered tests including mandatory bloods", () => {
    const sectionD = sections.find((s) => s.section_id === "D");
    expect(sectionD?.section_type).toBe("ordered_tests");
    expect(sectionD?.label.toLowerCase()).toMatch(/investigation|section d/);
  });

  it("still skips trust confirmation and hospital number as admin", () => {
    const admin = sections.filter((s) => s.section_type === "admin");
    expect(admin.some((s) => /patient details|practice details|hospital number/i.test(s.label))).toBe(
      true,
    );
  });
});

describe("seedCompletenessGroups Sherwood 2WW gynae", () => {
  const sections = detectSections(SHERWOOD_GYNAE_LETTER);
  const groups = seedCompletenessGroups(SHERWOOD_GYNAE_LETTER, sections);

  it("seeds Section A as 1-of suspected sites", () => {
    const group = groups.find((item) => /section a|cancer type|site/i.test(item.name));
    expect(group?.kind).toBe("one_of");
    expect((group?.members ?? []).length).toBeGreaterThanOrEqual(4);
  });

  it("seeds Section B as 1-of B1-B9", () => {
    const group = groups.find((item) => /section b|criteria|signs/i.test(item.name));
    expect(group?.kind).toBe("one_of");
    expect((group?.members ?? []).map((m) => m.name).join(" ")).toMatch(/B1/);
    expect((group?.members ?? []).map((m) => m.name).join(" ")).toMatch(/B9/);
  });

  it("seeds if Endometrium then TVUS", () => {
    const group = groups.find((item) => item.kind === "if_then" && /endometr/i.test(item.if_group?.name ?? ""));
    expect(group?.then_group?.name.toLowerCase()).toMatch(/tvus|ultrasound/);
  });

  it("seeds if Ovary then Ca125", () => {
    const group = groups.find((item) => item.kind === "if_then" && /ovar/i.test(item.if_group?.name ?? ""));
    expect(group?.then_group?.name.toLowerCase()).toMatch(/ca125|ca 125/);
  });

  it("seeds Section D bloods as mandatory", () => {
    const group = groups.find((item) => /blood|section d|mandatory test/i.test(item.name));
    expect(group?.kind).toBe("mandatory");
    expect(group?.required).toBe(true);
  });

  it("seeds Minimum Dataset BP and HR as mandatory observables", () => {
    const names = groups.map((item) => item.name.toLowerCase()).join(" | ");
    expect(names).toMatch(/blood pressure|bp/);
    expect(names).toMatch(/heart rate|hr/);
  });
});
