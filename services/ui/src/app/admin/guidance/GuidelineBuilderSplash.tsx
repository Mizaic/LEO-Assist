/**
 * Atlas trace: DI-6AE25829 / DI-0C8FBAF7 (cosmetic -- no functional overlap,
 * confirmed via search_design_controls before implementation).
 *
 * A playful, animated splash shown once per browser session the first time
 * an administrator opens the Clinical Guidelines tab. Purely decorative:
 * it carries no state, no data, and blocks nothing -- it auto-dismisses and
 * can be skipped instantly. Respects prefers-reduced-motion via useMotion().
 */
"use client";

import { useEffect } from "react";
import { motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import { useMotion } from "@leo/design-system";

export const GUIDANCE_SPLASH_SESSION_KEY = "leo.guidance.splashSeen";

interface ChipSpec {
  color: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
}

const CHIPS: ChipSpec[] = [
  { color: "#0891b2", from: { x: -180, y: -140 }, to: { x: -54, y: -54 } },
  { color: "#2563EB", from: { x: 180, y: -140 }, to: { x: 54, y: -54 } },
  { color: "#7C3AED", from: { x: -180, y: 140 }, to: { x: -54, y: 54 } },
  { color: "#D97706", from: { x: 180, y: 140 }, to: { x: 54, y: 54 } },
];

interface Props {
  onDismiss: () => void;
}

export default function GuidelineBuilderSplash({ onDismiss }: Props) {
  const { reducedMotion } = useMotion();

  useEffect(() => {
    const duration = reducedMotion ? 350 : 1800;
    const timer = setTimeout(onDismiss, duration);
    return () => clearTimeout(timer);
  }, [reducedMotion, onDismiss]);

  return (
    <fm.div
      role="presentation"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.25 } }}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 2000,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #F8FAFC 0%, #EEF2FF 100%)",
      }}
    >
      <Box sx={{ position: "absolute", top: 20, right: 24 }}>
        <Button
          onClick={onDismiss}
          size="small"
          variant="text"
          aria-label="Skip the guideline builder intro animation"
          sx={{ color: "text.secondary" }}
        >
          Skip
        </Button>
      </Box>

      <Box
        aria-live="polite"
        role="status"
        sx={{
          position: "absolute",
          width: 1,
          height: 1,
          overflow: "hidden",
          clip: "rect(0 0 0 0)",
        }}
      >
        Loading your guideline builder
      </Box>

      <Box aria-hidden="true" sx={{ position: "relative", width: 220, height: 200 }}>
        {!reducedMotion &&
          CHIPS.map((chip, i) => (
            <fm.div
              key={chip.color}
              initial={{ x: chip.from.x, y: chip.from.y, opacity: 0, scale: 0.4 }}
              animate={{
                x: chip.to.x,
                y: chip.to.y,
                opacity: 1,
                scale: 1,
                rotate: [0, 12, -8, 0],
              }}
              transition={{
                type: "spring",
                stiffness: 260,
                damping: 16,
                delay: i * 0.09,
              }}
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                marginLeft: -18,
                marginTop: -18,
                width: 36,
                height: 36,
                borderRadius: "50%",
                background: chip.color,
                boxShadow: "0 6px 16px rgba(15, 23, 42, 0.18)",
              }}
            />
          ))}
        <fm.div
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{
            type: "spring",
            stiffness: 320,
            damping: 20,
            delay: reducedMotion ? 0 : 0.55,
          }}
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            marginLeft: -30,
            marginTop: -30,
            width: 60,
            height: 60,
            borderRadius: "50%",
            background: "#14B8A6",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 10px 24px rgba(20, 184, 166, 0.35)",
          }}
        >
          <CheckRoundedIcon sx={{ color: "#FFFFFF", fontSize: 32 }} />
        </fm.div>
      </Box>

      <fm.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: reducedMotion ? 0 : 0.75 }}
        style={{ textAlign: "center", maxWidth: 360, marginTop: 8 }}
      >
        <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
          Clinical Guidelines
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Rules based on NICE and local guidance that LEO follows.
        </Typography>
      </fm.div>
    </fm.div>
  );
}
