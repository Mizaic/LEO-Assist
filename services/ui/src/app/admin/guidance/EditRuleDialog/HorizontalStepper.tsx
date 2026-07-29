/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Single flat stepper for the rule editor.
 *
 * Slots come from `buildNavSlots` -- Always true, Situations, then one
 * pill per confirmed situation (A, B, ...), Check, Suggest, Save.
 * There is no nested breadcrumb under Who; situation count can grow
 * after the situations step confirms.
 */
import { motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";

import { useMotion } from "@leo/design-system";

import type { NavSlot, NavSlotId } from "./navSlots";

interface Props {
  slots: NavSlot[];
  currentSlotId: NavSlotId;
  onJump: (slot: NavSlot) => void;
}

export default function HorizontalStepper({
  slots,
  currentSlotId,
  onJump,
}: Props) {
  return (
    <Box
      component="nav"
      role="navigation"
      aria-label="Steps to change this rule"
      data-tour="er-01-stepper"
      sx={{
        px: { xs: 1.5, md: 2.5 },
        py: 1,
        bgcolor: "background.paper",
        borderBottom: "1px solid",
        borderColor: "divider",
        overflowX: "auto",
      }}
    >
      <Stack
        component="ol"
        direction="row"
        spacing={{ xs: 0.5, md: 1 }}
        sx={{
          m: 0,
          p: 0,
          listStyle: "none",
          minWidth: "fit-content",
          alignItems: "stretch",
        }}
      >
        {slots.map((slot, index) => {
          const isCurrent = slot.id === currentSlotId;
          const isLast = index === slots.length - 1;
          const currentIndex = slots.findIndex((s) => s.id === currentSlotId);
          const isDone = index < currentIndex;
          return (
            <Box
              component="li"
              key={slot.id}
              sx={{
                p: 0,
                m: 0,
                display: "flex",
                alignItems: "center",
                flexShrink: 0,
              }}
            >
              <StepperItem
                slot={slot}
                index={index + 1}
                total={slots.length}
                isCurrent={isCurrent}
                isDone={isDone}
                onJump={onJump}
              />
              {!isLast && <StepperConnector />}
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
}

interface ItemProps {
  slot: NavSlot;
  index: number;
  total: number;
  isCurrent: boolean;
  isDone: boolean;
  onJump: (slot: NavSlot) => void;
}

function StepperItem({
  slot,
  index,
  total,
  isCurrent,
  isDone,
  onJump,
}: ItemProps) {
  const { reducedMotion } = useMotion();
  const locked = !slot.jumpable && !isCurrent;
  const ariaLabel = `Step ${index} of ${total}: ${slot.title}.${
    isCurrent ? " Current step." : ""
  }${locked ? " Not available yet." : ""}`;

  return (
    <Box
      component="button"
      type="button"
      onClick={() => {
        if (locked) return;
        onJump(slot);
      }}
      disabled={locked}
      aria-label={ariaLabel}
      aria-current={isCurrent ? "step" : undefined}
      sx={{
        position: "relative",
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        gap: 1,
        px: { xs: 1, md: 1.5 },
        py: 0.75,
        border: "none",
        borderRadius: 999,
        bgcolor: "transparent",
        color: locked ? "text.disabled" : "text.primary",
        cursor: locked ? "default" : "pointer",
        transition: "color 120ms ease, transform 120ms ease",
        "&:hover": {
          bgcolor: isCurrent || locked ? "transparent" : "action.hover",
        },
        "&:focus-visible": {
          outline: "2px solid",
          outlineColor: "primary.main",
          outlineOffset: 2,
        },
        "&:disabled": {
          color: "text.disabled",
        },
      }}
    >
      {isCurrent && (
        <fm.div
          layoutId="stepper-active-pill"
          transition={
            reducedMotion
              ? { duration: 0 }
              : { type: "spring", stiffness: 380, damping: 32 }
          }
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: 999,
            background: "var(--mui-palette-primary-50, #EFF6FF)",
            zIndex: 0,
          }}
        />
      )}
      <Box
        aria-hidden="true"
        sx={{
          position: "relative",
          zIndex: 1,
          width: 26,
          height: 26,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "0.85rem",
          fontWeight: 700,
          color: isDone
            ? "success.dark"
            : isCurrent
              ? "primary.dark"
              : "text.secondary",
          bgcolor: isDone
            ? "success.100"
            : isCurrent
              ? "primary.100"
              : "grey.100",
          flexShrink: 0,
        }}
      >
        {isDone ? (
          <CheckCircleRoundedIcon
            fontSize="inherit"
            sx={{ fontSize: "1rem" }}
          />
        ) : slot.id.startsWith("situation-") ? (
          slot.shortLabel
        ) : (
          index
        )}
      </Box>
      <Box sx={{ position: "relative", zIndex: 1, minWidth: 0, textAlign: "left" }}>
        <Typography
          variant="body2"
          sx={{
            fontWeight: isCurrent ? 700 : 500,
            color: isCurrent ? "primary.dark" : "inherit",
            lineHeight: 1.2,
            display: { xs: "none", sm: "block" },
            whiteSpace: "nowrap",
          }}
        >
          {slot.id.startsWith("situation-") ? slot.shortLabel : slot.title}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            fontWeight: isCurrent ? 700 : 500,
            color: isCurrent ? "primary.dark" : "inherit",
            lineHeight: 1.2,
            display: { xs: "block", sm: "none" },
            whiteSpace: "nowrap",
          }}
        >
          {slot.shortLabel}
        </Typography>
      </Box>
    </Box>
  );
}

function StepperConnector() {
  return (
    <Box
      aria-hidden="true"
      sx={{
        width: { xs: 16, md: 28 },
        height: "1px",
        bgcolor: "divider",
        mx: { xs: 0.25, md: 0.5 },
        flexShrink: 0,
      }}
    />
  );
}
