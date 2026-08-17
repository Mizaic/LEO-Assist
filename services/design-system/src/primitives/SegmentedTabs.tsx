/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BCA9B190")
 */
"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { motion as fm } from "framer-motion";

import { useMotion } from "../motion";
import { springOrInstant, springs, tapScale } from "../motion/springs";
import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";
import { useSegmentedPill } from "./useSegmentedPill";

export interface SegmentedTab {
  id: string;
  label: string;
  count?: number;
  icon?: ReactNode;
}

export interface SegmentedTabsProps {
  tabs: SegmentedTab[];
  value: string;
  onChange: (id: string) => void;
  "aria-label": string;
  dense?: boolean;
}

function resolveIndex(tabs: SegmentedTab[], id: string): number {
  const idx = tabs.findIndex((t) => t.id === id);
  return idx < 0 ? 0 : idx;
}

function tabButtonStyle(
  selected: boolean,
  dense: boolean,
  paddingX: number,
  height: number,
): React.CSSProperties {
  return {
    appearance: "none",
    border: "none",
    background: "transparent",
    color: color.text.primary,
    fontSize: dense ? 13 : 14,
    fontWeight: selected ? 700 : 600,
    padding: "0 " + paddingX + "px",
    height,
    borderRadius: radius.pill,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    position: "relative",
    zIndex: 1,
  };
}

/**
 * SegmentedTabs -- pill-style segmented control. A spring-driven
 * highlight tracks the live button box so a mid-flight change is
 * interruptible. Fully keyboard-accessible (Left/Right/Home/End).
 *
 * Design Controls: DI-LEO-AI-142, DO-LEO-AI-139, VT-LEO-AI-141.
 */
export function SegmentedTabs({
  tabs,
  value,
  onChange,
  "aria-label": ariaLabel,
  dense = false,
}: SegmentedTabsProps) {
  const { reducedMotion } = useMotion();
  const activeIdx = resolveIndex(tabs, value);
  const [focusIdx, setFocusIdx] = useState<number>(activeIdx);
  const listRef = useRef<HTMLDivElement | null>(null);
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const pill = useSegmentedPill(listRef, refs, activeIdx);

  useEffect(() => {
    setFocusIdx(activeIdx);
  }, [activeIdx]);

  const move = useCallback(
    (next: number) => {
      const bounded = (next + tabs.length) % tabs.length;
      setFocusIdx(bounded);
      const node = refs.current[bounded];
      if (node) node.focus();
    },
    [tabs.length],
  );

  const onKey = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>) => {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        move(focusIdx + 1);
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        move(focusIdx - 1);
        return;
      }
      if (event.key === "Home") {
        event.preventDefault();
        move(0);
        return;
      }
      if (event.key === "End") {
        event.preventDefault();
        move(tabs.length - 1);
      }
    },
    [focusIdx, move, tabs.length],
  );

  const height = dense ? 32 : 40;
  const paddingX = dense ? 12 : 16;
  const shell = useMemo<React.CSSProperties>(
    () => ({
      display: "inline-flex",
      alignItems: "center",
      gap: 2,
      background: color.surface.alt,
      border: "1px solid " + color.text.secondary,
      borderRadius: radius.pill,
      padding: 3,
      fontFamily: typography.fontFamily.body,
      position: "relative",
    }),
    [],
  );

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label={ariaLabel}
      data-testid="segmented-tabs"
      style={shell}
    >
      <fm.span
        aria-hidden="true"
        data-testid="segmented-tabs-pill"
        initial={false}
        animate={{
          x: pill.x,
          width: pill.width,
          opacity: pill.ready ? 1 : 0,
        }}
        transition={springOrInstant(reducedMotion, springs.ui)}
        style={{
          position: "absolute",
          top: 3,
          bottom: 3,
          left: 0,
          borderRadius: radius.pill,
          background: color.surface.raised,
          boxShadow: "0 1px 2px rgba(15, 23, 42, 0.08)",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />
      {tabs.map((tab, idx) => {
        const selected = tab.id === value;
        return (
          <fm.button
            key={tab.id}
            ref={(el) => {
              refs.current[idx] = el;
            }}
            role="tab"
            type="button"
            id={"segtab-" + tab.id}
            aria-selected={selected}
            tabIndex={focusIdx === idx ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={onKey}
            data-testid={"segmented-tab-" + tab.id}
            title={"Show " + tab.label}
            whileHover={
              selected || reducedMotion
                ? undefined
                : { backgroundColor: color.surface.raised }
            }
            whileTap={tapScale(reducedMotion)}
            transition={springOrInstant(reducedMotion, springs.press)}
            style={tabButtonStyle(selected, dense, paddingX, height)}
          >
            {tab.icon ?? null}
            <span>{tab.label}</span>
            {typeof tab.count === "number" ? (
              <span
                aria-label={tab.count + " items"}
                style={{
                  minWidth: 20,
                  padding: "0 6px",
                  borderRadius: radius.pill,
                  background: selected ? color.brand.primary : color.surface.divider,
                  color: selected ? color.brand.onBrand : color.text.secondary,
                  fontSize: 11,
                  fontWeight: 600,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {tab.count}
              </span>
            ) : null}
          </fm.button>
        );
      })}
    </div>
  );
}
