/**
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-64CA7740
 */
import { Suspense } from "react";
import TemplateList from "@/components/audit-template-builder/TemplateList";

export default function AuditTemplatesPage() {
  return (
    <Suspense>
      <TemplateList />
    </Suspense>
  );
}
