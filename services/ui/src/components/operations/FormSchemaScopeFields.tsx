/**
 * Organisation and service pickers for Teach this form.
 *
 * Reuses the tenant-drawer catalog: listOrgs and listOrgServices.
 * Atlas trace: UN-3B25A20E, DI-26546721
 *
 * When locked=true, pickers are replaced with read-only Chip elements.
 * Use this when org and service are already known from a pipeline context.
 */
"use client";

import Autocomplete from "@mui/material/Autocomplete";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";
import { listOrgServices, listOrgs } from "@/lib/api/admin";

type NamedId = { id: string; name: string };

interface Props {
  organizationId: string;
  serviceId: string;
  organizationName?: string;
  serviceName?: string;
  onOrganization: (id: string) => void;
  onService: (id: string) => void;
  locked?: boolean;
}

export function FormSchemaScopeFields({
  organizationId,
  serviceId,
  organizationName = "",
  serviceName = "",
  onOrganization,
  onService,
  locked = false,
}: Props) {
  const [orgs, setOrgs] = useState<NamedId[]>([]);
  const [services, setServices] = useState<NamedId[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (locked) return;
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listOrgs({ brief: true });
        if (!cancelled) {
          setOrgs(rows.map((org) => ({ id: org.id, name: org.name || org.id })));
          setError("");
        }
      } catch {
        if (!cancelled) {
          setOrgs([]);
          setError("Could not load organisations. Try again, or open Admin.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [locked]);

  useEffect(() => {
    if (locked || !organizationId) {
      if (!locked) setServices([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listOrgServices(organizationId);
        if (!cancelled) {
          setServices(
            rows.map((svc) => ({
              id: svc.id,
              name: svc.name || svc.code || svc.id,
            })),
          );
        }
      } catch {
        if (!cancelled) {
          setServices([]);
          setError("Could not load services for this organisation.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [organizationId, locked]);

  if (locked) {
    return (
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1 }}>
        <LockedScopePicker
          label="Organisation"
          value={organizationName || organizationId}
        />
        <LockedScopePicker label="Service" value={serviceName || serviceId} />
      </Stack>
    );
  }

  return (
    <Stack spacing={1} sx={{ mt: 1 }}>
      {error ? (
        <Typography variant="caption" color="error">
          {error}
        </Typography>
      ) : null}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
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
    </Stack>
  );
}

function LockedScopePicker({ label, value }: { label: string; value: string }) {
  return (
    <Stack spacing={0.5} sx={{ flex: 1 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      {value ? (
        <Chip
          label={value}
          size="small"
          aria-label={`${label}: ${value}`}
          sx={{ alignSelf: "flex-start" }}
        />
      ) : (
        <Typography variant="caption" color="text.disabled">
          Not set
        </Typography>
      )}
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
        <TextField
          {...params}
          label={label}
          inputProps={{ ...params.inputProps, "aria-label": label }}
        />
      )}
    />
  );
}
