/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   DI: DI-340279C1
 */
"use client";

import { useState } from "react";
import { motion as fm } from "framer-motion";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";

import type { DomainSummary, DomainUseCase } from "@/lib/analyticsApi";

const USE_CASE_STYLES: Record<DomainUseCase, { label: string; bg: string; color: string; border: string }> = {
  extraction: {
    label: "Extraction",
    bg: "#FFF7ED",
    color: "#9A3412",
    border: "#FED7AA",
  },
  completeness: {
    label: "Minimum dataset",
    bg: "#EEF2FF",
    color: "#3730A3",
    border: "#C7D2FE",
  },
  analytics: {
    label: "Analytics",
    bg: "#F0FDF4",
    color: "#166534",
    border: "#BBF7D0",
  },
  episode_detection: {
    label: "Episode detection",
    bg: "#F0F9FF",
    color: "#0369A1",
    border: "#BAE6FD",
  },
};

function UseCaseChip({ value }: { value: DomainUseCase }) {
  const s = USE_CASE_STYLES[value] ?? { label: value, bg: "#F1F5F9", color: "#475569", border: "#E2E8F0" };
  return (
    <Chip
      label={s.label}
      size="small"
      sx={{ height: 22, fontSize: "0.7rem", bgcolor: s.bg, color: s.color, border: `1px solid ${s.border}`, flexShrink: 0 }}
    />
  );
}

export interface DomainCardProps {
  domain: DomainSummary;
  index: number;
  canEdit: boolean;
  onNavigate: (id: string) => void;
  onEdit: (domain: DomainSummary) => void;
  onDelete: (domain: DomainSummary) => void;
}

export default function DomainCard({
  domain,
  index,
  canEdit,
  onNavigate,
  onEdit,
  onDelete,
}: DomainCardProps) {
  const [hovered, setHovered] = useState(false);
  const isNice = domain.source === "nice";
  const isPlatform = domain.source === "platform";
  const accent = isNice ? "#2563EB" : isPlatform ? "#64748B" : "#16A34A";
  const useCases: DomainUseCase[] = domain.use_cases ?? (domain.minimum_dataset_domain ? ["completeness"] : []);

  return (
    <fm.div
      data-testid={`domain-card-${domain.id}`}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: "easeOut", delay: Math.min(index, 12) * 0.04 }}
      whileHover={{ y: -2, boxShadow: "0 8px 18px rgba(15, 23, 42, 0.08)" }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onNavigate(domain.id)}
      style={{
        background: "#FFFFFF",
        border: "1px solid #E2E8F0",
        borderRadius: 12,
        padding: 18,
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        position: "relative",
        minHeight: 168,
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
          background: accent,
        }}
      />

      {canEdit && (
        <Box
          sx={{
            position: "absolute",
            top: 8,
            right: 8,
            display: hovered ? "flex" : "none",
            gap: 0.5,
            bgcolor: "rgba(255,255,255,0.95)",
            borderRadius: 1,
            boxShadow: "0 1px 4px rgba(0,0,0,0.1)",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <Tooltip title="Rename area">
            <IconButton
              size="small"
              aria-label={`Edit ${domain.name}`}
              onClick={() => onEdit(domain)}
            >
              <EditOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          {!isNice && (
            <Tooltip title="Delete area">
              <IconButton
                size="small"
                color="error"
                aria-label={`Delete ${domain.name}`}
                onClick={() => onDelete(domain)}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>
      )}

      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
          <FolderOpenOutlinedIcon sx={{ fontSize: 22, color: accent, flexShrink: 0 }} />
          <Typography sx={{ fontWeight: 600, fontSize: "1rem", lineHeight: 1.25, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {domain.name}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {useCases.map((uc) => <UseCaseChip key={uc} value={uc} />)}
          {isNice ? (
            <Chip icon={<MenuBookOutlinedIcon sx={{ fontSize: 12 }} />} label="NICE" size="small" sx={{ height: 22, fontSize: "0.7rem", bgcolor: "#DBEAFE", color: "#1E40AF", border: "1px solid #BFDBFE", flexShrink: 0 }} />
          ) : isPlatform ? (
            <Chip label="Built in" size="small" sx={{ height: 22, fontSize: "0.7rem", bgcolor: "#F1F5F9", color: "#475569", border: "1px solid #E2E8F0", flexShrink: 0 }} />
          ) : (
            <Chip label="Your org" size="small" sx={{ height: 22, fontSize: "0.7rem", bgcolor: "#ECFDF5", color: "#047857", border: "1px solid #A7F3D0", flexShrink: 0 }} />
          )}
        </Box>
      </Box>

      {domain.description ? (
        <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.82rem", lineHeight: 1.45, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {domain.description}
        </Typography>
      ) : (
        <Typography variant="body2" color="text.disabled" sx={{ fontSize: "0.82rem", fontStyle: "italic" }}>
          No description yet.
        </Typography>
      )}

      <Box sx={{ flex: 1 }} />

      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mt: 0.5 }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem", fontWeight: 500 }}>
          {domain.subdomain_count} subdomain{domain.subdomain_count !== 1 ? "s" : ""}
        </Typography>
        <ChevronRightIcon sx={{ fontSize: 18, color: "#94A3B8" }} />
      </Box>
    </fm.div>
  );
}
