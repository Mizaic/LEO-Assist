"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * Admin list of all audit templates with StatHero, design-system cards,
 * and a confirmation gate before archive.
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Tooltip from "@mui/material/Tooltip";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ArchiveOutlinedIcon from "@mui/icons-material/ArchiveOutlined";
import AddIcon from "@mui/icons-material/Add";
import DashboardCustomizeOutlinedIcon from "@mui/icons-material/DashboardCustomizeOutlined";
import PublicOutlinedIcon from "@mui/icons-material/PublicOutlined";
import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";
import { StatHero, ToolbarActions, type StatTile, type ToolbarAction } from "@leo/design-system";
import { listTemplates, archiveTemplate, type AuditTemplate } from "@/lib/auditTemplateApi";
import ConfirmDialog from "@/components/ConfirmDialog";

const STATUS_COLOUR: Record<string, "default" | "success" | "warning"> = {
  draft: "default",
  published: "success",
  archived: "warning",
};

const STATUS_ACCENT: Record<string, string> = {
  draft: "#94A3B8",
  published: "#047857",
  archived: "#B45309",
};

function CardSkeleton() {
  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1.5,
        p: 2,
        display: "flex",
        alignItems: "center",
        gap: 2,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 2,
          background: "#E2E8F0",
        }}
      />
      <Box sx={{ flex: 1, pl: 1 }}>
        <Skeleton variant="text" width={220} height={20} />
        <Skeleton variant="text" width={140} height={16} sx={{ mt: 0.25 }} />
      </Box>
      <Skeleton variant="circular" width={28} height={28} />
      <Skeleton variant="circular" width={28} height={28} />
    </Box>
  );
}

function TemplateCard({
  template,
  onEdit,
  onArchive,
}: {
  template: AuditTemplate;
  onEdit: () => void;
  onArchive: () => void;
}) {
  const accent = STATUS_ACCENT[template.status] ?? "#94A3B8";
  const updated = new Date(template.updated_at).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1.5,
        p: 2,
        pl: 2.5,
        display: "flex",
        alignItems: "center",
        gap: 2,
        bgcolor: "background.paper",
        position: "relative",
        overflow: "hidden",
        transition: "box-shadow 180ms ease-out",
        "&:hover": { boxShadow: "0 2px 8px rgba(0,0,0,0.07)" },
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 2,
          background: accent,
        }}
      />

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
          <Typography variant="subtitle2" fontWeight={600} noWrap>
            {template.title}
          </Typography>
          <Chip
            label={template.status}
            size="small"
            color={STATUS_COLOUR[template.status] ?? "default"}
            sx={{ height: 20, fontSize: 11, textTransform: "capitalize" }}
          />
          <Chip
            label={`v${template.version}`}
            size="small"
            variant="outlined"
            sx={{ height: 20, fontSize: 11 }}
          />
        </Box>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
          {template.tiles.length} {template.tiles.length === 1 ? "tile" : "tiles"}
          {" \u00B7 "}
          Updated {updated}
          {" \u00B7 "}
          {template.created_by}
        </Typography>
      </Box>

      <Tooltip title="Edit template">
        <IconButton size="small" onClick={onEdit} aria-label={`Edit ${template.title}`}>
          <EditOutlinedIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      {template.status !== "archived" && (
        <Tooltip title="Archive template">
          <IconButton
            size="small"
            onClick={onArchive}
            aria-label={`Archive ${template.title}`}
          >
            <ArchiveOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Box>
  );
}

export default function TemplateList() {
  const router = useRouter();
  const [templates, setTemplates] = useState<AuditTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<AuditTemplate | null>(null);
  const [archiving, setArchiving] = useState(false);

  const load = () => {
    setLoading(true);
    listTemplates()
      .then(setTemplates)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const stats: StatTile[] = useMemo(
    () => [
      {
        id: "total",
        label: "Total templates",
        value: templates.length,
        icon: <DashboardCustomizeOutlinedIcon />,
        tone: "neutral" as const,
      },
      {
        id: "published",
        label: "Published",
        value: templates.filter((t) => t.status === "published").length,
        icon: <PublicOutlinedIcon />,
        tone: "positive" as const,
      },
      {
        id: "draft",
        label: "Drafts",
        value: templates.filter((t) => t.status === "draft").length,
        icon: <EditNoteOutlinedIcon />,
        tone: "neutral" as const,
      },
    ],
    [templates],
  );

  const toolbarActions: ToolbarAction[] = [
    {
      id: "new-template",
      label: "New template",
      icon: <AddIcon fontSize="small" />,
      variant: "primary",
      onClick: () => router.push("/admin/audit-templates/new"),
    },
  ];

  const handleArchiveConfirm = async () => {
    if (!archiveTarget) return;
    setArchiving(true);
    try {
      await archiveTemplate(archiveTarget.template_id);
      setArchiveTarget(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Archive failed");
    } finally {
      setArchiving(false);
    }
  };

  return (
    <Box sx={{ p: 3, maxWidth: 960 }}>
      <StatHero stats={stats} />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 2,
          mt: 3,
        }}
      >
        <Typography variant="h6" fontWeight={700} component="h1">
          Audit templates
        </Typography>
        <ToolbarActions actions={toolbarActions} />
      </Box>

      {loading && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          {[0, 1, 2].map((i) => <CardSkeleton key={i} />)}
        </Box>
      )}

      {!loading && templates.length === 0 && (
        <Box
          sx={{
            border: "2px dashed",
            borderColor: "divider",
            borderRadius: 2,
            p: 6,
            textAlign: "center",
            color: "text.secondary",
          }}
        >
          <DashboardCustomizeOutlinedIcon sx={{ fontSize: 40, mb: 1, opacity: 0.4 }} />
          <Typography variant="body1" fontWeight={500}>
            No audit templates yet
          </Typography>
          <Typography variant="body2" sx={{ mt: 0.5 }}>
            Create a template to define what metrics your sites will see in their audit report.
          </Typography>
        </Box>
      )}

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
        {templates.map((t) => (
          <TemplateCard
            key={t.template_id}
            template={t}
            onEdit={() => router.push(`/admin/audit-templates/${t.template_id}`)}
            onArchive={() => setArchiveTarget(t)}
          />
        ))}
      </Box>

      {archiveTarget && (
        <ConfirmDialog
          title="Archive template?"
          body={`"${archiveTarget.title}" will no longer be available to assign to sites. Sites already using it will keep their current view until reassigned.`}
          confirmLabel={archiving ? "Archiving..." : "Archive"}
          variant="danger"
          onConfirm={handleArchiveConfirm}
          onCancel={() => setArchiveTarget(null)}
        />
      )}
    </Box>
  );
}
