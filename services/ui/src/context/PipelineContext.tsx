"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import { usePipelineStream } from "@/hooks/usePipelineStream";
import type { PipelineRunResponse } from "@/lib/types";
import type { PipelineStreamParams, WorkerState } from "@/hooks/usePipelineStream";

export interface PipelineContextValue {
  running: boolean;
  status: string | null;
  live: PipelineRunResponse | null;
  result: PipelineRunResponse | null;
  error: string | null;
  workerStates: Record<number, WorkerState>;
  start: (params: PipelineStreamParams) => void;
  cancel: () => void;
  showModal: boolean;
  setShowModal: (show: boolean) => void;
}

const PipelineContext = createContext<PipelineContextValue | null>(null);

export function PipelineProvider({ children }: { children: ReactNode }) {
  const stream = usePipelineStream();
  const [showModal, setShowModal] = useState(false);

  const start = useCallback(
    (params: PipelineStreamParams) => {
      stream.start(params);
      setShowModal(true);
    },
    [stream.start]
  );

  const value: PipelineContextValue = {
    ...stream,
    start,
    showModal,
    setShowModal,
  };

  return (
    <PipelineContext.Provider value={value}>{children}</PipelineContext.Provider>
  );
}

export function usePipeline() {
  const ctx = useContext(PipelineContext);
  if (!ctx) {
    throw new Error("usePipeline must be used within PipelineProvider");
  }
  return ctx;
}
