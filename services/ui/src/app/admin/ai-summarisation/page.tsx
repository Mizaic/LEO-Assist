/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import dynamic from "next/dynamic";

const SbarPlayground = dynamic(() => import("./SbarPlayground"), {
  ssr: false,
});

export default function AiSummarisationPage() {
  return <SbarPlayground />;
}
