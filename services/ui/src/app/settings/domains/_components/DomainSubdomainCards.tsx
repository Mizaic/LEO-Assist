"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import Tooltip from "@mui/material/Tooltip";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import SettingsIcon from "@mui/icons-material/Settings";
import type { SubdomainSummary } from "@/lib/analyticsApi";

export interface DomainSubdomainCardsProps {
  subdomainCount: number;
  subdomains: SubdomainSummary[];
  canEditDomains: boolean;
  deletingSubdomain: string | null;
  onCreateClick: () => void;
  onConfigure: (sub: SubdomainSummary) => void;
  onDelete: (sub: SubdomainSummary) => void;
}

export default function DomainSubdomainCards({
  subdomainCount,
  subdomains,
  canEditDomains,
  deletingSubdomain,
  onCreateClick,
  onConfigure,
  onDelete,
}: DomainSubdomainCardsProps) {
  return (
    <>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 2,
        }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Subdomains ({subdomainCount})
        </Typography>
        {canEditDomains && (
          <Button
            variant="contained"
            size="small"
            startIcon={<AddIcon />}
            onClick={onCreateClick}
          >
            Create subdomain
          </Button>
        )}
      </Box>

      {subdomainCount === 0 ? (
        <Typography
          color="text.secondary"
          sx={{ py: 4, textAlign: "center" }}
        >
          {canEditDomains
            ? "No subdomains yet. Create one to start adding SNOMED concepts."
            : "No subdomains yet."}
        </Typography>
      ) : (
        <List disablePadding>
          {subdomains.map((sub, idx) => (
            <Card key={`${sub.name}-${idx}`} sx={{ mb: 1 }}>
              <CardContent
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 2,
                  py: 1.5,
                  "&:last-child": { pb: 1.5 },
                }}
              >
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    {sub.name.replace(/_/g, " ")}
                  </Typography>
                  {sub.description && (
                    <Typography variant="body2" color="text.secondary">
                      {sub.description}
                    </Typography>
                  )}
                  <Box
                    sx={{
                      mt: 0.5,
                      display: "flex",
                      gap: 0.5,
                      flexWrap: "wrap",
                    }}
                  >
                    <Chip
                      label={`${sub.concept_count} concept${sub.concept_count !== 1 ? "s" : ""}`}
                      size="small"
                    />
                    {(sub.descendant_count ?? 0) > 0 && (
                      <Tooltip title="Additional codes matched automatically via IS_A hierarchy">
                        <Chip
                          label={`+${sub.descendant_count} variants`}
                          size="small"
                          color="info"
                          variant="outlined"
                        />
                      </Tooltip>
                    )}
                    {sub.milestone_type && (
                      <Chip
                        label={sub.milestone_type}
                        size="small"
                        variant="outlined"
                      />
                    )}
                    {sub.semantic_tags.map((t) => (
                      <Chip
                        key={t}
                        label={t}
                        size="small"
                        variant="outlined"
                        color="info"
                      />
                    ))}
                  </Box>
                </Box>
                <Box sx={{ display: "flex", gap: 0.5 }}>
                  <IconButton
                    onClick={() => onConfigure(sub)}
                    aria-label={`Configure ${sub.name}`}
                    size="small"
                  >
                    <SettingsIcon />
                  </IconButton>
                  {canEditDomains && (
                    <Tooltip title="Delete subdomain">
                      <span>
                        <IconButton
                          onClick={() => onDelete(sub)}
                          aria-label={`Delete ${sub.name}`}
                          size="small"
                          color="error"
                          disabled={deletingSubdomain === sub.name}
                        >
                          <DeleteOutlineIcon />
                        </IconButton>
                      </span>
                    </Tooltip>
                  )}
                </Box>
              </CardContent>
            </Card>
          ))}
        </List>
      )}
    </>
  );
}
