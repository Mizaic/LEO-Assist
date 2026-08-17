/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-21936FDD")
 */
"use client";

import { useAuth } from "@/lib/authContext";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import { LeoLogo, LeoSplash } from "@leo/design-system";
import { postLoginPath } from "@/lib/postLoginPath";

export default function Home() {
  const { session, status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (session) {
      router.replace(postLoginPath(session));
    }
  }, [session, router]);

  if (status === "loading") {
    return <LeoSplash />;
  }

  if (session) return null;

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        px: 3,
        gap: 4,
      }}
    >
      <LeoLogo height={56} variant="light" spinning spinDuration={2.4} />
      <Button
        variant="contained"
        size="large"
        onClick={() => router.push("/sign-in")}
        sx={{ px: 5, py: 1.5, fontSize: "1rem" }}
      >
        Sign in
      </Button>
      <Typography variant="caption" color="text.secondary">
        For authorised Mizaic staff only.
      </Typography>
    </Box>
  );
}
