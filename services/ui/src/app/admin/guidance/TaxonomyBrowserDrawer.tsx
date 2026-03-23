"use client";

/**
 * TaxonomyBrowserDrawer
 *
 * Slide-in drawer for browsing NICE guidelines by clinical area.
 *
 * Auto-sync flow:
 *   open → GET /nice/taxonomy
 *     available=true  → render hierarchy (titles & loaded status from server)
 *     available=false → POST /nice/catalogue/sync → poll → re-fetch taxonomy
 *
 * Polling is resilient to server restarts: a 404 on the job status endpoint
 * means the server restarted and the in-memory job was lost.  In that case
 * we immediately re-check whether the taxonomy is now available in Neo4j
 * (the sync may have completed before the restart) rather than looping forever.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import LinearProgress from "@mui/material/LinearProgress";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

interface Guideline {
  code: string;
  title: string;
  loaded: boolean;
}

interface Subcategory {
  id: string;
  title: string;
  guideline_count: number;
  loaded_count: number;
  guidelines: Guideline[];
}

interface Category {
  id: string;
  title: string;
  subcategories: Subcategory[];
}

interface TaxonomyResponse {
  available: boolean;
  categories?: Category[];
}

interface Props {
  open: boolean;
  onClose: () => void;
  /** Called when the user clicks Load on a guideline. */
  onSelectGuideline: (code: string) => void;
}

type Phase = "loading" | "syncing" | "ready" | "error";

const POLL_MS = 3000;
const MAX_POLLS = 60; // 3 min hard ceiling — prevents infinite loops if server restarts

export default function TaxonomyBrowserDrawer({ open, onClose, onSelectGuideline }: Props) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [syncStep, setSyncStep] = useState<string>("Setting up for the first time…");
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollCount = useRef(0);

  const fetchTaxonomy = useCallback(async (): Promise<boolean> => {
    const resp = await fetch("/api/nice/taxonomy");
    if (!resp.ok) throw new Error(`Taxonomy fetch failed: ${resp.status}`);
    const data: TaxonomyResponse = await resp.json();
    if (data.available && data.categories?.length) {
      setCategories(data.categories);
      setPhase("ready");
      return true;
    }
    return false;
  }, []);

  const runSync = useCallback(async () => {
    setPhase("syncing");
    setSyncStep("Fetching all NICE guidelines…");

    const syncResp = await fetch("/api/nice/catalogue/sync", { method: "POST" });
    if (!syncResp.ok) throw new Error("Could not start sync");
    const { job_id } = await syncResp.json();
    pollCount.current = 0;

    await new Promise<void>((resolve, reject) => {
      const poll = setInterval(async () => {
        pollCount.current += 1;

        // Hard ceiling — if the server restarted, the job_id is gone forever.
        // Re-check taxonomy directly rather than looping indefinitely.
        if (pollCount.current > MAX_POLLS) {
          clearInterval(poll);
          reject(new Error("Sync is taking longer than expected. Please close and reopen this panel."));
          return;
        }

        try {
          const r = await fetch(`/api/nice/jobs/${job_id}/status`);

          if (!r.ok) {
            // 404 = server restarted and wiped the in-memory job store.
            // The sync may have finished before the restart — check Neo4j directly.
            clearInterval(poll);
            setSyncStep("Checking whether data is ready…");
            const hasData = await fetchTaxonomy();
            if (hasData) {
              resolve();
            } else {
              reject(new Error(
                r.status === 404
                  ? "The server restarted during setup. Please close and try again — it should be instant now."
                  : `Job status check failed (HTTP ${r.status}).`
              ));
            }
            return;
          }

          const s = await r.json();

          if (s.catalogue_count !== undefined) {
            setSyncStep(`Downloaded ${s.catalogue_count} guidelines. Building taxonomy…`);
          }
          if (s.status === "done") {
            clearInterval(poll);
            resolve();
          } else if (s.status === "error") {
            clearInterval(poll);
            reject(new Error(s.error ?? "Sync failed"));
          }
        } catch (e) {
          clearInterval(poll);
          reject(e);
        }
      }, POLL_MS);
    });

    setSyncStep("Taxonomy built. Loading areas…");
  }, [fetchTaxonomy]);

  useEffect(() => {
    if (!open) return;
    setPhase("loading");
    setError(null);

    (async () => {
      try {
        const hasData = await fetchTaxonomy();
        if (!hasData) {
          await runSync();
          await fetchTaxonomy();
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
        setPhase("error");
      }
    })();
  }, [open, fetchTaxonomy, runSync]);

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", sm: 500 }, p: 0 } }}
    >
      <Box
        sx={{
          px: 3,
          py: 2,
          borderBottom: 1,
          borderColor: "divider",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          Browse guidelines by area
        </Typography>
        <Button size="small" onClick={onClose}>
          Close
        </Button>
      </Box>

      <Box sx={{ overflowY: "auto", flex: 1 }}>
        {(phase === "loading" || phase === "syncing") && (
          <Box sx={{ px: 3, py: 4 }}>
            <LinearProgress sx={{ mb: 2 }} />
            <Typography variant="body2" color="text.secondary">
              {phase === "loading" ? "Loading areas…" : syncStep}
            </Typography>
            {phase === "syncing" && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                This only happens once. It takes about 30 seconds.
              </Typography>
            )}
          </Box>
        )}

        {phase === "error" && (
          <Box sx={{ px: 3, py: 3 }}>
            <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
            <Button
              variant="outlined"
              onClick={() => {
                setPhase("loading");
                setError(null);
                fetchTaxonomy()
                  .then((ok) => { if (!ok) setPhase("error"); })
                  .catch(() => setPhase("error"));
              }}
            >
              Try again
            </Button>
          </Box>
        )}

        {phase === "ready" && categories.length === 0 && (
          <Box sx={{ px: 3, py: 4 }}>
            <Typography color="text.secondary">
              No areas found. Try refreshing the guideline list first.
            </Typography>
          </Box>
        )}

        {phase === "ready" &&
          categories.map((cat) => (
            <Accordion key={cat.id} disableGutters elevation={0} square>
              <AccordionSummary
                expandIcon={<ExpandMoreIcon />}
                sx={{ px: 3, borderBottom: 1, borderColor: "divider" }}
              >
                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                  {cat.title}
                </Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ p: 0 }}>
                {cat.subcategories.map((sub) => (
                  <SubcategoryPanel key={sub.id} sub={sub} onLoad={onSelectGuideline} />
                ))}
              </AccordionDetails>
            </Accordion>
          ))}
      </Box>
    </Drawer>
  );
}

