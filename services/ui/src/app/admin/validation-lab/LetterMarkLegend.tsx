/**
 * How to read letter marks: fill is kind, bar is context.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836 / VT-F0A6B9F4
 */
"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { changeLabel, type LetterMark } from "./letterHighlight";
import {
  assertionStyle,
  CONTEXT_BAR_PX,
  LEGEND_WHAT_KEYS,
  LEGEND_WHEN_KEYS,
  semanticTagStyle,
} from "./letterMarkStyle";

export function LetterMarkLegend({ marks }: { marks: LetterMark[] }) {
  if (!marks.length) return null;
  const changes = unique(
    marks.map((mark) => changeLabel(mark.change || "stable")).filter(Boolean),
  );
  return (
    <Stack
      spacing={1}
      sx={{
        mb: 1.5,
        p: 1.25,
        bgcolor: "#FFFFFF",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "8px",
      }}
      data-testid="validation-lab-letter-legend"
    >
      <Typography variant="caption" sx={{ fontWeight: 700, color: "text.primary" }}>
        How to read a highlight
      </Typography>
      <LegendSample />
      <LegendGroup
        title="When it applies -- the bar"
        variant="bar"
        items={LEGEND_WHEN_KEYS.map((key) => ({
          key,
          style: assertionStyle(key),
        }))}
      />
      <LegendGroup
        title="What it is -- the colour"
        variant="fill"
        items={LEGEND_WHAT_KEYS.map((key) => ({
          key,
          style: semanticTagStyle(key) || assertionStyle("present"),
        }))}
      />
      {changes.length ? (
        <Typography variant="caption" color="text.secondary">
          This step changed: {changes.join(", ")}
        </Typography>
      ) : null}
    </Stack>
  );
}

function LegendSample() {
  const when = assertionStyle("present");
  const what = semanticTagStyle("finding") || when;
  return (
    <Box>
      <Box
        component="span"
        sx={{
          display: "inline-block",
          bgcolor: what.bg,
          color: what.fg,
          borderLeft: `${CONTEXT_BAR_PX}px solid ${when.bar || when.fg}`,
          pl: 1.1,
          py: 0.35,
          borderRadius: "2px",
          fontWeight: 800,
          fontSize: "0.9rem",
        }}
      >
        jaundice
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
        Example: the colour means finding. The bar means present.
      </Typography>
    </Box>
  );
}

function LegendGroup({
  title,
  items,
  variant,
}: {
  title: string;
  items: Array<{ key: string; style: { bg: string; fg: string; label: string } }>;
  variant: "bar" | "fill";
}) {
  return (
    <Box>
      <Typography
        variant="caption"
        sx={{
          display: "block",
          fontWeight: 700,
          color: "text.secondary",
          mb: 0.5,
        }}
      >
        {title}
      </Typography>
      <LegendRow items={items} variant={variant} />
    </Box>
  );
}

function LegendRow({
  items,
  variant,
}: {
  items: Array<{ key: string; style: { bg: string; fg: string; label: string } }>;
  variant: "bar" | "fill";
}) {
  return (
    <Stack direction="row" flexWrap="wrap" gap={0.75}>
      {items.map((item) =>
        variant === "bar" ? (
          <LegendBarChip key={item.key} style={item.style} />
        ) : (
          <LegendFillChip key={item.key} style={item.style} />
        ),
      )}
    </Stack>
  );
}

function LegendBarChip({
  style,
}: {
  style: { bg: string; fg: string; label: string };
}) {
  return (
    <Box
      component="span"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        px: 0.5,
        py: 0.1,
        fontSize: "0.7rem",
        fontWeight: 700,
        color: "text.primary",
      }}
    >
      <Box
        component="span"
        sx={{
          width: CONTEXT_BAR_PX,
          height: 16,
          bgcolor: style.bar || style.fg,
          borderRadius: "2px",
        }}
      />
      {style.label}
    </Box>
  );
}

function LegendFillChip({
  style,
}: {
  style: { bg: string; fg: string; label: string };
}) {
  return (
    <Box
      component="span"
      sx={{
        bgcolor: style.bg,
        color: style.fg,
        px: 0.75,
        py: 0.15,
        borderRadius: "4px",
        fontSize: "0.7rem",
        fontWeight: 700,
      }}
    >
      {style.label}
    </Box>
  );
}

function unique(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    const key = value.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(value);
  }
  return out;
}
