"use client";

/**
 * Renders a content block tile -- non-data elements like headings, text,
 * dividers, callouts, images, and links.
 *
 * In builderMode + isSelected, text fields are inline-editable.
 * In renderer mode, the block is read-only.
 *
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 */

import { useCallback, useRef } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
import type { AuditTile } from "@/lib/auditTemplateApi";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ContentBlockTileProps {
  tile: AuditTile;
  /** In the builder: removes outer card chrome. Tiles provide their own chrome. */
  builderMode?: boolean;
  /** When true in builderMode: text fields become inline-editable. */
  isSelected?: boolean;
  onParamChange?: (updated: AuditTile) => void;
}

type P = Record<string, unknown>;

function str(params: P, key: string, fallback = ""): string {
  return typeof params[key] === "string" ? (params[key] as string) : fallback;
}

// ---------------------------------------------------------------------------
// Inline editable text -- contenteditable div
// ---------------------------------------------------------------------------

interface EditableTextProps {
  value: string;
  editable: boolean;
  multiline?: boolean;
  onCommit: (text: string) => void;
  style?: React.CSSProperties;
  className?: string;
}

function EditableText({ value, editable, multiline = false, onCommit, style }: EditableTextProps) {
  const ref = useRef<HTMLDivElement>(null);

  const handleBlur = useCallback(() => {
    if (ref.current) onCommit(ref.current.innerText ?? "");
  }, [onCommit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!multiline && e.key === "Enter") {
        e.preventDefault();
        ref.current?.blur();
      }
    },
    [multiline],
  );

  return (
    <div
      ref={ref}
      contentEditable={editable}
      suppressContentEditableWarning
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      style={{
        outline: editable ? "1px dashed #0D99FF80" : "none",
        borderRadius: 2,
        minHeight: "1em",
        cursor: editable ? "text" : "inherit",
        whiteSpace: multiline ? "pre-wrap" : "nowrap",
        overflow: "hidden",
        ...style,
      }}
    >
      {value}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Individual block renderers
// ---------------------------------------------------------------------------

function HeadingBlock({ p, editable, onChange }: { p: P; editable: boolean; onChange: (key: string, v: string) => void }) {
  const tag = str(p, "level", "h2") as "h2" | "h3";
  const isH2 = tag === "h2";
  return (
    <Box sx={{
      px: 2, py: 1.5, height: "100%", display: "flex", alignItems: "center",
      bgcolor: "background.paper",
    }}>
      <EditableText
        value={str(p, "text", "Heading")}
        editable={editable}
        onCommit={(v) => onChange("text", v)}
        style={{
          fontSize: isH2 ? "1.4rem" : "1.1rem",
          fontWeight: 700,
          color: "#1E293B",
          letterSpacing: "-0.3px",
          lineHeight: 1.3,
          width: "100%",
        }}
      />
    </Box>
  );
}

function BodyBlock({ p, editable, onChange }: { p: P; editable: boolean; onChange: (key: string, v: string) => void }) {
  return (
    <Box sx={{ px: 2, py: 1.5, height: "100%", bgcolor: "background.paper", overflow: "auto" }}>
      <EditableText
        value={str(p, "text", "Add your text here.")}
        editable={editable}
        multiline
        onCommit={(v) => onChange("text", v)}
        style={{ fontSize: "0.875rem", lineHeight: 1.7, color: "#374151", width: "100%" }}
      />
    </Box>
  );
}

function CalloutBlock({ p, editable, onChange }: { p: P; editable: boolean; onChange: (key: string, v: string) => void }) {
  const colour = str(p, "accentColour", "#0284C7");
  return (
    <Box sx={{
      px: 2, py: 1.5, height: "100%", display: "flex", alignItems: "flex-start", gap: 1,
      bgcolor: `${colour}0D`,
      borderLeft: `4px solid ${colour}`,
    }}>
      <InfoOutlinedIcon sx={{ fontSize: 16, color: colour, flexShrink: 0, mt: "2px" }} />
      <EditableText
        value={str(p, "text", "Key insight.")}
        editable={editable}
        multiline
        onCommit={(v) => onChange("text", v)}
        style={{ fontSize: "0.875rem", lineHeight: 1.6, color: "#1E293B", flex: 1 }}
      />
    </Box>
  );
}

function BannerBlock({ p, editable, onChange }: { p: P; editable: boolean; onChange: (key: string, v: string) => void }) {
  const bg = str(p, "bgColour", "#1E40AF");
  const tc = str(p, "textColour", "#FFFFFF");
  return (
    <Box sx={{ px: 3, height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", bgcolor: bg }}>
      <EditableText
        value={str(p, "text", "Report section")}
        editable={editable}
        onCommit={(v) => onChange("text", v)}
        style={{ fontSize: "1.1rem", fontWeight: 700, color: tc, lineHeight: 1.3 }}
      />
      {str(p, "subtitle") && (
        <EditableText
          value={str(p, "subtitle")}
          editable={editable}
          onCommit={(v) => onChange("subtitle", v)}
          style={{ fontSize: "0.8rem", color: `${tc}CC`, marginTop: 4 }}
        />
      )}
    </Box>
  );
}

function LabelBlock({ p }: { p: P }) {
  const bg = str(p, "bgColour", "#EDE9FE");
  const tc = str(p, "textColour", "#7C3AED");
  return (
    <Box sx={{
      px: 2, py: 0.75, height: "100%", display: "flex", alignItems: "center",
      bgcolor: bg,
    }}>
      <Typography sx={{ fontSize: "0.75rem", fontWeight: 700, color: tc, letterSpacing: "0.05em", textTransform: "uppercase" }}>
        {str(p, "text", "LABEL")}
      </Typography>
    </Box>
  );
}

function DividerBlock({ p }: { p: P }) {
  const colour = str(p, "colour", "#E2E8F0");
  return (
    <Box sx={{ height: "100%", display: "flex", alignItems: "center", px: 2 }}>
      <Box sx={{ width: "100%", borderTop: `${Number(p.thickness) || 1}px solid ${colour}` }} />
    </Box>
  );
}

function SpacerBlock() {
  return <Box sx={{ height: "100%", bgcolor: "transparent" }} />;
}

function ImageBlock({ p }: { p: P }) {
  const url = str(p, "url");
  const caption = str(p, "caption");
  return (
    <Box sx={{
      height: "100%", display: "flex", flexDirection: "column",
      border: "2px dashed #E2E8F0", borderRadius: 1, overflow: "hidden",
      bgcolor: "#F8FAFC",
    }}>
      {url ? (
        <img src={url} alt={str(p, "alt")} style={{ flex: 1, objectFit: "cover", width: "100%" }} />
      ) : (
        <Box sx={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 0.5, color: "text.disabled" }}>
          <ImageOutlinedIcon sx={{ fontSize: 28 }} />
          <Typography variant="caption">Add image URL in settings</Typography>
        </Box>
      )}
      {caption && (
        <Typography variant="caption" sx={{ p: 0.75, color: "text.secondary", textAlign: "center", borderTop: "1px solid", borderColor: "divider" }}>
          {caption}
        </Typography>
      )}
    </Box>
  );
}

function LinkBlock({ p }: { p: P }) {
  const text = str(p, "text", "View full report");
  const url = str(p, "url", "#");
  const isButton = p.variant === "button";
  return (
    <Box sx={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", p: 1.5 }}>
      <Box
        component="a"
        href={url}
        target="_blank"
        rel="noreferrer"
        sx={{
          display: "flex", alignItems: "center", gap: 0.5,
          ...(isButton
            ? { px: 2, py: 0.75, bgcolor: "#0369A1", color: "#fff", borderRadius: 1.5, textDecoration: "none", fontWeight: 600, fontSize: 13 }
            : { color: "#0369A1", textDecoration: "underline", fontSize: 13 }),
          "&:hover": { opacity: 0.8 },
        }}
      >
        <LinkOutlinedIcon sx={{ fontSize: 14 }} />
        {text}
      </Box>
    </Box>
  );
}

function MetricCardBlock({ p }: { p: P }) {
  const colour = str(p, "colour", "#047857");
  const delta = str(p, "delta");
  return (
    <Box sx={{
      height: "100%", display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", p: 2,
      bgcolor: `${colour}0D`, borderTop: `3px solid ${colour}`,
      textAlign: "center",
    }}>
      <Typography sx={{ fontSize: "2.2rem", fontWeight: 800, color: colour, lineHeight: 1 }}>
        {str(p, "value", "--")}
      </Typography>
      {delta && (
        <Typography variant="caption" sx={{ color: delta.startsWith("-") ? "#DC2626" : "#047857", fontWeight: 700, mt: 0.25 }}>
          {delta}
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
        {str(p, "label", "Metric")}
      </Typography>
      {str(p, "subtitle") && (
        <Typography variant="caption" sx={{ color: "text.disabled", fontSize: 10 }}>
          {str(p, "subtitle")}
        </Typography>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main ContentBlockTile
// ---------------------------------------------------------------------------

export default function ContentBlockTile({ tile, builderMode = false, isSelected = false, onParamChange }: ContentBlockTileProps) {
  const p = (tile.param_overrides ?? {}) as P;
  const editable = builderMode && isSelected && !!onParamChange;

  const handleChange = useCallback(
    (key: string, value: string) => {
      if (!onParamChange) return;
      onParamChange({ ...tile, param_overrides: { ...tile.param_overrides, [key]: value } });
    },
    [tile, onParamChange],
  );

  const id = tile.metric_id;

  if (id === "content-heading" || id === "content-subheading") {
    return <HeadingBlock p={p} editable={editable} onChange={handleChange} />;
  }
  if (id === "content-body") {
    return <BodyBlock p={p} editable={editable} onChange={handleChange} />;
  }
  if (id === "content-callout") {
    return <CalloutBlock p={p} editable={editable} onChange={handleChange} />;
  }
  if (id === "content-banner") {
    return <BannerBlock p={p} editable={editable} onChange={handleChange} />;
  }
  if (id === "content-label") {
    return <LabelBlock p={p} />;
  }
  if (id === "content-divider") {
    return <DividerBlock p={p} />;
  }
  if (id === "content-spacer") {
    return <SpacerBlock />;
  }
  if (id === "content-image") {
    return <ImageBlock p={p} />;
  }
  if (id === "content-link") {
    return <LinkBlock p={p} />;
  }
  if (id === "content-metric-card") {
    return <MetricCardBlock p={p} />;
  }

  return (
    <Box sx={{ p: 2, height: "100%", display: "flex", alignItems: "center", color: "text.disabled" }}>
      <Typography variant="caption">Unknown block: {id}</Typography>
    </Box>
  );
}
