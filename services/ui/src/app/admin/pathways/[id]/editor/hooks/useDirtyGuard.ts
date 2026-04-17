"use client";

// -- useDirtyGuard ------------------------------------------------------------
// Pathway editor "are my changes saved?" tracking.
//
// Why this exists (Phase 6b-iv): the original orchestrator silently fired a
// background save on every wizard "Next" click, persisted on every keystroke
// via a useEffect, and gave the user no clear signal that work was unsaved.
// Closing a tab mid-edit lost work without warning.
//
// This hook centralises three concerns:
//   1. Computing a stable signature from the parts of the pathway that get
//      persisted (plan metadata, trigger, nodes, edges, per-node configs).
//   2. Comparing the live signature against the last-saved baseline so the
//      Save bar can show "Unsaved changes" exactly when work is dirty.
//   3. Installing a beforeunload listener while dirty, so closing the tab
//      surfaces the browser's native "you have unsaved work" dialog.
//
// The hook is intentionally tiny and pure: callers own state, callers tell
// us when a save succeeds (`markSaved()`), callers consume `dirty`.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Edge, Node } from "@xyflow/react";

import type { ActionConfig } from "@/components/pathway/config/types";

export interface PathwaySignatureInputs {
  planName: string;
  planDescription: string;
  planStatus: string;
  triggerEvent: string;
  nodes: Node[];
  edges: Edge[];
  nodeConfigs: Record<string, ActionConfig>;
}

export interface UseDirtyGuardReturn {
  dirty: boolean;
  markSaved: () => void;
  markBaseline: () => void;
}

function nodeFingerprint(node: Node): unknown {
  const data = (node.data ?? {}) as Record<string, unknown>;
  // Strip non-serialisable fields (callbacks, runtime props) so the signature
  // is stable across re-renders. onConfigure is a fresh closure every render.
  const {
    onConfigure: _onConfigure,
    onDelete: _onDelete,
    config: _config,
    ...persistable
  } = data;
  void _onConfigure;
  void _onDelete;
  void _config;
  return {
    id: node.id,
    type: node.type ?? "",
    position: node.position
      ? { x: Math.round(node.position.x), y: Math.round(node.position.y) }
      : null,
    data: persistable,
  };
}

function edgeFingerprint(edge: Edge): unknown {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle ?? null,
    targetHandle: edge.targetHandle ?? null,
  };
}

export function computePathwaySignature(
  inputs: PathwaySignatureInputs,
): string {
  const payload = {
    planName: inputs.planName,
    planDescription: inputs.planDescription,
    planStatus: inputs.planStatus,
    triggerEvent: inputs.triggerEvent,
    nodes: inputs.nodes.map(nodeFingerprint),
    edges: inputs.edges.map(edgeFingerprint),
    nodeConfigs: inputs.nodeConfigs,
  };
  return JSON.stringify(payload);
}

export function useDirtyGuard(
  inputs: PathwaySignatureInputs,
  options: { ready: boolean },
): UseDirtyGuardReturn {
  const baselineRef = useRef<string | null>(null);
  const [signature, setSignature] = useState<string>(() =>
    computePathwaySignature(inputs),
  );

  const liveSignature = useMemo(
    () => computePathwaySignature(inputs),
    [inputs],
  );

  useEffect(() => {
    setSignature(liveSignature);
  }, [liveSignature]);

  // First time the pathway becomes "ready" (loaded from server, or freshly
  // created), capture the baseline so dirty starts as false rather than
  // comparing against an empty initial render.
  useEffect(() => {
    if (options.ready && baselineRef.current === null) {
      baselineRef.current = liveSignature;
    }
  }, [options.ready, liveSignature]);

  const dirty =
    baselineRef.current !== null && baselineRef.current !== signature;

  const markSaved = useCallback(() => {
    baselineRef.current = liveSignature;
    setSignature(liveSignature);
  }, [liveSignature]);

  const markBaseline = useCallback(() => {
    baselineRef.current = liveSignature;
  }, [liveSignature]);

  // Native "you have unsaved changes" prompt while the user is dirty.
  // Modern browsers ignore the message string and show their own copy, but
  // assigning returnValue is what triggers the prompt.
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  return { dirty, markSaved, markBaseline };
}
