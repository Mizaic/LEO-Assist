/**
 * Atlas trace:
 *   UN: UN-3B25A20E
 *   DI: DI-10667413
 *   DO: DO-9C9CB1D8
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { color } from "@leo/design-system/tokens";

import type { TenantCompletenessDomain } from "./tenantCompletenessApi";

export default function TenantCompletenessList({
  domains,
}: {
  domains: TenantCompletenessDomain[];
}) {
  if (domains.length === 0) {
    return <Alert severity="info">No completeness domains match this search.</Alert>;
  }
  return (
    <Box data-testid="tenant-completeness-list" sx={{ display: "grid", gap: 2 }}>
      {domains.map((domain, index) => (
        <TenantCompletenessCard
          key={domain.domain_id}
          domain={domain}
          index={index}
        />
      ))}
    </Box>
  );
}

function TenantCompletenessCard({
  domain,
  index,
}: {
  domain: TenantCompletenessDomain;
  index: number;
}) {
  const groups = domain.completeness_groups ?? [];
  return (
    <Box
      data-testid={`tenant-completeness-card-${domain.domain_id}`}
      sx={{
        position: "relative",
        borderRadius: "12px",
        p: "18px",
        minHeight: 168,
        border: "1px solid",
        borderColor: "divider",
        animationDelay: `${Math.min(index, 12) * 40}ms`,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 2,
          background: color.status.success,
        }}
      />
      <Typography component="h2" variant="subtitle1" fontWeight={700}>
        {domain.domain_name}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {domain.organization_name || domain.organization_id || domain.domain_id}
      </Typography>
      {groups.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No completeness groups yet.
        </Typography>
      ) : (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
          {groups.map((group, groupIndex) => (
            <Chip
              key={`${domain.domain_id}-${group.name}-${groupIndex}`}
              label={group.name}
              size="small"
              variant="outlined"
            />
          ))}
        </Box>
      )}
    </Box>
  );
}
