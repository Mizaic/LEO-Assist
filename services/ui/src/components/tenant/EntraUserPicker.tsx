"use client";

import { useEffect, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { searchEntraUsers, type EntraUser } from "@/lib/api/admin";

interface Props {
  onSelect: (user: { email: string; name: string }) => void;
  selectedEmail?: string;
  helperText?: string;
}

export default function EntraUserPicker({ onSelect, selectedEmail, helperText }: Props) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<EntraUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setOptions([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const t = setTimeout(async () => {
      try {
        const res = await searchEntraUsers(trimmed, 25);
        if (!cancelled) setOptions(res.users || []);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Search failed");
          setOptions([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query]);

  return (
    <Autocomplete
      options={options}
      filterOptions={(x) => x}
      getOptionLabel={(o) => o.displayName || o.mail || o.userPrincipalName || ""}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      loading={loading}
      onInputChange={(_, value) => setQuery(value)}
      onChange={(_, value) => {
        if (!value) return;
        const email = (value.mail || value.userPrincipalName || "").toLowerCase();
        if (!email) {
          setError("This Entra user has no mail or userPrincipalName.");
          return;
        }
        onSelect({ email, name: value.displayName || email });
      }}
      noOptionsText={
        query.trim().length < 2
          ? "Type at least 2 characters to search Entra"
          : "No matches"
      }
      renderOption={(props, option) => {
        const { key, ...rest } = props as { key: string };
        return (
          <Box component="li" key={key} {...rest}>
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {option.displayName}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {option.mail || option.userPrincipalName || option.id}
              </Typography>
            </Box>
          </Box>
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label="Search Entra by name or email"
          size="small"
          error={!!error}
          helperText={error || helperText || (selectedEmail ? `Selected: ${selectedEmail}` : "")}
          slotProps={{
            input: {
              ...params.InputProps,
              endAdornment: (
                <>
                  {loading ? <CircularProgress color="inherit" size={16} /> : null}
                  {params.InputProps.endAdornment}
                </>
              ),
            },
          }}
        />
      )}
    />
  );
}
