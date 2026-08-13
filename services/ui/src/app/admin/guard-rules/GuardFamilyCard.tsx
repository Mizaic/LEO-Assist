/**
 * Compact Pipeline Guard family card -- title and type only.
 * Click opens the family dialog.
 */
"use client";

import { motion as fm } from "framer-motion";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { GuardFamilyCopy } from "./guardFamilyCopy";
import { familyKind } from "./guardFamilyCopy";
import type { NerGuardRule } from "./types";

interface GuardFamilyCardProps {
  copy: GuardFamilyCopy;
  rules: NerGuardRule[];
  index: number;
  onOpen: () => void;
}

function sourceType(rules: NerGuardRule[]): string {
  const hasBuiltin = rules.some((rule) => rule.source === "builtin");
  const hasAdded = rules.some((rule) => rule.source !== "builtin");
  if (hasBuiltin && hasAdded) return "Built-in + added";
  if (hasAdded) return "Added";
  return "Built-in";
}

export default function GuardFamilyCard({
  copy,
  rules,
  index,
  onOpen,
}: GuardFamilyCardProps) {
  return (
    <fm.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.22,
        ease: "easeOut",
        delay: Math.min(index, 12) * 0.04,
      }}
      whileHover={{ boxShadow: "0 6px 16px rgba(15, 23, 42, 0.08)" }}
      style={{ height: "100%" }}
    >
      <button
        type="button"
        onClick={onOpen}
        data-testid={`guard-family-card-${copy.key}`}
        aria-label={`Open ${copy.title} details`}
        style={{
          position: "relative",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 10,
          width: "100%",
          height: "100%",
          minHeight: 104,
          textAlign: "left",
          background: "#FFFFFF",
          border: "1px solid #E2E8F0",
          borderRadius: 12,
          padding: "18px 18px 18px 22px",
          cursor: "pointer",
          font: "inherit",
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
            background: copy.accent,
          }}
        />
        <Typography component="h2" variant="subtitle1" sx={{ fontWeight: 700, fontSize: "1rem" }}>
          {copy.title}
        </Typography>
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Chip size="small" label={familyKind(copy.key)} sx={{ height: 22, fontSize: "0.7rem" }} />
          <Chip size="small" label={sourceType(rules)} sx={{ height: 22, fontSize: "0.7rem" }} />
        </Stack>
      </button>
    </fm.div>
  );
}
