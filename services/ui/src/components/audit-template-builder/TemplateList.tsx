"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ArchiveOutlinedIcon from "@mui/icons-material/ArchiveOutlined";
import AddIcon from "@mui/icons-material/Add";
import { listTemplates, archiveTemplate, type AuditTemplate } from "@/lib/auditTemplateApi";

const STATUS_COLOUR: Record<string, "default" | "success" | "warning" | "error"> = {
  draft: "default",
  published: "success",
  archived: "warning",
};

export default function TemplateList() {
  const router = useRouter();
  const [templates, setTemplates] = useState<AuditTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    listTemplates()
      .then(setTemplates)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleArchive = async (id: string) => {
    try {
      await archiveTemplate(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Archive failed");
    }
  };

  return (
    <Box sx={{ p: 3, maxWidth: 900 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h5" fontWeight={700}>
          Audit templates
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => router.push("/admin/audit-templates/new")}
        >
          New template
        </Button>
      </Box>

      {loading && <CircularProgress size={24} />}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {!loading && templates.length === 0 && (
        <Typography color="text.secondary">
          No templates yet. Create one to get started.
        </Typography>
      )}

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
        {templates.map((t) => (
          <Box
            key={t.template_id}
            sx={{
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 2,
              p: 2,
              display: "flex",
              alignItems: "center",
              gap: 2,
              bgcolor: "background.paper",
            }}
          >
            <Box sx={{ flex: 1 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="subtitle2" fontWeight={600}>
                  {t.title}
                </Typography>
                <Chip
                  label={t.status}
                  size="small"
                  color={STATUS_COLOUR[t.status] ?? "default"}
                  sx={{ height: 20, fontSize: 11 }}
                />
                <Chip
                  label={`v${t.version}`}
                  size="small"
                  variant="outlined"
                  sx={{ height: 20, fontSize: 11 }}
                />
              </Box>
              <Typography variant="caption" color="text.secondary">
                {t.tiles.length} tiles &middot; created by {t.created_by}
              </Typography>
            </Box>
            <Tooltip title="Edit">
              <IconButton
                size="small"
                onClick={() => router.push(`/admin/audit-templates/${t.template_id}`)}
              >
                <EditOutlinedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            {t.status !== "archived" && (
              <Tooltip title="Archive">
                <IconButton size="small" onClick={() => handleArchive(t.template_id)}>
                  <ArchiveOutlinedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
          </Box>
        ))}
      </Box>
    </Box>
  );
}
