/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   DI: DI-340279C1
 */
"use client";

import { useState, type CSSProperties } from "react";
import { motion as fm } from "framer-motion";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import {
  springOrInstant,
  springs,
  tapScale,
  useMotion,
} from "@leo/design-system";
import { color, elevation, typography } from "@leo/design-system/tokens";

import type { DomainSummary, DomainUseCase } from "@/lib/analyticsApi";
import {
  CardFooter,
  CoverageBar,
  HoverActions,
  SourceChip,
  ToneChip,
} from "./DomainCardParts";

const USE_CASE_LABEL: Record<DomainUseCase, string> = {
  extraction: "Extraction",
  completeness: "Minimum dataset",
  analytics: "Analytics",
  episode_detection: "Episode detection",
};

export interface DomainCardProps {
  domain: DomainSummary;
  index: number;
  canEdit: boolean;
  onNavigate: (id: string) => void;
  onEdit: (domain: DomainSummary) => void;
  onDelete: (domain: DomainSummary) => void;
  onTestInLab?: (domain: DomainSummary) => void;
}

export default function DomainCard({
  domain,
  index,
  canEdit,
  onNavigate,
  onEdit,
  onDelete,
  onTestInLab,
}: DomainCardProps) {
  const { reducedMotion } = useMotion();
  const [hovered, setHovered] = useState(false);
  const accent = sourceAccent(domain.source);
  const useCases: DomainUseCase[] =
    domain.use_cases ?? (domain.minimum_dataset_domain ? ["completeness"] : []);
  const enter = springOrInstant(reducedMotion, springs.ui);

  return (
    <fm.div
      data-testid={`domain-card-${domain.id}`}
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...enter, delay: reducedMotion ? 0 : Math.min(index, 12) * 0.04 }}
      whileTap={tapScale(reducedMotion)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onNavigate(domain.id)}
      style={cardStyle()}
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
      {canEdit ? (
        <HoverActions domain={domain} visible={hovered} onEdit={onEdit} onDelete={onDelete} />
      ) : null}
      <CardHeader domain={domain} accent={accent} useCases={useCases} />
      <CardDescription text={domain.description} />
      <div style={{ flex: 1 }} />
      <CoverageBar coveragePct={domain.coverage_pct} />
      <CardFooter domain={domain} hovered={hovered} onTestInLab={onTestInLab} />
    </fm.div>
  );
}

function CardHeader({
  domain,
  accent,
  useCases,
}: {
  domain: DomainSummary;
  accent: string;
  useCases: DomainUseCase[];
}) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        <FolderOpenOutlinedIcon sx={{ fontSize: 22, color: accent, flexShrink: 0 }} />
        <span
          style={{
            fontFamily: typography.fontFamily.heading,
            fontWeight: 700,
            fontSize: 16,
            letterSpacing: typography.letterSpacing.display,
            color: color.text.primary,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {domain.name}
        </span>
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", justifyContent: "flex-end" }}>
        {useCases.map((uc) => (
          <ToneChip key={uc} label={USE_CASE_LABEL[uc] ?? uc} />
        ))}
        <SourceChip source={domain.source} />
      </div>
    </div>
  );
}

function CardDescription({ text }: { text?: string | null }) {
  return (
    <p
      style={{
        margin: 0,
        fontSize: 13,
        lineHeight: 1.45,
        color: text ? color.text.secondary : color.text.caption,
        fontStyle: text ? "normal" : "italic",
        display: "-webkit-box",
        WebkitLineClamp: 2,
        WebkitBoxOrient: "vertical",
        overflow: "hidden",
      }}
    >
      {text || "No description yet."}
    </p>
  );
}

function sourceAccent(source?: string): string {
  if (source === "nice") return color.brand.primary;
  if (source === "platform") return color.text.secondary;
  return color.status.success;
}

function cardStyle(): CSSProperties {
  return {
    background: color.surface.raised,
    border: 0,
    borderRadius: 12,
    padding: 18,
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    position: "relative",
    minHeight: 168,
    boxShadow: elevation.card,
    fontFamily: typography.fontFamily.body,
  };
}
