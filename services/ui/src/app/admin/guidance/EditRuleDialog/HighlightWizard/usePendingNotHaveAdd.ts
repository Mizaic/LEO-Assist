/**
 * Opens concept search on a newly created NOT group after the next tree render.
 *
 * Atlas trace:
 *   DO: DO-4EA3C153
 *   DI: DI-0F0B27D3, DI-42246DA7
 *   Risks: R-4E4F22EF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4EA3C153")
 */

import { useEffect, useState } from "react";

import type { EditableLogicNode, NodeUpdate } from "../types";
import { beginShouldNotHaveAdd, findDirectNotGroup } from "./shouldNotHave";
import { findNodeById } from "./wizardMapping";

type RequestAdd = (
  parentNodeId: string,
  anchor?: HTMLElement | null,
  initialQuery?: string,
  multiPick?: boolean,
) => void;

export function usePendingNotHaveAdd(
  tree: EditableLogicNode,
  onRequestAdd: RequestAdd,
): {
  start: (
    parentNodeId: string,
    onUpdate: (update: NodeUpdate) => void,
    anchor?: HTMLElement,
  ) => void;
} {
  const [pending, setPending] = useState<{
    parentId: string;
    anchor?: HTMLElement;
  } | null>(null);

  useEffect(() => {
    if (!pending) return;
    const parent = findNodeById(tree, pending.parentId);
    const notGroup = parent ? findDirectNotGroup(parent) : null;
    if (!notGroup) return;
    onRequestAdd(notGroup.node_id, pending.anchor, undefined, true);
    setPending(null);
  }, [tree, pending, onRequestAdd]);

  function start(
    parentNodeId: string,
    onUpdate: (update: NodeUpdate) => void,
    anchor?: HTMLElement,
  ) {
    beginShouldNotHaveAdd({
      parent: findNodeById(tree, parentNodeId),
      onUpdate,
      onRequestAdd,
      markPending: () => setPending({ parentId: parentNodeId, anchor }),
      anchor,
    });
  }

  return { start };
}
