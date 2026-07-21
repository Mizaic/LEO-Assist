/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

import * as React from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";

import { NCDA_BREACH_TOOLTIPS } from "@/lib/ncdaLabels";
import {
  NATIONAL_FDS_28,
  NATIONAL_REFERRAL_62,
  NATIONAL_TREATMENT_31,
  PathwayBands,
} from "@/lib/ncdaPathway";

interface SliderConfig {
  field: keyof Omit<PathwayBands, "site_key">;
  label: string;
  helper: string;
  nationalBreach: number;
}

const SLIDERS: SliderConfig[] = [
  {
    field: "ftr_to_seen_typical_max_days",
    label: "Urgent referral to first hospital visit (days)",
    helper: "Time we expect from urgent referral to the first hospital visit.",
    nationalBreach: NATIONAL_FDS_28,
  },
  {
    field: "seen_to_dx_typical_max_days",
    label: "First hospital visit to outcome (days)",
    helper: "Time from the first hospital visit to cancer found or ruled out.",
    nationalBreach: NATIONAL_FDS_28,
  },
  {
    field: "ftr_to_dx_typical_max_days",
    label: "Urgent referral to outcome (days)",
    helper: NCDA_BREACH_TOOLTIPS.fds_28,
    nationalBreach: NATIONAL_FDS_28,
  },
  {
    field: "dx_to_treatment_typical_max_days",
    label: "Outcome to treatment (days)",
    helper: NCDA_BREACH_TOOLTIPS.treatment_31,
    nationalBreach: NATIONAL_TREATMENT_31,
  },
  {
    field: "ftr_to_treatment_typical_max_days",
    label: "Urgent referral to treatment (days)",
    helper: NCDA_BREACH_TOOLTIPS.referral_62,
    nationalBreach: NATIONAL_REFERRAL_62,
  },
];

async function fetchConfig(): Promise<PathwayBands[]> {
  const res = await fetch("/api/ncda/pathway-config", { cache: "no-store" });
  if (!res.ok) return [];
  const body = await res.json();
  return Array.isArray(body.items) ? body.items : [];
}

async function saveSite(site: PathwayBands) {
  await fetch(`/api/ncda/pathway-config/${site.site_key}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      ftr_to_seen_typical_max_days: site.ftr_to_seen_typical_max_days,
      seen_to_dx_typical_max_days: site.seen_to_dx_typical_max_days,
      dx_to_treatment_typical_max_days: site.dx_to_treatment_typical_max_days,
      ftr_to_dx_typical_max_days: site.ftr_to_dx_typical_max_days,
      ftr_to_treatment_typical_max_days: site.ftr_to_treatment_typical_max_days,
    }),
  });
}

export default function NcdaPathwayConfigPage() {
  const [bands, setBands] = React.useState<PathwayBands[]>([]);

  React.useEffect(() => {
    fetchConfig().then(setBands);
  }, []);

  const updateField = (
    siteKey: string,
    field: keyof Omit<PathwayBands, "site_key">,
    value: number,
  ) => {
    setBands((prev) =>
      prev.map((b) => (b.site_key === siteKey ? { ...b, [field]: value } : b)),
    );
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Pathway typical times by site
      </Typography>
      <Typography variant="body1" color="text.secondary" gutterBottom>
        Set how long each step usually takes for each cancer site. The
        national rules (28, 31, 62 days) are fixed and shown for context.
      </Typography>
      <Grid container spacing={2}>
        {bands.map((site) => (
          <Grid size={{ xs: 12, md: 6 }} key={site.site_key}>
            <Card data-testid={`ncda-config-card-${site.site_key}`}>
              <CardContent>
                <Stack
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  mb={2}
                >
                  <Typography variant="h6">{site.site_key}</Typography>
                  <Button
                    variant="contained"
                    size="small"
                    onClick={() => saveSite(site)}
                  >
                    Save
                  </Button>
                </Stack>
                <Stack spacing={2}>
                  {SLIDERS.map((cfg) => (
                    <Box key={cfg.field}>
                      <Typography variant="body2" gutterBottom>
                        {cfg.label}: {site[cfg.field]} days (national rule:{" "}
                        {cfg.nationalBreach})
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {cfg.helper}
                      </Typography>
                      <Slider
                        value={Number(site[cfg.field] ?? 0)}
                        min={0}
                        max={cfg.nationalBreach}
                        step={1}
                        onChange={(_, v) =>
                          updateField(site.site_key, cfg.field, Number(v))
                        }
                        valueLabelDisplay="auto"
                        data-testid={`ncda-config-slider-${site.site_key}-${cfg.field}`}
                      />
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
