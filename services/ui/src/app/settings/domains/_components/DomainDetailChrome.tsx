/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-21936FDD")
 */
"use client";

import type { Dispatch, SetStateAction } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Link from "@mui/material/Link";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import Tooltip from "@mui/material/Tooltip";
import Chip from "@mui/material/Chip";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import type { DomainDetail } from "@/lib/analyticsApi";

export interface DomainDetailChromeProps {
  router: { push: (path: string) => void };
  domainId: string;
  domain: DomainDetail | null;
  setDomain: Dispatch<SetStateAction<DomainDetail | null>>;
  canEditDomains: boolean;
  onEpisodeDetectorChange: (next: boolean) => Promise<void>;
  onEpisodeDetectorError: () => void;
}

export default function DomainDetailChrome({
  router,
  domainId,
  domain,
  setDomain,
  canEditDomains,
  onEpisodeDetectorChange,
  onEpisodeDetectorError,
}: DomainDetailChromeProps) {
  return (
    <>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link
          underline="hover"
          color="inherit"
          sx={{ cursor: "pointer" }}
          onClick={() => router.push("/settings")}
        >
          Settings
        </Link>
        <Link
          underline="hover"
          color="inherit"
          sx={{ cursor: "pointer" }}
          onClick={() => router.push("/settings/domains")}
        >
          Domains
        </Link>
        <Typography color="text.primary">
          {domain?.name ?? domainId}
        </Typography>
      </Breadcrumbs>

      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <IconButton
          aria-label="Back to domains"
          onClick={() => router.push("/settings/domains")}
          size="small"
        >
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
          {domain?.name ?? "Loading\u2026"}
        </Typography>
        {domain?.minimum_dataset_domain ? (
          <Tooltip
            title={`${domain.minimum_dataset_subdomain_count ?? 0} subdomain${
              (domain.minimum_dataset_subdomain_count ?? 0) === 1 ? "" : "s"
            } have completeness criteria.`}
          >
            <Chip
              label="Minimum dataset"
              size="small"
              sx={{
                bgcolor: "#EEF2FF",
                color: "#3730A3",
                border: "1px solid #C7D2FE",
              }}
            />
          </Tooltip>
        ) : null}
      </Box>
      {domain?.description && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {domain.description}
        </Typography>
      )}

      {domain && (
        <Box sx={{ mb: 3 }}>
          <Tooltip
            title={
              canEditDomains
                ? "When on, this domain's subdomains are used by the episode detector to identify cancer pathway milestones."
                : "Only a platform admin can change this setting."
            }
          >
            <FormControlLabel
              control={
                <Switch
                  checked={domain.episode_detector ?? false}
                  onChange={async (e) => {
                    if (!canEditDomains) return;
                    const val = e.target.checked;
                    setDomain((d) => (d ? { ...d, episode_detector: val } : d));
                    try {
                      await onEpisodeDetectorChange(val);
                    } catch {
                      setDomain((d) =>
                        d ? { ...d, episode_detector: !val } : d,
                      );
                      onEpisodeDetectorError();
                    }
                  }}
                  disabled={!canEditDomains}
                  size="small"
                />
              }
              label={
                <Typography variant="body2" color="text.secondary">
                  Episode detector config
                </Typography>
              }
            />
          </Tooltip>
        </Box>
      )}

      {domain && !canEditDomains && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You can view subdomains and export code lists. Only a platform admin
          can create subdomains or change codes.
        </Alert>
      )}
    </>
  );
}
