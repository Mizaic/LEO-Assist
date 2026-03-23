"use client";

/**
 * Subscription Panel
 *
 * Shown to org admins on the Subscription tab of the /portal page.
 * Displays tier, credit balance, and usage for their organisation's subscription.
 */

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";
import CreditCardIcon from "@mui/icons-material/CreditCard";
import { listOrgs, type Org } from "@/lib/api/admin";

interface Props {
  orgId?: string;
}

const TIER_LABELS: Record<string, string> = {
  cancer_alliance: "Cancer Alliance",
  icb: "ICB",
  pcn: "PCN",
  gp: "GP Practice",
};

export default function SubscriptionPanel({ orgId }: Props) {
  const [org, setOrg] = useState<Org | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!orgId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const orgs = await listOrgs();
      const found = orgs.find((o) => o.id === orgId) ?? null;
      setOrg(found);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load subscription data.");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!org) {
    return (
      <Alert severity="info">
        No organisation found. Please contact Mizaic support if you believe this is an error.
      </Alert>
    );
  }

  const sub = org.subscription;

  if (!sub) {
    return (
      <Box sx={{ py: 4, textAlign: "center", color: "text.secondary" }}>
        <CreditCardIcon sx={{ fontSize: 48, mb: 1, opacity: 0.3 }} />
        <Typography>No active subscription found for this organisation.</Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          Contact <strong>support@healthcarecopilot.ai</strong> to set up a subscription.
        </Typography>
      </Box>
    );
  }

  const creditsUsed = sub.credits_consumed ?? 0;
  const creditsPurchased = sub.credits_purchased ?? 0;
  const creditsPct = creditsPurchased > 0 ? Math.min(100, (creditsUsed / creditsPurchased) * 100) : 0;
  const creditsRemaining = creditsPurchased - creditsUsed;

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>
        Subscription for {org.name}
      </Typography>

      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 3 }}>
        {/* Tier card */}
        <Card variant="outlined" sx={{ flex: "1 1 220px" }}>
          <CardContent>
            <Typography variant="caption" color="text.secondary" gutterBottom>
              Subscription tier
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
              <Chip
                label={TIER_LABELS[sub.tier] ?? sub.tier}
                color="primary"
                size="small"
              />
            </Box>
          </CardContent>
        </Card>

        {/* Credits card */}
        <Card variant="outlined" sx={{ flex: "1 1 280px" }}>
          <CardContent>
            <Typography variant="caption" color="text.secondary" gutterBottom>
              Credit balance
            </Typography>
            <Typography variant="h5" sx={{ fontWeight: 700, mt: 0.5 }}>
              {creditsRemaining.toLocaleString()}
              <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                / {creditsPurchased.toLocaleString()} remaining
              </Typography>
            </Typography>
            <LinearProgress
              variant="determinate"
              value={creditsPct}
              color={creditsPct > 80 ? "error" : creditsPct > 60 ? "warning" : "primary"}
              sx={{ mt: 1, borderRadius: 1, height: 6 }}
            />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              {creditsUsed.toLocaleString()} used · {creditsPct.toFixed(0)}% consumed
            </Typography>
          </CardContent>
        </Card>

        {/* Expiry card */}
        {sub.expires_at && (
          <Card variant="outlined" sx={{ flex: "1 1 200px" }}>
            <CardContent>
              <Typography variant="caption" color="text.secondary" gutterBottom>
                Expires
              </Typography>
              <Typography variant="body1" sx={{ fontWeight: 600, mt: 0.5 }}>
                {new Date(sub.expires_at).toLocaleDateString("en-GB", {
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
              </Typography>
            </CardContent>
          </Card>
        )}
      </Box>

      {creditsPct > 80 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          You have used more than 80% of your credits. Contact{" "}
          <strong>support@healthcarecopilot.ai</strong> to top up.
        </Alert>
      )}

      <Typography variant="body2" color="text.secondary">
        Credits are consumed each time a patient record is processed through the LEO pipeline.
        Contact <strong>support@healthcarecopilot.ai</strong> to purchase additional credits or
        upgrade your subscription tier.
      </Typography>
    </Box>
  );
}
