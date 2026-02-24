# Usability Engineering Prompt

**Purpose:** Apply IEC 62366-1 usability engineering to the Primary Care Clinical Pathway Audit Platform. This prompt defines the process and deliverables for the Usability Engineering File (UEF).

**References:**
- IEC 62366-1:2015 + Amendment 1:2020 (Medical devices — Application of usability engineering)
- `design-controls/intended-use.md` (DC-IU-001)
- `design-controls/neo4j-nlp-terminology-schema.md`

---

## 1. Scope

The platform is SaMD for retrospective clinical pathway audit. User interfaces include:
- **HITL Review UI** — human reviewers validate AI-generated coding proposals, approve/edit/reject, and submit decisions
- **API** — programme administrators and system operators trigger pipelines, configure programmes
- **No direct patient-facing interface**

---

## 2. Execute the Following Tasks

### Task 1: Create Use Specification (USE-SPEC-001)

Create `docs/usability/use-specification.md` containing:

1. **User groups** — from intended use Section 3, with characteristics affecting usability:
   - Clinical audit teams
   - Pathway coordinators
   - Human reviewers (clinical coders)
   - Programme administrators
   - System administrators

2. **Use environment** — from intended use Section 5 (NHS primary care, cloud-hosted, REST API)

3. **User interface description** — describe the HITL review UI components and workflows

4. **Training and knowledge** — assumptions about reviewer training (SNOMED CT, clinical coding)

### Task 2: Create User Needs (USER-NEEDS-001)

Create `docs/usability/user-needs.md` with user needs derived from intended use and use specification. Format as traceable needs (ID, need statement, source, acceptance criterion).

### Task 3: Create Critical Task List (CRITICAL-TASKS-001)

Create `docs/usability/critical-tasks.md` identifying tasks where use error could cause harm. For each:
- Task ID, description, user group
- Use-related hazard (if any)
- Risk level (high/medium/low)
- Mitigation

Focus on: validating coding proposals, approving/rejecting episodes, interpreting alerts.

### Task 4: Create Use-Related Hazard Analysis (URHA-001)

Create `docs/usability/use-related-hazards.md` with:
- Hazard ID, description, cause, effect
- Severity and probability
- Risk control measure
- Residual risk

Focus on: incorrect approval of wrong coding, missed rejection of unsafe proposal, confusion in review queue.

### Task 5: Create Usability Engineering File Index (UEF-INDEX)

Create `docs/usability/README.md` as the UEF index linking all documents and summarising the usability process.

---

## 3. Output Format

All documents shall:
- Use markdown with clear headings
- Include document ID, version, status, date
- Cross-reference design-controls and each other
- Be suitable for design control traceability

---

## 4. Execution Order

1. Use Specification (foundation)
2. User Needs (derived from use spec + intended use)
3. Critical Tasks (from user needs)
4. Use-Related Hazards (from critical tasks)
5. UEF Index (links all)
