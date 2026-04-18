"use client";

import dynamic from "next/dynamic";

const SbarPlayground = dynamic(() => import("./SbarPlayground"), {
  ssr: false,
});

export default function AiSummarisationPage() {
  return <SbarPlayground />;
}
