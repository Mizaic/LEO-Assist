"use client";

import {
  useCallback,
  useEffect,
  useId,
  useState,
  type ReactNode,
} from "react";

import { useMotion } from "../motion";
import type { Role } from "../roles/types";

export interface IntroCopyBlock {
  title: string;
  lede: string;
  how?: string;
  what?: string;
}

export type IntroRoleCopy = Partial<Record<Role, IntroCopyBlock>> & {
  default: IntroCopyBlock;
};

export interface IntroCardProps {
  screenId: string;
  copy: IntroRoleCopy;
  role?: Role | null;
  children?: ReactNode;
}

// localStorage key prefix. Collapse state is per screenId so each page is
// independent. See DI-LEO-AI-136 / VT-LEO-AI-132 TC-004.
const STORAGE_PREFIX = "leo-introcard-";

function resolveBlock(
  copy: IntroRoleCopy,
  role: Role | null | undefined,
): IntroCopyBlock {
  if (role && copy[role]) return copy[role] as IntroCopyBlock;
  return copy.default;
}

function readPersistedCollapse(storageKey: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(storageKey) === "collapsed";
  } catch {
    return false;
  }
}

function persistCollapse(storageKey: string, collapsed: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      storageKey,
      collapsed ? "collapsed" : "expanded",
    );
  } catch {
    /* ignore quota errors */
  }
}

export function IntroCard({
  screenId,
  copy,
  role,
  children,
}: IntroCardProps) {
  const { reducedMotion } = useMotion();
  const bodyId = useId();
  const storageKey = STORAGE_PREFIX + screenId;
  const [collapsed, setCollapsed] = useState(false);
  const block = resolveBlock(copy, role);

  useEffect(() => {
    setCollapsed(readPersistedCollapse(storageKey));
  }, [storageKey]);

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      persistCollapse(storageKey, next);
      return next;
    });
  }, [storageKey]);

  const transitionMs = reducedMotion ? 0 : 180;

  return (
    <section
      aria-labelledby={screenId + "-intro-title"}
      data-testid={"intro-card-" + screenId}
      style={{
        background: "var(--mui-palette-background-paper, #ffffff)",
        border: "1px solid rgba(15, 23, 42, 0.08)",
        borderRadius: 12,
        padding: "16px 20px",
        marginBottom: 16,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <h2
          id={screenId + "-intro-title"}
          style={{ margin: 0, fontSize: 18, fontWeight: 600 }}
        >
          {block.title}
        </h2>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          style={{
            border: "1px solid rgba(15, 23, 42, 0.14)",
            background: "transparent",
            padding: "4px 10px",
            borderRadius: 999,
            cursor: "pointer",
            fontSize: 12,
          }}
        >
          {collapsed ? "Show details" : "Hide details"}
        </button>
      </div>
      <div
        id={bodyId}
        hidden={collapsed}
        style={{
          marginTop: collapsed ? 0 : 10,
          transition: "margin " + transitionMs + "ms ease-out",
        }}
      >
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5 }}>{block.lede}</p>
        {block.how ? (
          <p
            style={{ margin: "8px 0 0 0", fontSize: 14, lineHeight: 1.5 }}
          >
            <strong>How: </strong>
            {block.how}
          </p>
        ) : null}
        {block.what ? (
          <p
            style={{ margin: "4px 0 0 0", fontSize: 14, lineHeight: 1.5 }}
          >
            <strong>What happens next: </strong>
            {block.what}
          </p>
        ) : null}
        {children}
      </div>
    </section>
  );
}
