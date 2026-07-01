/**
 * Phase 7 -- live-render tests for the confirm dialog wiring.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *
 * Walks ``useConfirmEdits`` through three contracts:
 *
 *   1. A non-destructive update (e.g. add_concept) is forwarded to
 *      the underlying onUpdate without showing any dialog.
 *   2. A destructive root-kind change (AND -> OR) opens the kind
 *      confirm dialog with a before/after sentence and forwards the
 *      update only after the reviewer clicks "Yes, change it".
 *   3. An OBSERVATION operator flip (< -> >) opens the flip confirm
 *      dialog and Cancel discards the update.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { useConfirmEdits } from "../useConfirmEdits";
import { assignNodeIds } from "../treeOps";
import type {
  EditableLogicNode,
  EditableObservationPayload,
  NodeUpdate,
} from "../types";
import { CONFIRM_KIND_CHANGE, CONFIRM_OBSERVATION_FLIP } from "../copy";

function tree(seed: Parameters<typeof assignNodeIds>[0]): EditableLogicNode {
  return assignNodeIds(seed);
}

function obs(
  overrides: Partial<EditableObservationPayload> = {},
): EditableObservationPayload {
  return {
    observable_id: "365632008",
    observable_term: "Platelet count",
    operator: ">=",
    value: 400,
    unit: "10*9/L",
    within_days: 365,
    ...overrides,
  };
}

interface HarnessProps {
  initialTree: EditableLogicNode;
  update: NodeUpdate;
  onForwarded: (update: NodeUpdate) => void;
}

function Harness({ initialTree, update, onForwarded }: HarnessProps) {
  const { wrappedOnUpdate, confirmDialogs } = useConfirmEdits({
    tree: initialTree,
    onUpdate: onForwarded,
  });
  return (
    <>
      <button
        type="button"
        onClick={() => wrappedOnUpdate(update)}
        aria-label="trigger update"
      >
        trigger
      </button>
      {confirmDialogs}
    </>
  );
}

describe("Phase 7 -- useConfirmEdits", () => {
  it("forwards non-destructive updates without showing a dialog", async () => {
    const user = userEvent.setup();
    const root = tree({ kind: "AND", children: [] });
    const onForwarded = jest.fn();
    render(
      <Harness
        initialTree={root}
        update={{
          kind: "add_concept",
          parentNodeId: root.node_id,
          conceptId: "12345",
          term: "Cough",
        }}
        onForwarded={onForwarded}
      />,
    );
    await user.click(screen.getByLabelText(/trigger update/i));
    expect(onForwarded).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByText(CONFIRM_KIND_CHANGE.title),
    ).not.toBeInTheDocument();
  });

  it("opens the kind-change confirm and forwards on Yes", async () => {
    const user = userEvent.setup();
    const root = tree({ kind: "AND", children: [] });
    const onForwarded = jest.fn();
    render(
      <Harness
        initialTree={root}
        update={{
          kind: "change_kind",
          nodeId: root.node_id,
          newKind: "OR",
        }}
        onForwarded={onForwarded}
      />,
    );
    await user.click(screen.getByLabelText(/trigger update/i));
    expect(screen.getByText(CONFIRM_KIND_CHANGE.title)).toBeInTheDocument();
    expect(onForwarded).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", { name: CONFIRM_KIND_CHANGE.confirmLabel }),
    );
    expect(onForwarded).toHaveBeenCalledTimes(1);
    expect(onForwarded.mock.calls[0][0].newKind).toBe("OR");
  });

  it("opens the kind-change confirm and discards on Cancel", async () => {
    const user = userEvent.setup();
    const root = tree({ kind: "AND", children: [] });
    const onForwarded = jest.fn();
    render(
      <Harness
        initialTree={root}
        update={{
          kind: "change_kind",
          nodeId: root.node_id,
          newKind: "NOT",
        }}
        onForwarded={onForwarded}
      />,
    );
    await user.click(screen.getByLabelText(/trigger update/i));
    await user.click(
      screen.getByRole("button", { name: CONFIRM_KIND_CHANGE.cancelLabel }),
    );
    expect(onForwarded).not.toHaveBeenCalled();
  });

  it("does not confirm for non-root or non-destructive kind changes", async () => {
    const user = userEvent.setup();
    const root = tree({
      kind: "AND",
      children: [{ kind: "OR", children: [] }],
    });
    const childId = root.children![0].node_id;
    const onForwarded = jest.fn();
    render(
      <Harness
        initialTree={root}
        update={{
          kind: "change_kind",
          nodeId: childId,
          newKind: "AND",
        }}
        onForwarded={onForwarded}
      />,
    );
    await user.click(screen.getByLabelText(/trigger update/i));
    expect(onForwarded).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByText(CONFIRM_KIND_CHANGE.title),
    ).not.toBeInTheDocument();
  });

  it("opens the observation-flip confirm on a < -> > switch", async () => {
    const user = userEvent.setup();
    const root = tree({
      kind: "AND",
      children: [
        { kind: "OBSERVATION", observation: obs({ operator: "<" }) },
      ],
    });
    const leafId = root.children![0].node_id;
    const onForwarded = jest.fn();
    render(
      <Harness
        initialTree={root}
        update={{
          kind: "set_observation",
          nodeId: leafId,
          observation: obs({ operator: ">" }),
        }}
        onForwarded={onForwarded}
      />,
    );
    await user.click(screen.getByLabelText(/trigger update/i));
    expect(
      screen.getByText(CONFIRM_OBSERVATION_FLIP.title),
    ).toBeInTheDocument();
    expect(onForwarded).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", {
        name: CONFIRM_OBSERVATION_FLIP.confirmLabel,
      }),
    );
    expect(onForwarded).toHaveBeenCalledTimes(1);
  });

  it("does not confirm a same-side observation operator change", async () => {
    const user = userEvent.setup();
    const root = tree({
      kind: "AND",
      children: [
        { kind: "OBSERVATION", observation: obs({ operator: "<" }) },
      ],
    });
    const leafId = root.children![0].node_id;
    const onForwarded = jest.fn();
    render(
      <Harness
        initialTree={root}
        update={{
          kind: "set_observation",
          nodeId: leafId,
          observation: obs({ operator: "<=" }),
        }}
        onForwarded={onForwarded}
      />,
    );
    await user.click(screen.getByLabelText(/trigger update/i));
    expect(onForwarded).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByText(CONFIRM_OBSERVATION_FLIP.title),
    ).not.toBeInTheDocument();
  });
});
