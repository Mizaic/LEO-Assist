/**
 * Phase 7 -- shared confirm-edits wrapper.
 *
 * Wraps a logic-tree ``onUpdate`` so that two destructive edit kinds
 * are intercepted and require explicit reviewer confirmation:
 *
 *   - ``change_kind`` on the root group node (AND <-> OR <-> NOT
 *     <-> AT_LEAST). Renders ``ConfirmKindChangeDialog`` with the
 *     before/after sentence rendered by ``treeToSentence``.
 *
 *   - ``set_observation`` on any OBSERVATION leaf where the new
 *     operator crosses the threshold direction (e.g. ``<`` -> ``>``).
 *     Renders ``ConfirmObservationFlipDialog`` with a one-line
 *     before/after of the leaf.
 *
 * The wrapper is intentionally hosted at the Step level so that
 * SentenceCanvas (primary surface) and LogicTreeEditor (Advanced
 * view) share the same confirm UX without duplicating wiring.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-061AD3D1
 *   DO: DO-1EE0BFAE
 *   VT: VT-EEF2D497
 */
"use client";

import * as React from "react";
import {
  ConfirmKindChangeDialog,
  ConfirmObservationFlipDialog,
} from "./ConfirmDialogs";
import { isDestructiveRootKindChange, isObservationOperatorFlip } from "./copy";
import { applyUpdate } from "./treeOps";
import type {
  EditableLogicNode,
  EditableObservationPayload,
  NodeUpdate,
} from "./types";

interface UseConfirmEditsArgs {
  /** Current root tree, needed for the before/after preview. */
  tree: EditableLogicNode | null;
  /** Underlying onUpdate to forward confirmed (or non-destructive) updates to. */
  onUpdate: (update: NodeUpdate) => void;
}

interface UseConfirmEditsResult {
  /** Drop-in replacement for the supplied onUpdate. */
  wrappedOnUpdate: (update: NodeUpdate) => void;
  /** Confirm dialogs to render somewhere inside the component tree. */
  confirmDialogs: React.ReactNode;
}

interface PendingKindChange {
  update: NodeUpdate & { kind: "change_kind" };
  beforeTree: EditableLogicNode;
  afterTree: EditableLogicNode;
}

interface PendingObsFlip {
  update: NodeUpdate & { kind: "set_observation" };
  before: EditableObservationPayload;
  after: EditableObservationPayload;
}

export function useConfirmEdits({
  tree,
  onUpdate,
}: UseConfirmEditsArgs): UseConfirmEditsResult {
  const [pendingKind, setPendingKind] =
    React.useState<PendingKindChange | null>(null);
  const [pendingObs, setPendingObs] = React.useState<PendingObsFlip | null>(
    null,
  );

  const wrappedOnUpdate = React.useCallback(
    (update: NodeUpdate) => {
      if (!tree) {
        onUpdate(update);
        return;
      }
      const kindChange = maybePendingKindChange(update, tree);
      if (kindChange) {
        setPendingKind(kindChange);
        return;
      }
      const obsFlip = maybePendingObsFlip(update, tree);
      if (obsFlip) {
        setPendingObs(obsFlip);
        return;
      }
      onUpdate(update);
    },
    [onUpdate, tree],
  );

  const confirmDialogs = (
    <>
      <ConfirmKindChangeDialog
        open={pendingKind !== null}
        before={pendingKind?.beforeTree ?? null}
        after={pendingKind?.afterTree ?? null}
        onCancel={() => setPendingKind(null)}
        onConfirm={() => {
          if (pendingKind) {
            onUpdate(pendingKind.update);
          }
          setPendingKind(null);
        }}
      />
      <ConfirmObservationFlipDialog
        open={pendingObs !== null}
        before={pendingObs?.before ?? null}
        after={pendingObs?.after ?? null}
        onCancel={() => setPendingObs(null)}
        onConfirm={() => {
          if (pendingObs) {
            onUpdate(pendingObs.update);
          }
          setPendingObs(null);
        }}
      />
    </>
  );

  return { wrappedOnUpdate, confirmDialogs };
}

function maybePendingKindChange(
  update: NodeUpdate,
  tree: EditableLogicNode,
): PendingKindChange | null {
  if (update.kind !== "change_kind") return null;
  if (update.nodeId !== tree.node_id) return null;
  if (!isDestructiveRootKindChange(tree.kind, update.newKind)) return null;
  const afterTree = applyUpdate(tree, update);
  return {
    update,
    beforeTree: tree,
    afterTree,
  };
}

function maybePendingObsFlip(
  update: NodeUpdate,
  tree: EditableLogicNode,
): PendingObsFlip | null {
  if (update.kind !== "set_observation") return null;
  const target = findNode(tree, update.nodeId);
  if (!target || target.kind !== "OBSERVATION" || !target.observation) {
    return null;
  }
  const before = target.observation;
  const after = update.observation;
  if (!isObservationOperatorFlip(before.operator, after.operator)) return null;
  return { update, before, after };
}

function findNode(
  node: EditableLogicNode,
  nodeId: string,
): EditableLogicNode | null {
  if (node.node_id === nodeId) return node;
  for (const child of node.children ?? []) {
    const hit = findNode(child, nodeId);
    if (hit) return hit;
  }
  return null;
}
