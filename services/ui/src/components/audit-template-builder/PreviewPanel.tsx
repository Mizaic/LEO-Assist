"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * Preview panel for the audit template editor.
 * Renders the current (unsaved) tile configuration using live data
 * from a user-selected organisation. Platform admins can switch orgs
 * here without publishing the draft first.
 */

import { useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Alert from "@mui/material/Alert";

import type { OrgInfo } from "@/lib/authContext";
import type { AuditPage, AuditTile, MetricCatalogueEntry } from "@/lib/auditTemplateApi";
import AuditTemplateRenderer from "@/components/audit-template-renderer/AuditTemplateRenderer";

interface PreviewPanelProps {
  tiles: AuditTile[];
  title: string;
  savedId?: string;
  organizations: OrgInfo[];
  previewOrgId: string;
  onOrgChange: (id: string) => void;
  catalogue?: MetricCatalogueEntry[];
  pages?: AuditPage[];
}

function OrgPicker({
  organizations,
  value,
  onChange,
}: {
  organizations: OrgInfo[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
      <Typography variant="subtitle2" fontWeight={600} sx={{ whiteSpace: "nowrap" }}>
        Preview as:
      </Typography>
      <Select
        size="small"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        displayEmpty
        sx={{ minWidth: 260 }}
        inputProps={{ "aria-label": "Select organisation for preview" }}
      >
        {organizations.length === 0 && (
          <MenuItem value="" disabled>No organisations available</MenuItem>
        )}
        {organizations.map((o) => (
          <MenuItem key={o.id} value={o.id}>
            {o.name}{o.odsCode ? ` (${o.odsCode})` : ""}
          </MenuItem>
        ))}
      </Select>
      {!value && (
        <Alert severity="info" sx={{ py: 0, fontSize: 12 }}>
          Select an organisation to preview live data.
        </Alert>
      )}
    </Box>
  );
}

export default function PreviewPanel({
  tiles,
  title,
  savedId,
  organizations,
  previewOrgId,
  onOrgChange,
  catalogue = [],
  pages = [],
}: PreviewPanelProps) {
  const previewTemplate = useMemo(
    () => ({
      template_id: savedId ?? "preview",
      title: title || "Untitled template",
      version: 1,
      status: "draft" as const,
      tiles,
      pages: pages.length > 1 ? pages : [],
      created_by: "preview",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }),
    [savedId, title, tiles, pages],
  );

  return (
    <Box sx={{ p: 2, overflowY: "auto", flex: 1 }}>
      <OrgPicker
        organizations={organizations}
        value={previewOrgId}
        onChange={onOrgChange}
      />
      <Box sx={{ mt: 3 }}>
        {previewOrgId ? (
          <AuditTemplateRenderer
            template={previewTemplate}
            orgId={previewOrgId}
            catalogue={catalogue}
          />
        ) : (
          <AuditTemplateRenderer
            template={previewTemplate}
            orgId=""
            useMockData
            catalogue={catalogue}
          />
        )}
      </Box>
    </Box>
  );
}
