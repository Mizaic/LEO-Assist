"use client";

import { use, Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import { MeasureEditor } from "@/components/measures/MeasureEditor";

interface PageProps {
  params: Promise<{ id: string }>;
}

function EditorContent({ params }: PageProps) {
  const { id } = use(params);
  const measureId = id === "new" ? undefined : id;
  return <MeasureEditor measureId={measureId} />;
}

export default function MeasureEditorPage(props: PageProps) {
  return (
    <Suspense fallback={<Box sx={{ display: "flex", justifyContent: "center", p: 6 }}><CircularProgress aria-label="Loading" /></Box>}>
      <EditorContent {...props} />
    </Suspense>
  );
}
