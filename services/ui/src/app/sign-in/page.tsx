"use client";

import { useAuth } from "@/lib/authContext";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Link from "@mui/material/Link";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";

const ERROR_MESSAGES: Record<string, string> = {
  token_v1_not_allowed:
    "Azure AD is issuing v1.0 tokens. Set accessTokenAcceptedVersion: 2 in the app manifest.",
  token_exchange_failed: "Token exchange failed. Please try again.",
  missing_code: "Sign-in was cancelled or incomplete.",
};

function SignInContent() {
  const { session, status, signIn } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const error = searchParams.get("error");
  const errorMessage = error ? ERROR_MESSAGES[error] ?? error : null;

  useEffect(() => {
    if (session) {
      router.replace("/dashboard");
    }
  }, [session, router]);

  if (status === "loading") {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (session) return null;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        gap: 3,
        px: 3,
      }}
    >
      <Box
        component="img"
        src="/leo-icon.svg"
        alt="LEO"
        sx={{ width: 64, height: 64 }}
      />
      <Typography variant="h5" sx={{ fontWeight: 700 }}>
        Sign in to LEO
      </Typography>
      {errorMessage && (
        <Alert severity="error" sx={{ maxWidth: 400 }}>
          {errorMessage}
        </Alert>
      )}
      <Button
        variant="contained"
        size="large"
        onClick={() => signIn()}
        sx={{ px: 4, py: 1.2 }}
      >
        Sign in with Microsoft
      </Button>
      <Typography variant="caption" color="text.secondary">
        Azure AD single sign-on
      </Typography>
      <Link
        href="/"
        underline="hover"
        sx={{ fontSize: "0.85rem", color: "text.secondary", mt: 1 }}
      >
        Back to home
      </Link>
    </Box>
  );
}

export default function SignInPage() {
  return (
    <Suspense
      fallback={
        <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
          <CircularProgress />
        </Box>
      }
    >
      <SignInContent />
    </Suspense>
  );
}
