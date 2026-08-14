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
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import { LeoLogo, LeoSplash } from "@leo/design-system";
import CodeOutlinedIcon from "@mui/icons-material/CodeOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import AutoModeOutlinedIcon from "@mui/icons-material/AutoModeOutlined";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";

const FEATURES = [
  {
    title: "Clinical NLP & Coding",
    description:
      "Reads encounter records and applies SNOMED CT coding with entity extraction, negation detection, and context awareness — no manual rules.",
    icon: <CodeOutlinedIcon sx={{ fontSize: 32, color: "primary.main" }} />,
  },
  {
    title: "Pathway Reasoning",
    description:
      "LLM-assisted clinical reasoning disambiguates complex presentations, escalates uncertainty, and explains every coding decision.",
    icon: <PsychologyOutlinedIcon sx={{ fontSize: 32, color: "secondary.main" }} />,
  },
  {
    title: "Agentic Intelligence",
    description:
      "Autonomous pipeline execution across configurable clinical programmes — with human review gates built in at every critical step.",
    icon: <AutoModeOutlinedIcon sx={{ fontSize: 32, color: "warning.main" }} />,
  },
  {
    title: "Population Analytics",
    description:
      "Programme-agnostic metrics, milestone tracking, and population-level insights — configured to any pathway, not hard-coded to one.",
    icon: <BarChartOutlinedIcon sx={{ fontSize: 32, color: "info.main" }} />,
  },
];

export default function Home() {
  const { session, status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (session) {
      router.replace("/care/dashboard");
    }
  }, [session, router]);

  if (status === "loading") {
    return <LeoSplash />;
  }

  if (session) return null;

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Hero */}
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          pt: { xs: 8, md: 12 },
          pb: { xs: 6, md: 8 },
          px: 3,
          textAlign: "center",
        }}
      >
        <Box sx={{ mb: 3 }}>
          <LeoLogo height={56} variant="light" spinning spinDuration={2.4} />
        </Box>
        <Typography
          variant="h6"
          sx={{
            color: "text.secondary",
            fontWeight: 400,
            maxWidth: 640,
            lineHeight: 1.6,
            fontSize: "1.05rem",
            mb: 4,
          }}
        >
          Clinical audit intelligence by Mizaic. LEO analyses primary care
          encounter records, applies SNOMED CT coding, and reconstructs
          clinical pathways for national audit programmes — with human review
          at every step.
        </Typography>
        <Button
          variant="contained"
          size="large"
          onClick={() => router.push("/sign-in")}
          sx={{ px: 5, py: 1.5, fontSize: "1rem" }}
        >
          Sign in
        </Button>
      </Box>

      {/* Feature cards */}
      <Box sx={{ maxWidth: 960, mx: "auto", px: 3, pb: { xs: 6, md: 8 }, width: "100%" }}>
        <Grid container spacing={3}>
          {FEATURES.map((f) => (
            <Grid key={f.title} size={{ xs: 12, sm: 6 }}>
              <Card sx={{ height: "100%", "&:hover": { borderColor: "primary.light" } }}>
                <CardContent sx={{ p: 3 }}>
                  <Box sx={{ mb: 1.5 }}>{f.icon}</Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1, fontFamily: "inherit" }}>
                    {f.title}
                  </Typography>
                  <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
                    {f.description}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>

      {/* Safety and trust */}
      <Box
        sx={{
          bgcolor: "grey.50",
          py: { xs: 5, md: 6 },
          px: 3,
          textAlign: "center",
        }}
      >
        <Typography variant="h5" sx={{ mb: 2 }}>
          Built for clinical safety and regulatory trust
        </Typography>
        <Typography
          variant="body1"
          sx={{ color: "text.secondary", maxWidth: 640, mx: "auto", lineHeight: 1.7 }}
        >
          Every AI output is a proposal. LEO never acts without human review.
          Designed and built to IEC 62304 and ISO 14971 with a full design
          control and risk management framework.
        </Typography>
      </Box>

      {/* Footer */}
      <Box
        component="footer"
        sx={{
          mt: "auto",
          py: 3,
          textAlign: "center",
          borderTop: "1px solid",
          borderColor: "divider",
        }}
      >
        <Typography variant="caption" color="text.secondary">
          by Mizaic
        </Typography>
      </Box>
    </Box>
  );
}
