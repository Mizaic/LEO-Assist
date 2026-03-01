"use client";

import { use } from "react";
import { redirect } from "next/navigation";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ReportViewPage({ params }: PageProps) {
  const { id } = use(params);
  redirect(`/reports/${id}/edit`);
}
