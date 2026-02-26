"use client";

import { useSession, signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import CircularProgress from "@mui/material/CircularProgress";

export default function Home() {
  const { data: session, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session) {
      router.replace("/dashboard");
    }
  }, [session, router]);

  if (status === "loading") {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "80vh" }}>
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
        minHeight: "80vh",
        gap: 3,
      }}
    >
      <LocalHospitalOutlinedIcon sx={{ fontSize: 64, color: "primary.main" }} />
      <Typography variant="h4">Clinical Audit Platform</Typography>
      <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 480, textAlign: "center" }}>
        Primary care clinical coding review, episode analysis, safety signal
        monitoring, and FHIR-based reporting.
      </Typography>
      <Button variant="contained" size="large" onClick={() => signIn("microsoft-entra-id")}>
        Sign in with Microsoft
      </Button>
      <Typography variant="caption" color="text.secondary">
        Azure AD single sign-on
      </Typography>
    </Box>
  );
}
