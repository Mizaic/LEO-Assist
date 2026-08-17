/**
 * App shell nav chrome -- midnight navy structural rail.
 * Heavier than page frost. Brand: dark surfaces use white ink.
 */
import type { SxProps, Theme } from "@mui/material/styles";

import { color } from "@leo/design-system/tokens";

export const NAV_INK = "rgba(255, 255, 255, 0.78)";
export const NAV_INK_STRONG = "#FFFFFF";
export const NAV_INK_MUTED = "rgba(255, 255, 255, 0.55)";
export const NAV_HAIRLINE = "rgba(255, 255, 255, 0.12)";
export const NAV_HOVER = "rgba(255, 255, 255, 0.08)";
export const NAV_ACCENT = color.brand.primary;

const PRESS: SxProps<Theme> = {
  "&:active": { transform: "scale(0.97)" },
  transition: "transform 100ms ease-out, background-color 160ms ease-out",
  "@media (prefers-reduced-motion: reduce)": {
    "&:active": { transform: "none" },
    transition: "none",
  },
};

export const drawerPaperSx: SxProps<Theme> = {
  backgroundColor: color.brand.primaryDark,
  backgroundImage: "none",
  color: NAV_INK_STRONG,
  borderRight: "1px solid " + NAV_HAIRLINE,
  boxShadow: "4px 0 24px rgba(0, 9, 59, 0.22)",
};

export const mobileAppBarSx: SxProps<Theme> = {
  bgcolor: color.brand.primaryDark,
  color: NAV_INK_STRONG,
  borderBottom: "1px solid " + NAV_HAIRLINE,
};

export function railButtonSx(active: boolean): SxProps<Theme> {
  return {
    justifyContent: "center",
    px: 0,
    py: 1,
    minHeight: 44,
    mx: 0.75,
    borderRadius: 2,
    backgroundColor: active ? color.brand.primary : "transparent",
    "&:hover": {
      backgroundColor: active ? color.brand.primaryHover : NAV_HOVER,
    },
    "&.Mui-selected": {
      backgroundColor: color.brand.primary,
      "&:hover": { backgroundColor: color.brand.primaryHover },
    },
    ...PRESS,
  };
}

export function railIconSx(active: boolean): SxProps<Theme> {
  return {
    minWidth: 0,
    color: active ? color.brand.onBrand : NAV_INK,
  };
}

export function fullNavButtonSx(active: boolean): SxProps<Theme> {
  return {
    py: 1.2,
    borderRadius: 2,
    backgroundColor: active ? color.brand.primary : "transparent",
    "&:hover": {
      backgroundColor: active ? color.brand.primaryHover : NAV_HOVER,
    },
    "&.Mui-selected": {
      backgroundColor: color.brand.primary,
      color: color.brand.onBrand,
      "&:hover": { backgroundColor: color.brand.primaryHover },
    },
    ...PRESS,
  };
}

export function fullNavIconSx(active: boolean): SxProps<Theme> {
  return {
    minWidth: 36,
    color: active ? color.brand.onBrand : NAV_INK,
  };
}
