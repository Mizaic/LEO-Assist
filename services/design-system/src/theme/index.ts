"use client";

import { createTheme, type Theme } from "@mui/material/styles";

import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";

/**
 * Creates the MUI theme for the LEO Intelligence Console. All inputs
 * come from the design-system token set so re-theming happens in one
 * place. DM Sans and JetBrains Mono are loaded via next/font in the
 * consuming app (services/ui/src/lib/fonts.ts) and surface through the
 * --font-dm-sans / --font-jetbrains-mono CSS variables referenced
 * below.
 *
 * Design Controls: DI-LEO-AI-141, DO-LEO-AI-138, VT-LEO-AI-140.
 */

const MUI_PRIMARY = "#1F3A8A";
const MUI_PRIMARY_LIGHT = "#3B5FD9";
const MUI_PRIMARY_DARK = "#152A66";
const MUI_DIVIDER = "#CBD5E1";
const MUI_SELECTION = "#C7D2FE";

const MOTION_FAST_MS = 120;

const FONT_BODY = typography.fontFamily.body;
const FONT_MONO = typography.fontFamily.mono;

function displayScale() {
  return {
    h1: { fontSize: "2rem", fontWeight: 700, lineHeight: 1.2, letterSpacing: "-0.01em" },
    h2: { fontSize: "1.5rem", fontWeight: 700, lineHeight: 1.25, letterSpacing: "-0.01em" },
    h3: { fontSize: "1.25rem", fontWeight: 600, lineHeight: 1.3 },
    h4: { fontSize: "1.125rem", fontWeight: 700, lineHeight: 1.35, letterSpacing: "-0.01em" },
    h5: { fontSize: "1rem", fontWeight: 700, lineHeight: 1.4, letterSpacing: "-0.01em" },
    h6: { fontSize: "0.95rem", fontWeight: 600, lineHeight: 1.4 },
    body1: { fontSize: "1rem", fontWeight: 400, lineHeight: 1.55 },
    body2: { fontSize: "0.95rem", fontWeight: 400, lineHeight: 1.5, color: color.text.secondary },
    caption: { fontSize: "0.8125rem", fontWeight: 400, lineHeight: 1.45, color: color.text.caption },
    subtitle1: { fontWeight: 600, fontFamily: FONT_BODY, fontSize: "1rem" },
    subtitle2: { fontWeight: 600, fontFamily: FONT_BODY, fontSize: "0.9rem" },
  };
}

function baseOverrides() {
  return {
    MuiCssBaseline: {
      styleOverrides: {
        "::selection": { background: MUI_SELECTION },
        kbd: { fontFamily: FONT_MONO },
        ":focus-visible": {
          outline: "3px solid " + color.focus.ring,
          outlineOffset: "2px",
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
          textTransform: "none" as const,
          fontWeight: 600,
          borderRadius: radius.sm,
          transitionDuration: MOTION_FAST_MS + "ms",
        },
        sizeMedium: { padding: "8px 20px", minHeight: 40 },
        sizeSmall: { minHeight: 32 },
        sizeLarge: { minHeight: 48 },
      },
    },
  };
}

function componentOverrides() {
  return {
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: radius.lg,
          border: "1px solid " + color.surface.divider,
          boxShadow: "none",
          transition:
            "box-shadow " + MOTION_FAST_MS + "ms ease, border-color " +
            MOTION_FAST_MS + "ms ease",
          "&:hover": {
            boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
            borderColor: MUI_DIVIDER,
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 500, borderRadius: radius.sm },
        sizeSmall: { height: 24, fontSize: "0.8125rem" },
      },
    },
    MuiTextField: {
      defaultProps: { size: "small" as const, variant: "outlined" as const },
      styleOverrides: {
        root: { "& .MuiOutlinedInput-root": { borderRadius: radius.sm } },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontWeight: 600,
          color: "#475569",
          fontSize: "0.8125rem",
          textTransform: "uppercase" as const,
          letterSpacing: "0.05em",
        },
        root: { borderColor: "#F1F5F9" },
      },
    },
    MuiTableRow: {
      styleOverrides: { root: { "&:hover": { backgroundColor: color.surface.alt } } },
    },
    MuiDialog: {
      styleOverrides: { paper: { borderRadius: radius.lg } },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          borderRight: "1px solid " + color.surface.divider,
          backgroundColor: color.surface.base,
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: radius.sm / 2,
          height: 6,
          backgroundColor: color.surface.divider,
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: radius.sm,
          margin: "2px 8px",
          "&.Mui-selected": {
            backgroundColor: "rgba(31, 58, 138, 0.1)",
            "&:hover": { backgroundColor: "rgba(31, 58, 138, 0.14)" },
          },
        },
      },
    },
    MuiSkeleton: { styleOverrides: { root: { borderRadius: radius.sm } } },
    MuiTooltip: {
      styleOverrides: {
        tooltip: { fontSize: "0.8125rem", backgroundColor: color.text.primary },
      },
    },
  };
}

export function createLeoTheme(): Theme {
  const base = baseOverrides();
  const components = componentOverrides();
  return createTheme({
    palette: {
      primary: { main: MUI_PRIMARY, light: MUI_PRIMARY_LIGHT, dark: MUI_PRIMARY_DARK },
      secondary: { main: "#0F766E", light: "#14B8A6", dark: "#0D5D56" },
      background: { default: color.surface.alt, paper: color.surface.base },
      divider: MUI_DIVIDER,
      text: { primary: color.text.primary, secondary: color.text.secondary },
      success: { main: "#15803D", light: "#22C55E", dark: "#166534" },
      error: { main: color.status.danger, light: "#DC2626", dark: "#991B1B" },
      warning: { main: color.status.warning, light: "#D97706", dark: "#92400E" },
      info: { main: MUI_PRIMARY, light: MUI_PRIMARY_LIGHT },
    },
    typography: {
      fontFamily: FONT_BODY,
      fontSize: typography.fontSize.body,
      ...displayScale(),
    },
    shape: { borderRadius: radius.md },
    // Leave theme.spacing default (8px == tokens.spacing.xs) so sx={{ p: 2 }}
    // continues to mean 16px. Breaking that invariant would regress every
    // page we just shipped.
    components: { ...base, ...components },
  });
}
