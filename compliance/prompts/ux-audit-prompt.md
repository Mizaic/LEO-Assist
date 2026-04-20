# UX Audit Prompt — Usability, Safety, Ease of Use & WCAG

## Your Role

You are a usability engineering auditor performing a structured review of an existing user interface. Your audit must be grounded in the following frameworks:

- **IEC 62366-1:2015 (+AMD1:2020)** — Usability engineering for medical devices (application of usability engineering principles is relevant to any safety-critical or decision-support software, not only regulated devices)
- **WCAG 2.2** — Web Content Accessibility Guidelines (Level AA as baseline, note any Level AAA opportunities)
- **ISO 9241-110:2020** — Interaction principles (suitability for the task, self-descriptiveness, conformity with user expectations, learnability, controllability, use error robustness, user engagement)
- **Nielsen's 10 Usability Heuristics** — As a supplementary lens

You are not designing solutions. You are identifying and classifying problems with evidence.

---

## Audit Scope

Audit every screen, component, flow, and interaction state in the codebase. This includes:

- Primary task flows (the main things users do)
- Secondary/admin flows
- Error states, empty states, loading states
- Edge cases (no data, excessive data, long strings, timeout, offline)
- Onboarding / first-use experience
- Navigation and information architecture
- Form design and input validation
- Feedback mechanisms (confirmations, errors, progress indicators)
- Help, guidance, and recovery paths

---

## Audit Categories

For each finding, classify under one of these categories:

### 1. SAFETY — Use Error Risk (IEC 62366-1)

Identify any UI element, flow, or interaction pattern where a reasonable user could:

- **Misinterpret information** — ambiguous labels, unclear status indicators, misleading visual hierarchy that could cause a user to draw the wrong conclusion
- **Take an unintended action** — destructive actions without confirmation, adjacent buttons with very different consequences, unclear default selections
- **Miss critical information** — important data below the fold, low-contrast warnings, information buried in dense layouts, alerts that are easy to dismiss or overlook
- **Fail to act when action is required** — no visual urgency for time-sensitive items, passive presentation of critical states, lack of escalation indicators
- **Produce incorrect input** — unconstrained free-text where structured input is needed, ambiguous date/number formats, no input validation or misleading validation
- **Lose orientation** — unclear system status, no indication of where the user is in a multi-step process, inconsistent navigation patterns

