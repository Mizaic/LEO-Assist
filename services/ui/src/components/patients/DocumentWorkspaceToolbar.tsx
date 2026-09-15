/**
 * Search, type, and specialty filters for the EPR document workspace.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import { FilterBar, color, type FilterChip } from "@leo/design-system";
import {
  TYPE_FILTER_OPTIONS,
  type DocumentTypeFilter,
} from "./documentListFilters";

interface FolderOption {
  label: string;
  count: number;
}

interface Props {
  search: string;
  onSearchChange: (value: string) => void;
  typeFilter: DocumentTypeFilter;
  onTypeFilter: (id: DocumentTypeFilter) => void;
  folderFilter: string | null;
  onFolderFilter: (label: string | null) => void;
  folderOptions: FolderOption[];
  canAdd: boolean;
  onAdd: () => void;
}

export function DocumentWorkspaceToolbar({
  search,
  onSearchChange,
  typeFilter,
  onTypeFilter,
  folderFilter,
  onFolderFilter,
  folderOptions,
  canAdd,
  onAdd,
}: Props) {
  const typeChips: FilterChip[] = TYPE_FILTER_OPTIONS.map((opt) => ({
    id: opt.id,
    label: opt.label,
    active: typeFilter === opt.id,
    onToggle: () => onTypeFilter(opt.id),
  }));

  return (
    <Stack spacing={1}>
      <FilterBar
        search={search}
        onSearchChange={onSearchChange}
        searchPlaceholder="Search documents"
        aria-label="Search documents"
        chips={typeChips}
        trailing={
          canAdd ? (
            <Button
              size="small"
              variant="contained"
              startIcon={<AddIcon />}
              onClick={onAdd}
              data-testid="add-document-button"
              sx={{
                textTransform: "none",
                fontWeight: 700,
                minHeight: 36,
                "&:active": { transform: "scale(0.97)" },
              }}
            >
              Add document
            </Button>
          ) : null
        }
      />
      {folderOptions.length > 0 && (
        <Stack spacing={0.5}>
          <Typography
            variant="caption"
            fontWeight={700}
            sx={{ color: color.text.caption }}
          >
            Specialty
          </Typography>
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            <Chip
              label="All specialties"
              size="small"
              onClick={() => onFolderFilter(null)}
              variant={folderFilter === null ? "filled" : "outlined"}
              color={folderFilter === null ? "primary" : "default"}
              sx={{ height: 28 }}
            />
            {folderOptions.map((opt) => (
              <Chip
                key={opt.label}
                label={`${opt.label} (${opt.count})`}
                size="small"
                onClick={() =>
                  onFolderFilter(folderFilter === opt.label ? null : opt.label)
                }
                variant={folderFilter === opt.label ? "filled" : "outlined"}
                color={folderFilter === opt.label ? "primary" : "default"}
                sx={{ height: 28 }}
              />
            ))}
          </Stack>
        </Stack>
      )}
    </Stack>
  );
}
