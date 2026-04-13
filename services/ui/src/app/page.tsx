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
import CircularProgress from "@mui/material/CircularProgress";
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
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
        <CircularProgress aria-label="Loading" />
      </Box>
    );
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
        <Box
          component="img"
          src="/leo-icon.svg"
          alt="LEO"
          sx={{ width: 80, height: 80, mb: 3 }}
        />
        <Typography variant="h3" sx={{ fontWeight: 700, letterSpacing: "-0.02em", mb: 0.5 }}>
          LEO
        </Typography>
        <Typography variant="body1" sx={{ color: "text.secondary", mb: 3, fontSize: "1.05rem" }}>
          by Mizaic
        </Typography>
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
          Clinical intelligence for the NHS. LEO reads encounter records,
          applies SNOMED coding, reasons across pathways, and surfaces the
          patients and patterns that matter — with clinicians in control at
          every step.
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
