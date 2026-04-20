/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-21936FDD")
 */
"use client";

/**
 * Onboarding Acceptance Wizard
 *
 * Shown to a primary user after clicking their invite email link and
 * completing Azure AD sign-in. Detects onboarding_status: pending on
 * their org and guides them through a short wizard:
 *
 *   Step 1 — Confirm organisation details (name, ODS code, type)
 *   Step 2 — Optionally invite a second admin user
 *   Step 3 — Confirmation / redirect to /portal
 *
 * On completion: PATCH /api/admin/orgs/{id} sets onboarding_status: complete.
 */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Chip from "@mui/material/Chip";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { useAuth } from "@/lib/authContext";
import { listOrgs, type Org } from "@/lib/api/admin";
import { apiFetch } from "@/lib/api/client";

const STEPS = ["Confirm your organisation", "Invite a colleague (optional)", "All done"];

const ORG_TYPE_LABELS: Record<string, string> = {
  gp: "GP Practice",
  pcn: "PCN (Primary Care Network)",
  icb: "Integrated Care Board",
  alliance: "Cancer Alliance",
  organization: "Organisation",
};

export default function OnboardingAcceptPage() {
  const { session, status } = useAuth();
  const router = useRouter();

  const [step, setStep] = useState(0);
  const [org, setOrg] = useState<Org | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);

  // Step 2 — invite a colleague
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteSent, setInviteSent] = useState(false);
  const [inviting, setInviting] = useState(false);

  // Load the caller's pending org
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const orgs = await listOrgs();
      const callerOrgId = session?.organizations?.[0]?.id;
      const found = orgs.find((o) => o.id === callerOrgId) ?? orgs[0] ?? null;
      setOrg(found);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load organisation details.");
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/sign-in");
      return;
    }
    if (status === "authenticated") {
      load();
    }
  }, [status, load, router]);

  // If org is already active (not pending), skip straight to portal
  useEffect(() => {
    if (org && org.onboarding_status === "complete") {
      router.replace("/portal");
    }
  }, [org, router]);

  const handleConfirmOrg = () => setStep(1);

  const handleInviteColleague = async () => {
    if (!inviteEmail.trim() || !org) return;
    setInviting(true);
    setError(null);
    try {
      await apiFetch("/api/admin/users", {
        method: "POST",
        body: {
          email: inviteEmail.trim().toLowerCase(),
          name: inviteName.trim() || inviteEmail.trim(),
          is_platform_admin: false,
          org_ids: [org.id],
        },
      });
      setInviteSent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send invite. Please try again.");
    } finally {
      setInviting(false);
    }
  };

  const handleComplete = async () => {
    if (!org) return;
    setCompleting(true);
    setError(null);
    try {
      await apiFetch(`/api/admin/orgs/${org.id}`, {
        method: "PATCH",
        body: { onboarding_status: "complete" },
      });
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not complete onboarding. Please try again.");
    } finally {
      setCompleting(false);
    }
  };

  if (status === "loading" || loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 640, mx: "auto", py: 6, px: 2 }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        Welcome to LEO
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
        Let&rsquo;s get your organisation set up. This will only take a moment.
      </Typography>

      <Stepper activeStep={step} sx={{ mb: 4 }}>
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

      {/* Step 0 — Confirm org */}
      {step === 0 && org && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700} gutterBottom>
              Confirm your organisation details
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              These details were set up by your system administrator. If anything is incorrect,
              please contact <strong>support@healthcarecopilot.ai</strong>.
            </Typography>

            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <Typography variant="body2" color="text.secondary">Organisation name</Typography>
                <Typography variant="body2" fontWeight={600}>{org.name}</Typography>
              </Box>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <Typography variant="body2" color="text.secondary">Type</Typography>
                <Chip label={ORG_TYPE_LABELS[org.type] ?? org.type} size="small" variant="outlined" />
              </Box>
              {org.odsCode && (
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <Typography variant="body2" color="text.secondary">ODS code</Typography>
                  <Typography variant="body2" fontFamily="monospace">{org.odsCode}</Typography>
                </Box>
              )}
            </Box>

            <Box sx={{ mt: 3, display: "flex", justifyContent: "flex-end" }}>
              <Button variant="contained" onClick={handleConfirmOrg}>
                Confirm &amp; continue
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Step 1 — Invite a colleague */}
      {step === 1 && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700} gutterBottom>
              Invite a colleague (optional)
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              You can invite another admin user to help manage your organisation.
              You can always do this later from the portal.
            </Typography>

            {inviteSent ? (
              <Alert severity="success" icon={<CheckCircleOutlineIcon />}>
                Invite sent to {inviteEmail}
              </Alert>
            ) : (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <TextField
                  fullWidth label="Their work email" size="small"
                  value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
                />
                <TextField
                  fullWidth label="Their name (optional)" size="small"
                  value={inviteName} onChange={(e) => setInviteName(e.target.value)}
                />
                <Button
                  variant="outlined"
                  onClick={handleInviteColleague}
                  disabled={inviting || !inviteEmail.trim()}
                  sx={{ alignSelf: "flex-start" }}
                >
                  {inviting ? "Sending…" : "Send invite"}
                </Button>
              </Box>
            )}

            <Box sx={{ mt: 3, display: "flex", justifyContent: "space-between" }}>
              <Button onClick={() => setStep(0)} color="inherit">
                Back
              </Button>
              <Button
                variant="contained"
                onClick={handleComplete}
                disabled={completing}
              >
                {completing ? "Finishing…" : "Finish setup"}
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Step 2 — Done */}
      {step === 2 && (
        <Card variant="outlined">
          <CardContent sx={{ textAlign: "center", py: 4 }}>
            <CheckCircleOutlineIcon sx={{ fontSize: 56, color: "success.main", mb: 2 }} />
            <Typography variant="h6" fontWeight={700} gutterBottom>
              You&rsquo;re all set!
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Your organisation is now active. Head to the portal to manage your
              sub-organisations, invite users, and view your subscription.
            </Typography>
            <Button variant="contained" size="large" onClick={() => router.push("/portal")}>
              Go to the portal
            </Button>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
