/**
 * Organisation and service pickers for Teach this form.
 *
 * Reuses existing /api/form-schemas/scope catalog and graph IDs.
 * Atlas trace: UN-3B25A20E
 */
"use client";

import Autocomplete from "@mui/material/Autocomplete";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useEffect, useState } from "react";

type NamedId = { id: string; name: string };

interface Props {
  organizationId: string;
  serviceId: string;
  onOrganization: (id: string) => void;
  onService: (id: string) => void;
}

const FETCH_HDRS = { "X-Requested-With": "XMLHttpRequest" };

export function FormSchemaScopeFields({
  organizationId,
  serviceId,
  onOrganization,
  onService,
}: Props) {
  const [orgs, setOrgs] = useState<NamedId[]>([]);
  const [services, setServices] = useState<NamedId[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/form-schemas/scope/organizations", {
          credentials: "include",
          headers: FETCH_HDRS,
        });
        if (!res.ok) return;
        const payload = (await res.json()) as { organizations?: NamedId[] };
        if (!cancelled) setOrgs(payload.organizations ?? []);
      } catch {
        // Keep empty pickers when the catalog is unavailable.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!organizationId) {
      setServices([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(
          `/api/form-schemas/scope/organizations/${encodeURIComponent(organizationId)}/services`,
          { credentials: "include", headers: FETCH_HDRS },
        );
        if (!res.ok) return;
        const payload = (await res.json()) as { services?: NamedId[] };
        if (!cancelled) setServices(payload.services ?? []);
      } catch {
        if (!cancelled) setServices([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1 }}>
      <ScopePicker
        label="Organisation"
        options={orgs}
        value={organizationId}
        onChange={(id) => {
          onOrganization(id);
          onService("");
        }}
      />
      <ScopePicker
        label="Service"
        options={services}
        value={serviceId}
        onChange={onService}
        disabled={!organizationId}
      />
    </Stack>
  );
}

function ScopePicker({
  label,
  options,
  value,
  onChange,
  disabled,
}: {
  label: string;
  options: NamedId[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  const selected = options.find((item) => item.id === value) ?? null;
  return (
    <Autocomplete
      size="small"
      fullWidth
      disabled={disabled}
      options={options}
      value={selected}
      getOptionLabel={(item) => item.name || item.id}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onChange={(_event, next) => onChange(next?.id ?? "")}
      renderInput={(params) => (
        <TextField {...params} label={label} inputProps={{ ...params.inputProps, "aria-label": label }} />
      )}
    />
  );
}
