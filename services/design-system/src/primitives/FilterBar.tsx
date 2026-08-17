/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BCA9B190")
 */
"use client";

import type { ChangeEvent, FormEvent, ReactNode } from "react";
import { motion as fm } from "framer-motion";

import { useMotion } from "../motion";
import { springOrInstant, springs, tapScale } from "../motion/springs";
import { color } from "../tokens/color";
import { elevation, radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";

export interface FilterChip {
  id: string;
  label: string;
  active: boolean;
  count?: number;
  onToggle: () => void;
}

export interface FilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  "aria-label"?: string;
  chips?: FilterChip[];
  trailing?: ReactNode;
  onSubmit?: () => void;
}

/**
 * FilterBar -- search input + optional filter chip cluster + optional
 * trailing slot (e.g. sort picker). Chips carry aria-pressed. Search
 * input is a semantic <input type="search"> with aria-label.
 *
 * Design Controls: DI-LEO-AI-142, DO-LEO-AI-139, VT-LEO-AI-141.
 */

function handleSubmit(
  event: FormEvent<HTMLFormElement>,
  onSubmit?: () => void,
): void {
  event.preventDefault();
  if (onSubmit) onSubmit();
}

export function FilterBar({
  search,
  onSearchChange,
  searchPlaceholder = "Search",
  "aria-label": ariaLabel = "Filters",
  chips,
  trailing,
  onSubmit,
}: FilterBarProps) {
  const { reducedMotion } = useMotion();
  return (
    <form
      role="search"
      aria-label={ariaLabel}
      data-testid="filter-bar"
      onSubmit={(e) => handleSubmit(e, onSubmit)}
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: 12,
        fontFamily: typography.fontFamily.body,
      }}
    >
      <label
        style={{
          position: "relative",
          flex: "1 1 320px",
          maxWidth: 520,
          display: "inline-flex",
          alignItems: "center",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            left: 12,
            color: color.text.caption,
            pointerEvents: "none",
            fontSize: 14,
          }}
        >
          {"\u229E"}
        </span>
        <input
          type="search"
          value={search}
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            onSearchChange(e.target.value)
          }
          placeholder={searchPlaceholder}
          aria-label="Search"
          data-testid="filter-bar-search"
          style={{
            flex: 1,
            font: "inherit",
            fontFamily: typography.fontFamily.body,
            fontSize: 14,
            height: 40,
            padding: "0 14px 0 32px",
            borderRadius: radius.md,
            border: "1px solid " + color.text.secondary,
            background: color.surface.raised,
            boxShadow: elevation.card,
            color: color.text.primary,
            outline: "none",
            transition: "box-shadow 120ms ease-out, border-color 120ms ease-out",
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = color.focus.ring;
            e.currentTarget.style.boxShadow =
              elevation.card + ", 0 0 0 3px " + color.focus.ringAlpha;
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = color.text.secondary;
            e.currentTarget.style.boxShadow = elevation.card;
          }}
        />
      </label>

      {chips && chips.length > 0 ? (
        <div
          role="group"
          aria-label="Filter chips"
          data-testid="filter-bar-chips"
          style={{ display: "inline-flex", flexWrap: "wrap", gap: 6 }}
        >
          {chips.map((chip) => (
            <fm.button
              key={chip.id}
              type="button"
              aria-pressed={chip.active}
              data-testid={"filter-chip-" + chip.id}
              onClick={chip.onToggle}
              whileTap={tapScale(reducedMotion)}
              transition={springOrInstant(reducedMotion, springs.press)}
              style={{
                appearance: "none",
                border: "1px solid " +
                  (chip.active ? color.brand.primary : color.text.secondary),
                background: chip.active ? color.brand.primary : color.surface.raised,
                color: chip.active ? color.brand.onBrand : color.text.primary,
                fontFamily: typography.fontFamily.body,
                fontSize: 13,
                fontWeight: 500,
                padding: "6px 12px",
                borderRadius: radius.pill,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span>{chip.label}</span>
              {typeof chip.count === "number" ? (
                <span
                  style={{
                    fontVariantNumeric: "tabular-nums",
                    fontSize: 11,
                    opacity: 0.8,
                  }}
                >
                  {chip.count}
                </span>
              ) : null}
            </fm.button>
          ))}
        </div>
      ) : null}

      {trailing ? (
        <div style={{ marginLeft: "auto", display: "inline-flex", gap: 8 }}>
          {trailing}
        </div>
      ) : null}
    </form>
  );
}