function SubcategoryPanel({
  sub,
  onLoad,
}: {
  sub: Subcategory;
  onLoad: (code: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 3,
          py: 1.5,
          cursor: "pointer",
          "&:hover": { bgcolor: "action.hover" },
        }}
        onClick={() => setExpanded((v) => !v)}
        role="button"
        aria-expanded={expanded}
        aria-label={`Expand ${sub.title}`}
      >
        <Box>
          <Typography variant="body2" sx={{ fontWeight: 500 }}>
            {sub.title}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
            <Chip
              label={`${sub.guideline_count} guideline${sub.guideline_count !== 1 ? "s" : ""}`}
              size="small"
              variant="outlined"
            />
            {sub.loaded_count > 0 && (
              <Chip
                icon={<CheckCircleOutlineIcon />}
                label={`${sub.loaded_count} loaded`}
                size="small"
                color="success"
                variant="outlined"
              />
            )}
          </Stack>
        </Box>
        <ExpandMoreIcon
          sx={{
            transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
            color: "action.active",
            flexShrink: 0,
          }}
        />
      </Box>

      {expanded && (
        <List dense disablePadding>
          {sub.guidelines.map((g) => (
            <ListItem
              key={g.code}
              sx={{ pl: 4, pr: 2 }}
              secondaryAction={
                <Button
                  size="small"
                  variant={g.loaded ? "text" : "outlined"}
                  color={g.loaded ? "success" : "primary"}
                  onClick={() => onLoad(g.code)}
                  aria-label={`Load guideline ${g.code}`}
                >
                  {g.loaded ? "Reload" : "Load"}
                </Button>
              }
            >
              <ListItemText
                primary={
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Chip
                      label={g.code}
                      size="small"
                      color={g.loaded ? "success" : "primary"}
                      variant="outlined"
                    />
                    <Typography variant="body2" noWrap title={g.title} sx={{ maxWidth: 280 }}>
                      {g.title !== g.code ? g.title : <em style={{ color: "#888" }}>{g.code}</em>}
                    </Typography>
                  </Stack>
                }
              />
            </ListItem>
          ))}
          {sub.guidelines.length === 0 && (
            <ListItem sx={{ pl: 4 }}>
              <ListItemText
                primary={
                  <Typography variant="body2" color="text.secondary">
                    No guidelines listed for this area.
                  </Typography>
                }
              />
            </ListItem>
          )}
          <Divider />
        </List>
      )}
    </Box>
  );
}
