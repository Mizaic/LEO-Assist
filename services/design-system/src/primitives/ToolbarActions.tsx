/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BCA9B190")
 */
"use client";

import type { ReactNode } from "react";

import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";
import { useMotion } from "../motion";

export interface ToolbarAction {
  id: string;
  label: string;
  onClick: () => void;
  icon?: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  loading?: boolean;
}

export interface ToolbarActionsProps {
  actions: ToolbarAction[];
  align?: "start" | "end";
}

/**
 * ToolbarActions -- right-aligned action cluster with hover lift.
 * Primary buttons use the brand tone; secondary use an outline and
 * ghost drops the border. Honours reduced-motion.
 *
 * Design Controls: DI-LEO-AI-142, DO-LEO-AI-139, VT-LEO-AI-141.
 */

function styleForVariant(
  variant: ToolbarAction["variant"],
): React.CSSProperties {
  if (variant === "primary") {
    return {
      background: color.brand.primary,
      color: color.brand.onBrand,
      borderColor: color.brand.primary,
    };
  }
  if (variant === "ghost") {
    return {
      background: "transparent",
      color: color.text.primary,
      borderColor: "transparent",
    };
  }
  return {
    background: color.surface.raised,
    color: color.text.primary,
    borderColor: color.surface.divider,
  };
}

export function ToolbarActions({
  actions,
  align = "end",
}: ToolbarActionsProps) {
  const { reducedMotion } = useMotion();
  const transitionMs = reducedMotion ? 0 : 120;

  return (
    <div
      data-testid="toolbar-actions"
      style={{
        display: "inline-flex",
        justifyContent: align === "end" ? "flex-end" : "flex-start",
        gap: 8,
        fontFamily: typography.fontFamily.body,
      }}
    >
      {actions.map((a) => {
        const variantStyle = styleForVariant(a.variant ?? "secondary");
        const isDisabled = a.disabled || a.loading;
        return (
          <button
            key={a.id}
            type="button"
            onClick={a.onClick}
            disabled={isDisabled}
            data-testid={"toolbar-action-" + a.id}
            style={{
              appearance: "none",
              border: "1px solid",
              borderRadius: radius.md,
              fontFamily: typography.fontFamily.body,
              fontSize: 14,
              fontWeight: 600,
              height: 40,
              padding: "0 14px",
              cursor: isDisabled ? "not-allowed" : "pointer",
              opacity: isDisabled ? 0.6 : 1,
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              transition:
                "transform " +
                transitionMs +
                "ms ease-out, box-shadow " +
                transitionMs +
                "ms ease-out",
              ...variantStyle,
            }}
            onMouseDown={(e) => {
              if (isDisabled) return;
              e.currentTarget.style.transform = "translateY(1px)";
            }}
            onMouseUp={(e) => {
              if (isDisabled) return;
              e.currentTarget.style.transform = "translateY(0)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = "translateY(0)";
            }}
          >
            {a.icon ?? null}
            <span>{a.loading ? a.label + "\u2026" : a.label}</span>
          </button>
        );
      })}
    </div>
  );
}
