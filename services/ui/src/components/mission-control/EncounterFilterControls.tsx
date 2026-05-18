"use client";

import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";

interface Props {
  codedOnly: boolean;
  linkedOnly: boolean;
  timelineLabel: string | null;
  searchTerms: string[];
  inputDraft: string;
  anyExpanded: boolean;
  anyCollapsed: boolean;
  onCodedOnlyChange: (value: boolean) => void;
  onLinkedOnlyChange: (value: boolean) => void;
  onClearTimeline: () => void;
  onSearchTermsChange: (value: string[]) => void;
  onInputDraftChange: (value: string) => void;
  onClearFilters: () => void;
  onCollapseAll: () => void;
  onExpandAll: () => void;
}

export default function EncounterFilterControls({
  codedOnly,
  linkedOnly,
  timelineLabel,
  searchTerms,
  inputDraft,
  anyExpanded,
  anyCollapsed,
  onCodedOnlyChange,
  onLinkedOnlyChange,
  onClearTimeline,
  onSearchTermsChange,
  onInputDraftChange,
  onClearFilters,
  onCollapseAll,
  onExpandAll,
}: Props) {
  const hasFilters = codedOnly || linkedOnly || Boolean(timelineLabel) || searchTerms.length > 0;

  return (
    <Box
      sx={{
        position: "sticky",
        top: 0,
        zIndex: 2,
        display: "flex",
        flexDirection: "column",
        gap: 1,
        py: 1,
        bgcolor: "background.paper",
        borderBottom: "1px solid",
        borderColor: "divider",
      }}
    >
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
        <Chip
          clickable
          color={codedOnly ? "error" : "default"}
          variant={codedOnly ? "filled" : "outlined"}
          label="Coded only"
          aria-pressed={codedOnly}
          onClick={() => onCodedOnlyChange(!codedOnly)}
        />
        <Chip
          clickable
          color={linkedOnly ? "error" : "default"}
          variant={linkedOnly ? "filled" : "outlined"}
          label="Linked only"
          aria-pressed={linkedOnly}
          onClick={() => onLinkedOnlyChange(!linkedOnly)}
        />
        {timelineLabel && (
          <Chip
            clickable
            color="error"
            label={`Timeline: ${timelineLabel}`}
            aria-pressed
            onDelete={onClearTimeline}
            onClick={onClearTimeline}
          />
        )}
        {hasFilters && (
          <Button size="small" variant="text" color="error" onClick={onClearFilters}>
            Clear filters
          </Button>
        )}
        {anyExpanded && (
          <Button size="small" variant="text" sx={{ ml: "auto" }} onClick={onCollapseAll}>
            Collapse all
          </Button>
        )}
        {anyCollapsed && (
          <Button
            size="small"
            variant="text"
            sx={{ ml: anyExpanded ? 0 : "auto" }}
            onClick={onExpandAll}
          >
            Expand all
          </Button>
        )}
      </Box>
      <Autocomplete
        multiple
        freeSolo
        options={[]}
        value={searchTerms}
        inputValue={inputDraft}
        onChange={(_, value) => onSearchTermsChange(value as string[])}
        onInputChange={(_, value, reason) => {
          if (reason !== "input") {
            onInputDraftChange(value);
            return;
          }
          if (value.endsWith(",")) {
            const term = value.slice(0, -1).trim();
            if (term) onSearchTermsChange([...searchTerms, term]);
            onInputDraftChange("");
          } else {
            onInputDraftChange(value);
          }
        }}
        renderTags={(value, getTagProps) =>
          value.map((option, index) => {
            const { key, ...tagProps } = getTagProps({ index });
            return <Chip key={key} label={option} size="small" color="error" {...tagProps} />;
          })
        }
        renderInput={(params) => (
          <TextField {...params} size="small" label="Search text in shown encounters" />
        )}
      />
    </Box>
  );
}
