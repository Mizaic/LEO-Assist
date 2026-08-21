/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import { LeoLogo } from "@leo/design-system";

type UnauthorizedVariant = "unauthenticated" | "no-access";

interface UnauthorizedScreenProps {
  onSignIn?: () => void;
  onSignOut?: () => void;
  variant?: UnauthorizedVariant;
}

const COPY: Record<
  UnauthorizedVariant,
  { title: string; body: string; help: string; action: string }
> = {
  unauthenticated: {
    title: "You need to sign in first",
    body:
      "This page is for authorised Mizaic staff only. Please sign in with " +
      "your Microsoft account to continue.",
    help:
      "Not sure if you have an account? Ask your system administrator to " +
      "set one up for you.",
    action: "Sign in with Microsoft",
  },
  "no-access": {
    title: "You do not have access",
    body:
      "Your Microsoft sign-in worked, but your account has not been given " +
      "access to LEO. Ask your system administrator to assign a LEO role.",
    help:
      "If you think this is a mistake, contact your system administrator. " +
      "Do not try to open clinical pages again until access is granted.",
    action: "Sign out",
  },
};

export default function UnauthorizedScreen({
  onSignIn,
  onSignOut,
  variant = "unauthenticated",
}: UnauthorizedScreenProps) {
  const copy = COPY[variant];
  const onAction =
    variant === "no-access" ? onSignOut : onSignIn;

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        bgcolor: "background.default",
        px: 3,
        py: 6,
      }}
    >
      <Box
        sx={{
          maxWidth: 480,
          width: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 2,
        }}
      >
        <LeoLogo variant="light" height={48} />
        <Box
          sx={{
            width: 72,
            height: 72,
            borderRadius: "50%",
            bgcolor: "rgba(13, 70, 214, 0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <LockOutlinedIcon sx={{ fontSize: 36, color: "primary.main" }} />
        </Box>

        <Typography
          variant="h5"
          component="h1"
          sx={{ fontWeight: 700, textAlign: "center", color: "text.primary" }}
        >
          {copy.title}
        </Typography>

        <Typography
          variant="body1"
          sx={{ color: "text.secondary", textAlign: "center", lineHeight: 1.65 }}
        >
          {copy.body}
        </Typography>

        {onAction ? (
          <Button
            variant="contained"
            size="large"
            onClick={onAction}
            sx={{
              mt: 1,
              px: 5,
              py: 1.3,
              fontWeight: 700,
              fontSize: "1rem",
              width: "100%",
            }}
          >
            {copy.action}
          </Button>
        ) : null}

        <Typography
          variant="body2"
          sx={{ color: "text.secondary", textAlign: "center" }}
        >
          {copy.help}
        </Typography>

        <Divider sx={{ width: "100%", mt: 1 }} />

        <Typography
          variant="caption"
          component="p"
          sx={{
            color: "text.secondary",
            textAlign: "center",
            lineHeight: 1.7,
            fontSize: "0.72rem",
          }}
        >
          This system holds sensitive patient data. All access attempts are
          logged. Unauthorised access is a criminal offence under the Computer
          Misuse Act 1990 and may be reported to the Information
          Commissioner&apos;s Office.
        </Typography>
      </Box>
    </Box>
  );
}
