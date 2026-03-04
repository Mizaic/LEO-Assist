"use client";

import { use, Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import { ReportEditor } from "@/components/editor/ReportEditor";

interface PageProps {
  params: Promise<{ id: string }>;
}

function EditorContent({ params }: PageProps) {
  const { id } = use(params);
  return <ReportEditor reportId={id} />;
}

export default function ReportEditorPage(props: PageProps) {
  return (
    <Suspense fallback={<Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}><CircularProgress aria-label="Loading" /></Box>}>
      <EditorContent {...props} />
    </Suspense>
  );
}
