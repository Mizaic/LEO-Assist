/**
 * BucketFlipWarning -- type-the-name confirmation gate.
 *
 * The Reconcile drawer renders this banner when the projected actions
 * would silently move the episode from one lifecycle bucket
 * (`active`, `in_review`, `cancer_excluded`, `confirmed_cancer`) to
 * another. The Confirm button stays disabled until the reviewer types
 * the exact target bucket name -- the same pattern used elsewhere in
 * the app for irreversible actions (see ui-accessibility.mdc).
 *
 * Pressing Escape does NOT bypass the gate; the parent renders the
 * field inline rather than as a modal so screen-reader users hear it
 * in flow with the rest of the drawer.
 *
 * Atlas trace:
 *   DO: services/ui/src/components/mission-control/BucketFlipWarning.tsx
 *   DI: DI-9DCC9F84 (Reconcile pathway)
 *   DI: DI-C424BB44 (VerificationLock primitive)
 */
"use client";

import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

interface Props {
  currentBucket: string;
  proposedBucket: string;
  typed: string;
  onTypedChange: (next: string) => void;
}

export const TYPE_TO_CONFIRM_LABEL = "Type the new pathway category to confirm";

function bucketDisplay(bucket: string): string {
  if (bucket === "in_review") return "In review";
  if (bucket === "cancer_excluded") return "Cancer excluded";
  if (bucket === "confirmed_cancer") return "Confirmed cancer";
  if (bucket === "active") return "Active";
  return bucket;
}

export function bucketMatch(typed: string, proposed: string): boolean {
  return (
    typed.trim().toLowerCase() === bucketDisplay(proposed).toLowerCase() ||
    typed.trim().toLowerCase() === proposed.toLowerCase()
  );
}

export default function BucketFlipWarning({
  currentBucket,
  proposedBucket,
  typed,
  onTypedChange,
}: Props) {
  const target = bucketDisplay(proposedBucket);
  return (
    <Alert
      severity="warning"
      role="alert"
      data-testid="bucket-flip-warning"
      sx={{ mb: 2 }}
    >
      <AlertTitle>This will change the pathway category</AlertTitle>
      <Typography variant="body2" sx={{ mb: 1 }}>
        Your changes move this pathway from{" "}
        <strong>{bucketDisplay(currentBucket)}</strong> to{" "}
        <strong>{target}</strong>. This affects which dashboards include the
        patient and cannot be undone automatically.
      </Typography>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mt: 1 }}>
        <TextField
          autoComplete="off"
          size="small"
          value={typed}
          onChange={(e) => onTypedChange(e.target.value)}
          label={TYPE_TO_CONFIRM_LABEL}
          placeholder={target}
          inputProps={{
            "aria-label": TYPE_TO_CONFIRM_LABEL,
            "data-testid": "bucket-flip-typed",
          }}
          sx={{ maxWidth: 360 }}
        />
        <Typography variant="caption" color="text.secondary">
          Type <strong>{target}</strong> to enable Confirm.
        </Typography>
      </Box>
    </Alert>
  );
}
