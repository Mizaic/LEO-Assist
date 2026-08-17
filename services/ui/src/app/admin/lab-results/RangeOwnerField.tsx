/**
 * Atlas trace:
 *   DI: DI-6EFB48AB
 */
"use client";

import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";

import { spanTwo } from "./labConfigForm";
import {
  PLATFORM_OWNER,
  filterRangeOrgs,
  orgSearchLabel,
  type RangeOrgOption,
} from "./rangeDraft";

export function RangeOwnerField({
  orgId,
  orgs,
  onChange,
}: {
  orgId: string;
  orgs: RangeOrgOption[];
  onChange: (orgId: string) => void;
}) {
  const options = [PLATFORM_OWNER, ...orgs];
  const value = options.find((row) => row.id === orgId) || PLATFORM_OWNER;
  return (
    <Autocomplete
      sx={spanTwo()}
      options={options}
      value={value}
      filterOptions={filterRangeOrgs}
      getOptionLabel={orgSearchLabel}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onChange={(_, next) => onChange(next?.id || "")}
      noOptionsText="Type a name or ODS code"
      renderInput={(params) => (
        <TextField
          {...params}
          size="small"
          label="Owner"
          helperText="Type a name or ODS code to set an organisation overlay"
        />
      )}
    />
  );
}
