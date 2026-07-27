/**
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

import { AnimatePresence, motion as fm } from "framer-motion";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import HighlightOffRoundedIcon from "@mui/icons-material/HighlightOffRounded";

import { popVariants } from "./motionPresets";
import type { PromoteResult, Rule } from "./ruleReviewTypes";

export interface RuleReviewSessionPanelsProps {
  reducedMotion: boolean;
  sessionApproved: Rule[];
  sessionExcluded: Rule[];
  sessionApprovedOpen: boolean;
  sessionExcludedOpen: boolean;
  promotedRules: Record<string, PromoteResult>;
  promoteBusy: string | null;
  onToggleApprovedOpen: () => void;
  onToggleExcludedOpen: () => void;
  onEdit: (rule: Rule) => void;
  onPromoteConfirm: (rule: Rule) => void;
}

export default function RuleReviewSessionPanels({
  reducedMotion,
  sessionApproved,
  sessionExcluded,
  sessionApprovedOpen,
  sessionExcludedOpen,
  promotedRules,
  promoteBusy,
  onToggleApprovedOpen,
  onToggleExcludedOpen,
  onEdit,
  onPromoteConfirm,
}: RuleReviewSessionPanelsProps) {
  return (
    <>
      {sessionApproved.length > 0 ? (
        <Box sx={{ mb: 3 }}>
          <Stack
            component="button"
            type="button"
            direction="row"
            alignItems="center"
            spacing={0.5}
            onClick={onToggleApprovedOpen}
            aria-expanded={sessionApprovedOpen}
            aria-controls="session-approved-body"
            sx={{
              mb: sessionApprovedOpen ? 1 : 0,
              p: 0,
              border: "none",
              bgcolor: "transparent",
              cursor: "pointer",
              width: "100%",
              textAlign: "left",
            }}
          >
            <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.6, flex: 1 }}>
              {`Approved in this session (${sessionApproved.length})`}
            </Typography>
            <IconButton
              size="small"
              tabIndex={-1}
              aria-hidden
              sx={{ transform: sessionApprovedOpen ? "rotate(180deg)" : "none" }}
            >
              <ExpandMoreRoundedIcon fontSize="small" />
            </IconButton>
          </Stack>
          <Collapse in={sessionApprovedOpen}>
            <Stack id="session-approved-body" spacing={1}>
              <AnimatePresence initial={false}>
                {sessionApproved.map((rule) => (
                  <fm.div
                    key={rule.rule_id}
                    layout
                    variants={popVariants(reducedMotion)}
                    initial="initial"
                    animate="animate"
                    exit="exit"
                  >
                    <Box
                      sx={{
                        p: 1.5,
                        border: "1px solid",
                        borderColor: "success.light",
                        borderRadius: 1.5,
                        bgcolor: "#F0FDF4",
                      }}
                    >
                      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 1 }}>
                        <fm.div
                          initial={reducedMotion ? undefined : { scale: 0 }}
                          animate={{ scale: 1 }}
                          transition={{
                            type: "spring",
                            stiffness: 420,
                            damping: 18,
                            delay: reducedMotion ? 0 : 0.1,
                          }}
                          style={{ display: "flex" }}
                        >
                          <CheckCircleRoundedIcon fontSize="small" color="success" />
                        </fm.div>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                          {rule.name || rule.rule_id}
                        </Typography>
                      </Stack>
                      <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                        <Button
                          size="small"
                          variant="outlined"
                          color="primary"
                          startIcon={<EditOutlinedIcon fontSize="small" />}
                          onClick={() => onEdit(rule)}
                          aria-label={`Edit approved rule ${rule.rule_id}`}
                        >
                          Edit
                        </Button>
                        {promotedRules[rule.rule_id] ? (
                          <Alert
                            severity="success"
                            sx={{ py: 0, px: 1, fontSize: "0.75rem", flex: 1 }}
                          >
                            Added to {promotedRules[rule.rule_id].domain_name}
                          </Alert>
                        ) : (
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={promoteBusy === rule.rule_id}
                            onClick={() => onPromoteConfirm(rule)}
                          >
                            Add to domain
                          </Button>
                        )}
                      </Stack>
                    </Box>
                  </fm.div>
                ))}
              </AnimatePresence>
            </Stack>
          </Collapse>
        </Box>
      ) : null}

      {sessionExcluded.length > 0 ? (
        <Box sx={{ mb: 3 }}>
          <Stack
            component="button"
            type="button"
            direction="row"
            alignItems="center"
            spacing={0.5}
            onClick={onToggleExcludedOpen}
            aria-expanded={sessionExcludedOpen}
            aria-controls="session-excluded-body"
            sx={{
              mb: sessionExcludedOpen ? 1 : 0,
              p: 0,
              border: "none",
              bgcolor: "transparent",
              cursor: "pointer",
              width: "100%",
              textAlign: "left",
            }}
          >
            <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.6, flex: 1 }}>
              {`Excluded in this session (${sessionExcluded.length})`}
            </Typography>
            <IconButton
              size="small"
              tabIndex={-1}
              aria-hidden
              sx={{ transform: sessionExcludedOpen ? "rotate(180deg)" : "none" }}
            >
              <ExpandMoreRoundedIcon fontSize="small" />
            </IconButton>
          </Stack>
          <Collapse in={sessionExcludedOpen}>
            <Stack id="session-excluded-body" spacing={1}>
              <AnimatePresence initial={false}>
                {sessionExcluded.map((rule) => (
                  <fm.div
                    key={rule.rule_id}
                    layout
                    variants={popVariants(reducedMotion)}
                    initial="initial"
                    animate="animate"
                    exit="exit"
                  >
                    <Box
                      sx={{
                        p: 1.5,
                        border: "1px solid",
                        borderColor: "grey.300",
                        borderRadius: 1.5,
                        bgcolor: "grey.50",
                      }}
                    >
                      <Stack direction="row" spacing={0.75} alignItems="center">
                        <HighlightOffRoundedIcon fontSize="small" color="action" />
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                          {rule.name || rule.rule_id}
                        </Typography>
                        <Chip
                          size="small"
                          label={
                            rule.generation_outcome === "no_rule_expected"
                              ? "No rule needed"
                              : "Excluded"
                          }
                          variant="outlined"
                        />
                      </Stack>
                    </Box>
                  </fm.div>
                ))}
              </AnimatePresence>
            </Stack>
          </Collapse>
        </Box>
      ) : null}
    </>
  );
}
