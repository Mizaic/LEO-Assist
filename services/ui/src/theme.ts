"use client";

import { createTheme } from "@mui/material/styles";
import { FOCUS_RING, MOTION, RADIUS, TYPE_SCALE } from "@/theme/tokens";

const FONT_BODY = "'DM Sans', system-ui, sans-serif";
const FONT_MONO = "'JetBrains Mono', monospace";

const theme = createTheme({
  palette: {
    primary: { main: "#1F3A8A", light: "#3B5FD9", dark: "#152A66" },
    secondary: { main: "#0F766E", light: "#14B8A6", dark: "#0D5D56" },
    background: { default: "#F8FAFC", paper: "#FFFFFF" },
    divider: "#CBD5E1",
    text: { primary: "#0F172A", secondary: "#596577" },
    success: { main: "#15803d", light: "#22c55e", dark: "#166534" },
    error: { main: "#b91c1c", light: "#dc2626", dark: "#991b1b" },
    warning: { main: "#b45309", light: "#d97706", dark: "#92400e" },
    info: { main: "#1F3A8A", light: "#3B5FD9" },
  },
  typography: {
    fontFamily: FONT_BODY,
    fontSize: 16,
    h1: TYPE_SCALE.h1,
    h2: TYPE_SCALE.h2,
    h3: TYPE_SCALE.h3,
    h4: TYPE_SCALE.h4,
    h5: TYPE_SCALE.h5,
    h6: TYPE_SCALE.h6,
    body1: TYPE_SCALE.body1,
    body2: { ...TYPE_SCALE.body2, color: "#596577" },
    caption: { ...TYPE_SCALE.caption, color: "#6B7280" },
    subtitle1: { fontWeight: 600, fontFamily: FONT_MONO, fontSize: "1rem" },
    subtitle2: { fontWeight: 500, fontFamily: FONT_MONO, fontSize: "0.9rem" },
  },
  shape: { borderRadius: RADIUS.md },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        "::selection": { background: "#c7d2fe" },
        "kbd": { fontFamily: FONT_MONO },
        ":focus-visible": {
          outline: `${FOCUS_RING.widthPx}px solid ${FOCUS_RING.color}`,
          outlineOffset: `${FOCUS_RING.offsetPx}px`,
        },
        "@keyframes cardIn": {
          from: { opacity: 0, transform: "translateY(-6px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
        "@keyframes slideIn": {
          from: { opacity: 0, transform: "translateX(20px)" },
          to: { opacity: 1, transform: "translateX(0)" },
        },
        "@media (prefers-reduced-motion: reduce)": {
          "*, *::before, *::after": {
            animationDuration: "0.001ms !important",
            animationIterationCount: "1 !important",
            transitionDuration: "0.001ms !important",
          },
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 600,
          borderRadius: RADIUS.sm,
          transitionDuration: `${MOTION.durationFast}ms`,
        },
        sizeMedium: { padding: "8px 20px", minHeight: 40 },
        sizeSmall: { minHeight: 32 },
        sizeLarge: { minHeight: 48 },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: RADIUS.lg,
          border: "1px solid #E2E8F0",
          boxShadow: "none",
          transition: `box-shadow ${MOTION.durationFast}ms ease, border-color ${MOTION.durationFast}ms ease`,
          "&:hover": {
            boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
            borderColor: "#CBD5E1",
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 500, borderRadius: RADIUS.sm },
        sizeSmall: { height: 24, fontSize: "0.8125rem" },
      },
    },
    MuiTextField: {
      defaultProps: { size: "small", variant: "outlined" },
      styleOverrides: {
        root: { "& .MuiOutlinedInput-root": { borderRadius: RADIUS.sm } },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontWeight: 600,
          color: "#475569",
          fontSize: "0.8125rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        },
        root: { borderColor: "#F1F5F9" },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          "&:hover": { backgroundColor: "#F8FAFC" },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: RADIUS.lg },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          borderRight: "1px solid #E2E8F0",
          backgroundColor: "#FFFFFF",
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: { borderRadius: RADIUS.sm / 2, height: 6, backgroundColor: "#E2E8F0" },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: RADIUS.sm,
          margin: "2px 8px",
          "&.Mui-selected": {
            backgroundColor: "rgba(31, 58, 138, 0.1)",
            "&:hover": { backgroundColor: "rgba(31, 58, 138, 0.14)" },
          },
        },
      },
    },
    MuiSkeleton: {
      styleOverrides: { root: { borderRadius: RADIUS.sm } },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          fontSize: "0.8125rem",
          backgroundColor: "#0F172A",
        },
      },
    },
  },
});

export default theme;
