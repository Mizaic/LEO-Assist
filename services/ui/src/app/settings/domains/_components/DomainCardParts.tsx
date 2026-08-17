/**
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   DI: DI-340279C1
 */
"use client";

import type { CSSProperties, ReactNode } from "react";
import Tooltip from "@mui/material/Tooltip";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import { color, elevation } from "@leo/design-system/tokens";

import type { DomainSummary } from "@/lib/analyticsApi";

export function CoverageBar({ coveragePct }: { coveragePct?: number }) {
  if (coveragePct === undefined) return null;
  const tone = coverageTone(coveragePct);
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
        <span style={{ fontSize: 11, color: color.text.secondary }}>Coding coverage</span>
        <span style={{ fontSize: 11, fontWeight: 600, color: tone }}>{Math.round(coveragePct)}%</span>
      </div>
      <div
        style={{ height: 4, borderRadius: 2, background: color.surface.alt, overflow: "hidden" }}
        aria-label={`${Math.round(coveragePct)}% coding coverage`}
      >
        <div style={{ width: Math.min(coveragePct, 100) + "%", height: "100%", background: tone }} />
      </div>
    </div>
  );
}

export function CardFooter({
  domain,
  hovered,
  onTestInLab,
}: {
  domain: DomainSummary;
  hovered: boolean;
  onTestInLab?: (domain: DomainSummary) => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <span style={{ fontSize: 12, fontWeight: 500, color: color.text.secondary }}>
        {domain.subdomain_count} subdomain{domain.subdomain_count !== 1 ? "s" : ""}
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        {onTestInLab ? (
          <Tooltip title="Test this area in Validation Lab">
            <button
              type="button"
              aria-label={`Test ${domain.name} in validation lab`}
              data-testid="domain-card-test-in-lab"
              onClick={(e) => {
                e.stopPropagation();
                onTestInLab(domain);
              }}
              style={iconBtn(hovered)}
            >
              <ScienceOutlinedIcon fontSize="small" sx={{ color: color.brand.primary }} />
            </button>
          </Tooltip>
        ) : null}
        <ChevronRightIcon sx={{ fontSize: 18, color: color.text.caption }} />
      </div>
    </div>
  );
}

export function HoverActions({
  domain,
  visible,
  onEdit,
  onDelete,
}: {
  domain: DomainSummary;
  visible: boolean;
  onEdit: (domain: DomainSummary) => void;
  onDelete: (domain: DomainSummary) => void;
}) {
  return (
    <div
      style={{
        position: "absolute",
        top: 8,
        right: 8,
        display: visible ? "flex" : "none",
        gap: 4,
        background: color.surface.raised,
        borderRadius: 8,
        boxShadow: elevation.card,
        zIndex: 1,
      }}
      onClick={(e) => e.stopPropagation()}
    >
      <IconTip title="Rename area" label={`Edit ${domain.name}`} onClick={() => onEdit(domain)}>
        <EditOutlinedIcon fontSize="small" />
      </IconTip>
      {domain.source !== "nice" ? (
        <IconTip title="Delete area" label={`Delete ${domain.name}`} onClick={() => onDelete(domain)}>
          <DeleteOutlineIcon fontSize="small" sx={{ color: color.status.danger }} />
        </IconTip>
      ) : null}
    </div>
  );
}

export function SourceChip({ source }: { source?: string }) {
  if (source === "nice") {
    return (
      <ToneChip
        label="NICE"
        icon={<MenuBookOutlinedIcon sx={{ fontSize: 12 }} />}
        bg={color.brand.primary + "1a"}
        fg={color.brand.primaryHover}
      />
    );
  }
  if (source === "platform") {
    return <ToneChip label="Built in" bg={color.surface.alt} fg={color.text.secondary} />;
  }
  return <ToneChip label="Your org" bg={color.status.success + "1f"} fg={color.status.success} />;
}

export function ToneChip({
  label,
  icon,
  bg = color.surface.alt,
  fg = color.text.secondary,
}: {
  label: string;
  icon?: ReactNode;
  bg?: string;
  fg?: string;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        height: 22,
        fontSize: 11,
        fontWeight: 600,
        background: bg,
        color: fg,
        borderRadius: 999,
        padding: "0 8px",
        flexShrink: 0,
      }}
    >
      {icon}
      {label}
    </span>
  );
}

function IconTip({
  title,
  label,
  onClick,
  children,
}: {
  title: string;
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Tooltip title={title}>
      <button type="button" aria-label={label} onClick={onClick} style={iconBtn(true)}>
        {children}
      </button>
    </Tooltip>
  );
}

function coverageTone(pct: number): string {
  if (pct >= 80) return color.status.success;
  if (pct >= 50) return color.status.warning;
  return color.status.danger;
}

function iconBtn(visible: boolean): CSSProperties {
  return {
    border: 0,
    background: "transparent",
    cursor: "pointer",
    padding: 4,
    display: "inline-flex",
    opacity: visible ? 1 : 0,
  };
}
