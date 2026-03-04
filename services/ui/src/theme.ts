"use client";

import { createTheme } from "@mui/material/styles";

const FONT_BODY = "'DM Sans', system-ui, sans-serif";
const FONT_MONO = "'JetBrains Mono', monospace";

const theme = createTheme({
  palette: {
    primary: { main: "#1F3A8A", light: "#3B5FD9", dark: "#152A66" },
    secondary: { main: "#14B8A6", light: "#2DD4BF", dark: "#0D9488" },
    background: { default: "#F8FAFC", paper: "#FFFFFF" },
    divider: "#E2E8F0",
    text: { primary: "#0F172A", secondary: "#596577" },
    success: { main: "#16a34a", light: "#22c55e" },
    error: { main: "#dc2626", light: "#ef4444" },
    warning: { main: "#d97706", light: "#f59e0b" },
    info: { main: "#1F3A8A", light: "#3B5FD9" },
  },
  typography: {
    fontFamily: FONT_BODY,
    h4: { fontWeight: 700, letterSpacing: "-0.01em" },
    h5: { fontWeight: 700, letterSpacing: "-0.01em" },
    h6: { fontWeight: 600 },
    subtitle1: { fontWeight: 600, fontFamily: FONT_MONO, fontSize: "0.95rem" },
    subtitle2: { fontWeight: 500, fontFamily: FONT_MONO, fontSize: "0.85rem" },
    body2: { color: "#596577" },
    caption: { color: "#6B7280" },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        "::selection": { background: "#c7d2fe" },
        "kbd": { fontFamily: FONT_MONO },
        "@keyframes cardIn": {
          from: { opacity: 0, transform: "translateY(-6px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
        "@keyframes slideIn": {
          from: { opacity: 0, transform: "translateX(20px)" },
          to: { opacity: 1, transform: "translateX(0)" },
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 600, borderRadius: 8 },
        sizeMedium: { padding: "8px 20px", minHeight: 40 },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          border: "1px solid #E2E8F0",
          boxShadow: "none",
          transition: "box-shadow 0.15s ease, border-color 0.15s ease",
          "&:hover": {
            boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
            borderColor: "#CBD5E1",
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 500, borderRadius: 6 },
        sizeSmall: { height: 24, fontSize: "0.75rem" },
      },
    },
    MuiTextField: {
      defaultProps: { size: "small", variant: "outlined" },
      styleOverrides: {
        root: { "& .MuiOutlinedInput-root": { borderRadius: 8 } },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: { fontWeight: 600, color: "#596577", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" },
        root: { borderColor: "#F1F5F9" },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          cursor: "pointer",
          "&:hover": { backgroundColor: "#F8FAFC" },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 12 },
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
        root: { borderRadius: 4, height: 6, backgroundColor: "#E2E8F0" },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          margin: "2px 8px",
          "&.Mui-selected": {
            backgroundColor: "rgba(31, 58, 138, 0.08)",
            "&:hover": { backgroundColor: "rgba(31, 58, 138, 0.12)" },
          },
        },
      },
    },
    MuiSkeleton: {
      styleOverrides: { root: { borderRadius: 8 } },
    },
  },
});

export default theme;
