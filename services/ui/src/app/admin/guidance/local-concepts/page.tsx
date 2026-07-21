"use client";

/**
 * Local clinical concept wizard -- guided create for LEO-local triggers
 * and narrative actions (package, aliases, extraction dry-run, approve).
 *
 * Atlas:
 *   UN: UN-13601C35
 *   DI: DI-FB0066CA
 *   DO: DO-7CF39715
 *   VT: VT-F266ECFB
 */
import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import {
  createLocalConceptWithAlias,
  createLocalTerminologyPackage,
  dryRunLocalConceptRecovery,
  listLocalTerminologyPackages,
  type LocalTerminologyPackage,
} from "@/lib/api/legacy";

const STEPS = [
  "Package",
  "Define",
  "Aliases",
  "Extraction dry-run",
  "Approve",
] as const;

type ConceptKind = "finding" | "procedure" | "narrative_action" | "both";
type PackageScope = "global" | "tenant";

export default function LocalConceptsWizardPage() {
  const [step, setStep] = useState(0);
  const [packages, setPackages] = useState<LocalTerminologyPackage[]>([]);
  const [packageId, setPackageId] = useState("");
  const [packageScope, setPackageScope] = useState<PackageScope>("global");
  const [newPackageName, setNewPackageName] = useState("");
  const [tenantOrgId, setTenantOrgId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [conceptKind, setConceptKind] = useState<ConceptKind>("finding");
  const [description, setDescription] = useState("");
  const [alias, setAlias] = useState("");
  const [sampleText, setSampleText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [dryRunMatches, setDryRunMatches] = useState<number | null>(null);
  const [approved, setApproved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const out = await listLocalTerminologyPackages();
        if (!cancelled) {
          setPackages(out.items || []);
          const globalDefault = (out.items || []).find(
            (p) => p.scope === "global" && p.status !== "retired",
          );
          if (globalDefault && !packageId) setPackageId(globalDefault.id);
        }
      } catch {
        if (!cancelled) setPackages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const canNext = useMemo(() => {
    if (step === 0) return packageId.trim().length > 0;
    if (step === 1) return displayName.trim().length >= 2;
    if (step === 2) return alias.trim().length >= 2;
    if (step === 3) return sampleText.trim().length >= 2;
    return true;
  }, [step, packageId, displayName, alias, sampleText]);

  const createPackage = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await createLocalTerminologyPackage({
        name: newPackageName.trim() || "New local package",
        scope: packageScope,
        org_id: packageScope === "tenant" ? tenantOrgId.trim() : undefined,
      });
      setPackages((prev) => [...prev, created]);
      setPackageId(created.id);
      setNewPackageName("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create package");
    } finally {
      setBusy(false);
    }
  };

  const runDryRun = async () => {
    setBusy(true);
    setError(null);
    try {
      const previewId =
        createdId ||
        `LEO-LOCAL-${displayName
          .trim()
          .toUpperCase()
          .replace(/[^A-Z0-9]+/g, "-")
          .replace(/-+/g, "-")
          .replace(/^-|-$/g, "")
          .slice(0, 48)}`;
      const result = await dryRunLocalConceptRecovery({
        sample_text: sampleText,
        aliases: [
          {
            form: alias,
            concept_id: previewId,
            fsn: `${displayName} (LEO local)`,
          },
        ],
      });
      setDryRunMatches(result.matched_count);
      if (!createdId) setCreatedId(previewId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dry-run failed");
      setDryRunMatches(0);
    } finally {
      setBusy(false);
    }
  };

  const approveAndCreate = async () => {
    if (!packageId.trim()) {
      setError("Select a terminology package before approving.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const out = await createLocalConceptWithAlias({
        display_name: displayName.trim(),
        alias: alias.trim(),
        concept_kind: conceptKind,
        description: description.trim() || undefined,
        concept_id: createdId || undefined,
        package_id: packageId.trim(),
        approve: true,
      });
      setCreatedId(out.concept.id);
      setApproved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create local concept");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box sx={{ p: 2, maxWidth: 720 }} data-testid="local-concepts-wizard">
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 0.5 }}>
        Local clinical concepts
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Create a LEO-local trigger or narrative action in a terminology package,
        add an alias, test extraction, then approve. Audit domains stay on real
        SNOMED codes only.
      </Typography>

      <Stepper activeStep={step} sx={{ mb: 3 }}>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {step === 0 && (
        <Stack spacing={2} data-testid="wizard-step-package">
          <TextField
            select
            label="Terminology package"
            value={packageId}
            onChange={(e) => setPackageId(e.target.value)}
            fullWidth
            required
            helperText="Global packages apply everywhere. Tenant packages apply only to one organisation."
            inputProps={{ "data-testid": "local-concept-package" }}
          >
            {packages.length === 0 && (
              <MenuItem value="" disabled>
                No packages yet -- create one below
              </MenuItem>
            )}
            {packages.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {p.name} ({p.scope}
                {p.org_id ? ` / ${p.org_id}` : ""}) -- {p.status}
              </MenuItem>
            ))}
          </TextField>
          <Typography variant="subtitle2">Or create a package</Typography>
          <TextField
            select
            label="Package scope"
            value={packageScope}
            onChange={(e) => setPackageScope(e.target.value as PackageScope)}
            fullWidth
            inputProps={{ "data-testid": "local-concept-package-scope" }}
          >
            <MenuItem value="global">Global (all organisations)</MenuItem>
            <MenuItem value="tenant">This organisation (tenant)</MenuItem>
          </TextField>
          {packageScope === "tenant" && (
            <TextField
              label="Organisation id"
              value={tenantOrgId}
              onChange={(e) => setTenantOrgId(e.target.value)}
              fullWidth
              required
              inputProps={{ "data-testid": "local-concept-package-org" }}
            />
          )}
          <TextField
            label="New package name"
            value={newPackageName}
            onChange={(e) => setNewPackageName(e.target.value)}
            fullWidth
            inputProps={{ "data-testid": "local-concept-package-name" }}
          />
          <Button
            variant="outlined"
            onClick={createPackage}
            disabled={
              busy ||
              (packageScope === "tenant" && !tenantOrgId.trim())
            }
            data-testid="local-concept-create-package"
          >
            Create package
          </Button>
          {!packageId.trim() && (
            <Alert severity="warning" data-testid="local-concept-package-required">
              Select or create a package before continuing.
            </Alert>
          )}
        </Stack>
      )}

      {step === 1 && (
        <Stack spacing={2} data-testid="wizard-step-define">
          <TextField
            label="Display name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            fullWidth
            inputProps={{ "data-testid": "local-concept-display-name" }}
          />
          <TextField
            select
            label="Kind"
            value={conceptKind}
            onChange={(e) => setConceptKind(e.target.value as ConceptKind)}
            fullWidth
            inputProps={{ "data-testid": "local-concept-kind" }}
          >
            <MenuItem value="finding">Finding trigger</MenuItem>
            <MenuItem value="narrative_action">Narrative action</MenuItem>
            <MenuItem value="procedure">Procedure</MenuItem>
            <MenuItem value="both">Both</MenuItem>
          </TextField>
          <TextField
            label="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            fullWidth
            multiline
            minRows={2}
          />
        </Stack>
      )}

      {step === 2 && (
        <Stack spacing={2} data-testid="wizard-step-aliases">
          <TextField
            label="Alias phrase clinicians write"
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
            required
            fullWidth
            helperText="Exact phrase used for recovery and Surface Form mapping"
            inputProps={{ "data-testid": "local-concept-alias" }}
          />
        </Stack>
      )}

      {step === 3 && (
        <Stack spacing={2} data-testid="wizard-step-extraction">
          <TextField
            label="Sample clinical text"
            value={sampleText}
            onChange={(e) => setSampleText(e.target.value)}
            required
            fullWidth
            multiline
            minRows={4}
            inputProps={{ "data-testid": "local-concept-sample-text" }}
          />
          <Button
            variant="outlined"
            onClick={runDryRun}
            disabled={busy || !canNext}
            data-testid="local-concept-dry-run"
          >
            Run dry-run
          </Button>
          {dryRunMatches !== null && (
            <Alert
              severity={dryRunMatches > 0 ? "success" : "warning"}
              data-testid="local-concept-dry-run-result"
            >
              {dryRunMatches > 0
                ? `Matched ${dryRunMatches} local concept span(s) in the sample.`
                : "No match. Check the alias spelling against the sample text."}
            </Alert>
          )}
        </Stack>
      )}

      {step === 4 && (
        <Stack spacing={2} data-testid="wizard-step-approve">
          <Alert severity="info">
            Approving creates the local Concept in the selected package, maps
            the alias, and marks the Surface Form approved for runtime resolve.
            It will not appear in Audit Domain SNOMED search.
          </Alert>
          <Typography variant="body2">
            Package: <strong>{packageId}</strong>
            <br />
            Name: <strong>{displayName}</strong>
            <br />
            Alias: <strong>{alias}</strong>
            <br />
            Kind: <strong>{conceptKind}</strong>
          </Typography>
          <Button
            variant="contained"
            onClick={approveAndCreate}
            disabled={busy || approved || !packageId.trim()}
            data-testid="local-concept-approve"
          >
            {approved ? "Approved" : "Approve and create"}
          </Button>
          {approved && createdId && (
            <Alert severity="success" data-testid="local-concept-approved">
              Created {createdId}. You can attach it in Clinical Guidelines rule
              editor search (Local chip).
            </Alert>
          )}
        </Stack>
      )}

      <Stack direction="row" spacing={1} sx={{ mt: 3 }}>
        <Button
          disabled={step === 0 || busy}
          onClick={() => setStep((s) => Math.max(0, s - 1))}
        >
          Back
        </Button>
        {step < STEPS.length - 1 && (
          <Button
            variant="contained"
            disabled={!canNext || busy}
            onClick={() => setStep((s) => s + 1)}
            data-testid="local-concept-next"
          >
            Next
          </Button>
        )}
      </Stack>
    </Box>
  );
}
