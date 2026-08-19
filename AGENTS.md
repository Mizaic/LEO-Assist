# Agent Standards — Cross-Tool Baseline

Lean baseline for AI coding agents (Cursor, Claude Code, Copilot, Gemini,
Codex) in Atlas and Atlas-owned products. Detailed rules live in `rules/`.
When this file and a `.mdc` rule disagree, the `.mdc` rule and
`rules/core/precedence.mdc` win.

## Conflict authority

Choose the **stricter** rule:

1. Patient safety and tenant isolation
2. Regulatory compliance and auditability
3. Security and secrets handling
4. Architecture constraints (Neo4j, async jobs, workflow graph execution)
5. Coding standards and style

Accessibility is non-negotiable. Safety UX wins over delight. Beauty must
never weaken safety, security, audit, or accessibility.

## Universal essentials

1. **Atlas is the company operating system.** Leadership sets policy and
   OKRs. Atlas owns person, team, process, report, product, event,
   location, and object. The person must still believe Atlas is the tool
   for their own OKRs. Put them on their next owned job.
   See `rules/core/atlas-operating-system.mdc`.

2. **One way of working.** New files follow this pack (Wave 1). Old files
   wait for a Wave 2 change. Standards, methods, tools, and look are
   this pack plus the Mizaic Brand Guidelines. See `NEW-WORK-CHECKLIST.md`.

3. **Design controls live in the MCP.** Never write a local YAML/JSON/
   Markdown design-control store. Product ID comes from the home-repo
   overlay. See `rules/design-controls/`.

4. **FHIR R4 for clinical data.** Experiences call the FHIR API only.
   Every query filters by `organization_id`.

5. **Secrets from Key Vault only.** No secrets in the repo. Never log them.

6. **Audit is append-only.** Record who, what, when, outcome.

7. **Humans approve regulated decisions.** Agents draft. No silent writes.
   You verify, then validate with Playwright and screenshots. You do not
   self-approve a User Need.

8. **Red then green.** Test-driven development. See `rules/core/tdd.mdc`.

9. **Plain English** at about UK reading age 11 for everything a person
   reads.

10. **Mizaic-Frontend kit.** Electric Blue `#0d46d6`, Overpass, Albert
    Sans, official logos. New UI is MUI. See `rules/core/brand-kit.mdc`.

11. **One change = one requirement.** If it is not traceable and testable,
    it is not done.

## Adopting this pack

```bash
./install.sh --target <repo> --profile core|craft|design-controls|testing|full
```

The installer writes `.cursor/.atlas-pack-version`. That file is the
quality record. Pack version is in `manifest.json`.
