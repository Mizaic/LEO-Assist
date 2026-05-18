/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-21936FDD")
 */
"use client";

/**
 * /settings/preferences -- per-practitioner UI preferences
 * (Wave E Phase 1 / DI-LEO-AI-169 / VT-LEO-AI-168).
 *
 * Currently surfaces the density toggle. Patient reachable routes still
 * force `spacious` regardless of the saved preference; the page makes that
 * explicit so users understand why their selection is overridden in some
 * places.
 */

import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";

import AreaIntro from "@/components/AreaIntro";
import { useDemoMode } from "@/context/DemoModeContext";
import { DENSITY_TIERS, useDensity } from "@/context/DensityContext";
import type { DensityTier } from "@/theme/tokens";

const DENSITY_COPY: Record<
  DensityTier,
  { label: string; helper: string }
> = {
  compact: {
    label: "Compact",
    helper:
      "Smaller rows for power users on big screens. Best for review queues and tables.",
  },
  comfortable: {
    label: "Comfortable",
    helper: "The default. Touch targets stay above 40px on every screen.",
  },
  spacious: {
    label: "Spacious",
    helper:
      "Larger spacing for clinical demos and shared screens. Always used on patient-facing pages.",
  },
};

export default function SettingsPreferencesPage() {
  const { density, setDensity, isRouteForced, isPersisting } = useDensity();
  const { isDemoMode, setDemoMode } = useDemoMode();

  const handleChange = (
    _event: React.MouseEvent<HTMLElement>,
    next: DensityTier | null,
  ) => {
    if (!next) return;
    setDensity(next);
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      <AreaIntro area="settings" />
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
        Preferences
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Personal settings for how LEO appears while you work. Some settings
        follow your account; device-only settings are saved in this browser.
      </Typography>

      <Stack spacing={2}>
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  Display density
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Choose how tightly LEO packs information on the page. The
                  default keeps every button easy to tap.
                </Typography>
              </Box>

              <ToggleButtonGroup
                value={density}
                exclusive
                onChange={handleChange}
                aria-label="display density"
                disabled={isPersisting}
                sx={{ alignSelf: "flex-start" }}
              >
                {DENSITY_TIERS.map((tier) => (
                  <ToggleButton
                    key={tier}
                    value={tier}
                    aria-label={DENSITY_COPY[tier].label}
                    sx={{ textTransform: "none", px: 2 }}
                  >
                    {DENSITY_COPY[tier].label}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>

              <Typography variant="body2" color="text.secondary">
                {DENSITY_COPY[density].helper}
              </Typography>

              {isRouteForced ? (
                <Typography
                  variant="caption"
                  color="warning.main"
                  sx={{ fontStyle: "italic" }}
                >
                  You are on a patient-facing page, so spacious density is
                  being used right now. Your saved preference still applies
                  everywhere else.
                </Typography>
              ) : null}
            </Stack>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <Stack spacing={1.5}>
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  Demo mode
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Hide patient identifiers, organisation names, and encounter
                  text on shared screens. This display setting is saved only in
                  this browser.
                </Typography>
              </Box>

              <FormControlLabel
                control={
                  <Switch
                    checked={isDemoMode}
                    onChange={(event) => setDemoMode(event.target.checked)}
                    inputProps={{ "aria-label": "Enable demo mode" }}
                  />
                }
                label={isDemoMode ? "Demo mode on" : "Demo mode off"}
              />

              <Typography variant="caption" color="text.secondary">
                Demo mode changes what is rendered on screen. It does not change
                API responses, stored patient records, or account preferences.
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