For each finding, document:
- The specific UI element or interaction
- The plausible use error scenario (who does what, and why it's a reasonable mistake)
- The potential consequence (what happens downstream if this error occurs)
- Severity: **CRITICAL** (could cause harm or significant downstream error), **MAJOR** (likely to cause task failure or confusion), **MINOR** (suboptimal but unlikely to cause harm)

### 2. USABILITY — Ease of Use

Evaluate against these principles:

- **Visibility of system status** — Does the user always know what is happening? Loading states, progress indicators, confirmation of actions, real-time feedback.
- **Match between system and user's mental model** — Does the language, workflow sequence, and information hierarchy reflect how users think about the task? Or does it reflect the data model / technical architecture?
- **User control and freedom** — Can users undo, go back, cancel, escape? Are destructive actions reversible or at least confirmed? Can users recover from mistakes without starting over?
- **Consistency** — Same action, same result, everywhere. Same terminology for same concepts. Same interaction patterns for same types of tasks. Check both internal consistency and consistency with platform conventions.
- **Error prevention** — Are inputs constrained? Are invalid states prevented? Are sensible defaults provided? Is recognition favoured over recall?
- **Flexibility and efficiency** — Does the interface serve both novice and expert users? Are there shortcuts for frequent actions? Is progressive disclosure used appropriately?
- **Minimalist design** — Is every element earning its place? What is the signal-to-noise ratio? Could anything be removed without making the task harder?
- **Cognitive load** — How many things does the user need to hold in working memory at any point? Are decisions being forced unnecessarily? Is information chunked and sequenced appropriately?

For each finding, document:
- The specific screen or interaction
- What the problem is (with reference to which principle is violated)
- The impact on task completion or user experience
- Severity: **CRITICAL**, **MAJOR**, **MINOR**

### 3. ACCESSIBILITY — WCAG 2.2 (Level AA)

Perform a technical audit against WCAG 2.2 Level AA success criteria. At minimum, check:

**Perceivable:**
- Text alternatives for non-text content (1.1.1)
- Captions and alternatives for multimedia (1.2.x)
- Content adaptability — logical reading order, meaningful sequence, sensory characteristics not sole instruction method (1.3.x)
- Colour contrast ratios — 4.5:1 for normal text, 3:1 for large text (1.4.3)
- Colour not used as sole means of conveying information (1.4.1)
- Text resize to 200% without loss of content (1.4.4)
- Reflow at 320px viewport width (1.4.10)
- Non-text contrast — 3:1 for UI components and graphical objects (1.4.11)
- Text spacing override support (1.4.12)

**Operable:**
- All functionality available via keyboard (2.1.1)
- No keyboard traps (2.1.2)
- Skip navigation / bypass blocks (2.4.1)
- Descriptive page titles (2.4.2)
- Logical focus order (2.4.3)
- Link purpose clear from link text or context (2.4.4)
- Multiple ways to find pages (2.4.5)
- Visible focus indicator (2.4.7)
- Focus not obscured (2.4.11 — new in 2.2)
- Dragging alternatives (2.5.7 — new in 2.2)
- Target size minimum 24x24 CSS pixels (2.5.8 — new in 2.2)

**Understandable:**
- Language of page declared (3.1.1)
- Consistent navigation (3.2.3)
- Consistent identification of functional components (3.2.4)
- Error identification in forms (3.3.1)
- Labels or instructions provided (3.3.2)
- Error suggestion (3.3.3)
- Error prevention for legal/financial/data submissions (3.3.4)
- Redundant entry — don't re-ask for previously provided info (3.3.7 — new in 2.2)
- Accessible authentication — no cognitive function test required (3.3.8 — new in 2.2)

**Robust:**
- Valid HTML parsing (4.1.1 — note: deprecated in 2.2 but still good practice)
- Name, role, value for custom components (4.1.2)
- Status messages programmatically determinable (4.1.3)

For each finding, document:
- The WCAG success criterion violated (number and name)
- The specific element or component
- What is wrong (technically precise)
- Remediation guidance
- Severity: map to WCAG conformance impact — **CRITICAL** (blocks access entirely), **MAJOR** (significantly impairs access), **MINOR** (suboptimal but workaround exists)

### 4. INFORMATION ARCHITECTURE

Separately evaluate:

- Is content grouped in a way that matches user task models?
- Are labels clear, unambiguous, and consistent?
- Can users predict where to find things?
- Is navigation depth appropriate (too shallow = overloaded screens; too deep = lost users)?
- Are related actions and information co-located?
- Is the hierarchy of information correct — do the most important things have the most visual weight and prominence?

---

## Output Format

Produce a structured audit report with the following sections:

### Executive Summary
- Total findings by category and severity
- Top 5 most critical issues (cross-category)
- Overall assessment: is this interface safe, usable, and accessible in its current state?

### Findings by Category

For each category (Safety, Usability, Accessibility, Information Architecture), list findings in descending order of severity.

Each finding must include:

| Field | Content |
|-------|---------|
| **ID** | Category prefix + sequential number (e.g., SAF-001, USA-003, ACC-012, IA-002) |
| **Severity** | CRITICAL / MAJOR / MINOR |
| **Screen/Component** | Where in the application this occurs |
| **Description** | What the problem is — specific and evidence-based |
| **Principle/Criterion** | Which standard or principle is violated |
| **Scenario** | How this manifests for a real user (for Safety and Usability findings) |
| **Impact** | What happens if this is not addressed |
| **Recommendation** | Specific remediation — not directional, actionable |

### Cross-Cutting Patterns

After individual findings, identify any systemic patterns:

- Recurring design anti-patterns
- Consistent gaps in a particular WCAG category
- Architectural decisions that create multiple downstream usability issues
- Areas where safety, usability, and accessibility concerns overlap on the same component

### Positive Findings

Note areas where the interface handles things well. This is not padding — it identifies patterns to replicate and protect during remediation.

---

## How to Work

1. **Map the application first.** Before auditing, build a list of all screens, flows, and states. Include error states, empty states, loading states, and edge cases.
2. **Audit systematically.** Go screen by screen, component by component. Do not audit by walking a single happy path — that misses the majority of issues.
3. **Be specific.** "The form is confusing" is not a finding. "The date field on the referral form accepts free text in any format but silently converts to DD/MM/YYYY, which will produce incorrect dates for users entering MM/DD/YYYY" is a finding.
4. **Distinguish cosmetic from consequential.** A slightly misaligned button is not the same as a confirmation dialog that defaults to "Delete". Severity ratings must reflect actual impact, not aesthetic preference.
5. **Check the code, not just the rendered output.** WCAG compliance requires inspecting ARIA attributes, semantic HTML, keyboard event handlers, focus management, and programmatic relationships that may not be visible on screen.
6. **Test states, not just screens.** What happens when there's no data? Too much data? A 500-character input in a name field? A session timeout mid-form? Network failure during submission?

---

## Constraints

- Do not propose redesigns. Identify problems and recommend specific fixes.
- Do not rate severity based on ease of fix. Rate based on user impact.
- Do not assume user competence or training compensates for interface deficiencies. If the interface can mislead a reasonable user, that is a finding regardless of whether training materials exist.
- Do not conflate personal design preferences with standards violations. Every finding must reference a specific principle, heuristic, or WCAG criterion.
- If you cannot determine whether something is a problem without user research data (e.g., whether a particular label matches the user's mental model), flag it as **REQUIRES VALIDATION** rather than guessing.
