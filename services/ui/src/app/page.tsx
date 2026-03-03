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
import Divider from "@mui/material/Divider";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import HealthAndSafetyOutlinedIcon from "@mui/icons-material/HealthAndSafetyOutlined";
import GroupsOutlinedIcon from "@mui/icons-material/GroupsOutlined";
import TimelineOutlinedIcon from "@mui/icons-material/TimelineOutlined";

const FEATURES = [
  {
    title: "Referral Quality Review",
    description:
      "Review and benchmark cancer referral quality against NICE Guideline NG12 to support consistent, high-quality referral practice.",
    icon: <SearchOutlinedIcon sx={{ fontSize: 32, color: "primary.main" }} />,
  },
  {
    title: "Electronic Safety Netting",
    description:
      "Standardised, electronic safety netting to ensure no patient is lost to follow-up across the referral pathway.",
    icon: <HealthAndSafetyOutlinedIcon sx={{ fontSize: 32, color: "secondary.main" }} />,
  },
  {
    title: "Screening Programme Monitoring",
    description:
      "Proactively identify eligible patients and support engagement with cancer and non-cancer screening programmes.",
    icon: <GroupsOutlinedIcon sx={{ fontSize: 32, color: "warning.main" }} />,
  },
  {
    title: "Early Diagnosis Tracking",
    description:
      "Track key milestones from presentation through referral to diagnosis and treatment, benchmarked against national targets.",
    icon: <TimelineOutlinedIcon sx={{ fontSize: 32, color: "info.main" }} />,
  },
];

export default function Home() {
  const { session, status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (session) {
      router.replace("/dashboard");
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
          LEO for Primary Care
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
          Supporting Primary Care Networks to deliver consistent, high-quality
          cancer referral practice, safety netting, and screening engagement.
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

      {/* DES alignment */}
      <Box
        sx={{
          bgcolor: "grey.50",
          py: { xs: 5, md: 6 },
          px: 3,
          textAlign: "center",
        }}
      >
        <Typography variant="h5" sx={{ mb: 2 }}>
          Aligned with Network Contract DES Requirements
        </Typography>
        <Typography
          variant="body1"
          sx={{ color: "text.secondary", maxWidth: 640, mx: "auto", lineHeight: 1.7 }}
        >
          LEO supports Primary Care Networks in meeting their DES obligations
          for improving cancer referral practice, strengthening electronic
          safety netting, promoting early diagnosis, and increasing screening
          uptake across their registered populations.
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
        <Divider sx={{ display: "none" }} />
        <Typography variant="caption" color="text.secondary">
          Powered by Mizaic
        </Typography>
      </Box>
    </Box>
  );
}
