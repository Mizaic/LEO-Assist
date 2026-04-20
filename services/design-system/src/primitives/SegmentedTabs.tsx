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

import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";
import { useMotion } from "../motion";

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

/**
 * SegmentedTabs -- pill-style segmented control. Fully keyboard-accessible
 * (Left/Right/Home/End). Uses tokens + framer-motion-style opacity
 * transition; honours reduced-motion.
 *
 * Design Controls: DI-LEO-AI-142, DO-LEO-AI-139, VT-LEO-AI-141.
 */

function resolveIndex(tabs: SegmentedTab[], id: string): number {
  const idx = tabs.findIndex((t) => t.id === id);
  return idx < 0 ? 0 : idx;
}

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
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

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

  const transition = reducedMotion ? "none" : "background 160ms ease-out, color 160ms ease-out";
  const height = dense ? 32 : 40;
  const paddingX = dense ? 12 : 16;

  const shell = useMemo<React.CSSProperties>(
    () => ({
      display: "inline-flex",
      alignItems: "center",
      gap: 2,
      background: color.surface.alt,
      border: "1px solid " + color.surface.divider,
      borderRadius: radius.pill,
      padding: 3,
      fontFamily: typography.fontFamily.body,
    }),
    [],
  );

  return (
    <div role="tablist" aria-label={ariaLabel} data-testid="segmented-tabs" style={shell}>
      {tabs.map((tab, idx) => {
        const selected = tab.id === value;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[idx] = el;
            }}
            role="tab"
            type="button"
            id={"segtab-" + tab.id}
            aria-selected={selected}
            aria-controls={"segpanel-" + tab.id}
            tabIndex={focusIdx === idx ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={onKey}
            data-testid={"segmented-tab-" + tab.id}
            style={{
              appearance: "none",
              border: "none",
              background: selected ? color.surface.raised : "transparent",
              color: selected ? color.text.primary : color.text.secondary,
              fontSize: dense ? 13 : 14,
              fontWeight: selected ? 600 : 500,
              padding: "0 " + paddingX + "px",
              height,
              borderRadius: radius.pill,
              cursor: "pointer",
              transition,
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              boxShadow: selected ? "0 1px 2px rgba(15, 23, 42, 0.08)" : "none",
            }}
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
          </button>
        );
      })}
    </div>
  );
}
