"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";

interface UnauthorizedScreenProps {
  onSignIn: () => void;
}

export default function UnauthorizedScreen({ onSignIn }: UnauthorizedScreenProps) {
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
        {/* Icon */}
        <Box
          sx={{
            width: 72,
            height: 72,
            borderRadius: "50%",
            bgcolor: "rgba(31, 58, 138, 0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <LockOutlinedIcon sx={{ fontSize: 36, color: "primary.main" }} />
        </Box>

        {/* Main message — plain English, reading age ~11 */}
        <Typography
          variant="h5"
          sx={{ fontWeight: 700, textAlign: "center", color: "text.primary" }}
        >
          You need to sign in first
        </Typography>

        <Typography
          variant="body1"
          sx={{ color: "text.secondary", textAlign: "center", lineHeight: 1.65 }}
        >
          This page is for authorised Mizaic staff only. Please sign in with
          your Microsoft account to continue.
        </Typography>

        {/* Primary action */}
        <Button
          variant="contained"
          size="large"
          onClick={onSignIn}
          sx={{ mt: 1, px: 5, py: 1.3, fontWeight: 700, fontSize: "1rem", width: "100%" }}
        >
          Sign in with Microsoft
        </Button>

        {/* "Need access?" help text */}
        <Typography variant="body2" sx={{ color: "text.secondary", textAlign: "center" }}>
          Not sure if you have an account?{" "}
          <strong>Ask your system administrator</strong> to set one up for
          you.
        </Typography>

        <Divider sx={{ width: "100%", mt: 1 }} />

        {/* Legal notice — smaller, clearly secondary */}
        <Typography
          variant="caption"
          component="p"
          sx={{
            color: "text.disabled",
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
