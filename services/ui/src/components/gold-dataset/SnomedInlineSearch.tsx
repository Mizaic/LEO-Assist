import TermSearch from "@/components/TermSearch";
import type { TermSearchResult } from "@/lib/types";

interface Props {
  entityText: string;
  entityLabel: string;
  hasExistingCode: boolean;
  onSelect: (
    result: TermSearchResult,
    alsoFixSurfaceForm: boolean,
    addToSubdomains?: string[],
  ) => void;
  onClose: () => void;
}

function normaliseLookupTag(raw: string): string | null {
  const tag = String(raw ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s/-]+/g, "_");
  if (!tag) return null;
  if (tag === "observable") return "observable_entity";
  if (tag === "observation") return "observable_entity";
  return tag;
}

export default function SnomedInlineSearch({
  entityText,
  entityLabel,
  hasExistingCode,
  onSelect,
  onClose,
}: Props) {
  const hintTag = normaliseLookupTag(entityLabel);
  const typeLabel = entityLabel ? entityLabel.replace(/_/g, " ") : null;
  return (
    <TermSearch
      initialQuery={entityText}
      hintTags={hintTag ? [hintTag] : undefined}
      entityText={entityText}
      entityLabel={entityLabel}
      title={hasExistingCode ? "Fix SNOMED code" : "Find SNOMED code"}
      contextLabel={typeLabel ? `"${entityText}" - ${typeLabel}` : `"${entityText}"`}
      preventAutoClose
      onSelect={(result) => void onSelect(result, true, [])}
      onClose={onClose}
      onCorrection={() => {}}
    />
  );
}
