"use client";

/**
 * Sandbox cost estimate table. Extracted from prompts/[id]/page.tsx
 * (Phase 4b decomposition).
 */

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { CostEstimate, SandboxResult } from "./types";

interface SandboxCostTableProps {
  result: SandboxResult;
}

const HEADERS = [
  "Model",
  "Without cache (call 1)",
  "With cache (call 2+)",
  "Saving",
] as const;

export function SandboxCostTable({ result }: SandboxCostTableProps) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Typography
          variant="caption"
          fontWeight={700}
          color="text.secondary"
        >
          COST ESTIMATE
        </Typography>
        {result.presetName && (
          <Chip
            size="small"
            label={result.presetName}
            color="primary"
            variant="outlined"
            sx={{ height: 18, fontSize: "0.62rem" }}
          />
        )}
        {result.consensusMode && (
          <Chip
            size="small"
            label="Consensus"
            color="info"
            sx={{ height: 18, fontSize: "0.62rem" }}
          />
        )}
        <Stack direction="row" spacing={0.5} sx={{ ml: "auto" }}>
          <Chip
            size="small"
            label={`System ${result.tokenEstimate.approxSystemTokens.toLocaleString()} tok`}
            variant="outlined"
            sx={{ height: 18, fontSize: "0.6rem" }}
          />
          <Chip
            size="small"
            label={`User ${result.tokenEstimate.approxUserTokens.toLocaleString()} tok`}
            variant="outlined"
            color="secondary"
            sx={{ height: 18, fontSize: "0.6rem" }}
          />
          <Chip
            size="small"
            label={`Output ~${result.tokenEstimate.estOutputTokens} tok`}
            variant="outlined"
            color="info"
            sx={{ height: 18, fontSize: "0.6rem" }}
          />
          <Chip
            size="small"
            label={`Core: ${result.coreExamples.length}  Dynamic: ${result.selectedDynamicExamples.length}`}
            variant="outlined"
            color="success"
            sx={{ height: 18, fontSize: "0.6rem" }}
          />
        </Stack>
      </Stack>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr 80px",
          gap: 0.5,
          mb: 0.5,
        }}
      >
        {HEADERS.map((h) => (
          <Typography
            key={h}
            variant="caption"
            fontWeight={700}
            color="text.disabled"
            sx={{ fontSize: "0.65rem" }}
          >
            {h}
          </Typography>
        ))}
      </Box>
      <Divider sx={{ mb: 0.75 }} />

      {result.costEstimates.map((ce, idx) => (
        <CostRow key={idx} estimate={ce} />
      ))}

      {result.llmTokenUsage && <ActualUsageRow result={result} />}
    </Paper>
  );
}

function CostRow({ estimate }: { estimate: CostEstimate }) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr 1fr 80px",
        gap: 0.5,
        mb: 0.75,
        alignItems: "start",
      }}
    >
      <Stack spacing={0.25}>
        <Stack direction="row" spacing={0.5} alignItems="center">
          {estimate.role === "secondary" && (
            <Chip
              size="small"
              label="2nd"
              color="secondary"
              sx={{ height: 16, fontSize: "0.58rem" }}
            />
          )}
          <Typography
            variant="caption"
            fontWeight={600}
            sx={{ fontSize: "0.7rem", lineHeight: 1.2 }}
          >
            {estimate.model.displayName}
          </Typography>
        </Stack>
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ fontFamily: "monospace", fontSize: "0.58rem" }}
        >
          ${estimate.model.costPer1mInput}/M in - $
          {estimate.model.costPer1mCachedInput}/M cached - $
          {estimate.model.costPer1mOutput}/M out
        </Typography>
      </Stack>

      <Stack spacing={0.2}>
        <Typography
          variant="caption"
          fontWeight={700}
          sx={{ fontSize: "0.72rem", color: "warning.dark" }}
        >
          ${estimate.withoutCache.totalCost.toFixed(5)}
        </Typography>
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ fontSize: "0.6rem" }}
        >
          Input ${estimate.withoutCache.inputCost?.toFixed(5)} + Out $
          {estimate.withoutCache.outputCost?.toFixed(5)}
        </Typography>
      </Stack>

      <Stack spacing={0.2}>
        <Typography
          variant="caption"
          fontWeight={700}
          sx={{ fontSize: "0.72rem", color: "success.dark" }}
        >
          ${estimate.withCache.totalCost.toFixed(5)}
        </Typography>
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ fontSize: "0.6rem" }}
        >
          Cached ${estimate.withCache.cachedInputCost?.toFixed(5)} + User $
          {estimate.withCache.uncachedInputCost?.toFixed(5)} + Out $
          {estimate.withCache.outputCost?.toFixed(5)}
        </Typography>
      </Stack>

      <Chip
        size="small"
        label={`${estimate.cacheSavingPct.toFixed(1)}%`}
        color={
          estimate.cacheSavingPct > 50
            ? "success"
            : estimate.cacheSavingPct > 20
              ? "warning"
              : "default"
        }
        sx={{
          height: 22,
          fontSize: "0.65rem",
          fontWeight: 700,
          alignSelf: "center",
        }}
      />
    </Box>
  );
}

function ActualUsageRow({ result }: { result: SandboxResult }) {
  const usage = result.llmTokenUsage!;
  return (
    <>
      <Divider sx={{ my: 0.75 }} />
      <Stack
        direction="row"
        spacing={1}
        flexWrap="wrap"
        useFlexGap
        alignItems="center"
      >
        <Typography
          variant="caption"
          color="text.disabled"
          fontWeight={600}
        >
          ACTUAL (live call)
        </Typography>
        <Chip
          size="small"
          label={`Input ${usage.inputTokens.toLocaleString()} tok`}
          color="primary"
          sx={{ height: 18, fontSize: "0.62rem" }}
        />
        {usage.cachedInputTokens > 0 && (
          <Chip
            size="small"
            label={`Cached ${usage.cachedInputTokens.toLocaleString()} tok`}
            color="success"
            sx={{ height: 18, fontSize: "0.62rem" }}
          />
        )}
        <Chip
          size="small"
          label={`Output ${usage.outputTokens.toLocaleString()} tok`}
          color="secondary"
          sx={{ height: 18, fontSize: "0.62rem" }}
        />
        {result.llmActualCostUsd != null && (
          <Chip
            size="small"
            label={`$${result.llmActualCostUsd.toFixed(5)}`}
            sx={{
              height: 20,
              fontSize: "0.68rem",
              bgcolor: "success.100",
              color: "success.dark",
              fontWeight: 700,
            }}
          />
        )}
      </Stack>
    </>
  );
}
