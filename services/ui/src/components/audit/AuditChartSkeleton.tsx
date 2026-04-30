/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import Box from "@mui/material/Box";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";

export type AuditChartSkeletonVariant =
  | "bars"
  | "horizontalBars"
  | "radar"
  | "radarGrid"
  | "pie"
  | "pyramid"
  | "segmented"
  | "strip"
  | "sankey"
  | "stats";

interface AuditChartSkeletonProps {
  variant?: AuditChartSkeletonVariant;
  height?: number;
  label?: string;
}

// Maintenance note: these skeletons intentionally mirror the chart geometry
// used in /care/audit. If a chart type changes, update its matching skeleton
// variant in this file in the same change.

const widths = ["72%", "54%", "82%", "38%", "66%"];

function BarsSkeleton({ horizontal = false }: { horizontal?: boolean }) {
  return (
    <Stack spacing={1.1} sx={{ height: "100%", justifyContent: "center" }}>
      {widths.map((width, idx) => (
        <Box
          key={`${width}-${idx}`}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            height: horizontal ? 24 : 34,
          }}
        >
          <Skeleton variant="text" width={horizontal ? 72 : 34} />
          <Skeleton
            variant="rounded"
            width={horizontal ? width : 28 + idx * 10}
            height={horizontal ? 14 : 24 + (idx % 3) * 14}
            sx={horizontal ? undefined : { alignSelf: "flex-end" }}
          />
          {!horizontal && <Skeleton variant="rounded" width={24} height={18 + idx * 8} />}
          {!horizontal && <Skeleton variant="rounded" width={24} height={26 + idx * 5} />}
        </Box>
      ))}
    </Stack>
  );
}

function RadarSkeleton() {
  return (
    <Box sx={{ display: "grid", placeItems: "center", height: "100%" }}>
      <Box sx={{ position: "relative", width: 190, height: 190 }}>
        {[0, 1, 2].map((idx) => (
          <Skeleton
            key={idx}
            variant="circular"
            width={190 - idx * 46}
            height={190 - idx * 46}
            sx={{
              position: "absolute",
              left: idx * 23,
              top: idx * 23,
              bgcolor: "action.hover",
            }}
          />
        ))}
        {[0, 1, 2, 3, 4, 5].map((idx) => (
          <Box
            key={idx}
            sx={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: 84,
              height: 1,
              bgcolor: "divider",
              transformOrigin: "0 50%",
              transform: `rotate(${idx * 60}deg)`,
            }}
          />
        ))}
      </Box>
    </Box>
  );
}

function PieSkeleton() {
  return (
    <Stack direction="row" spacing={2} alignItems="center" sx={{ height: "100%" }}>
      <Skeleton variant="circular" width={150} height={150} />
      <Stack spacing={1} sx={{ flex: 1 }}>
        {[0, 1, 2, 3].map((idx) => (
          <Skeleton key={idx} variant="rounded" height={14} width={`${72 - idx * 8}%`} />
        ))}
      </Stack>
    </Stack>
  );
}

function PyramidSkeleton() {
  return (
    <Stack spacing={1.2} sx={{ height: "100%", justifyContent: "center" }}>
      <Stack direction="row" spacing={2} justifyContent="center">
        <Skeleton variant="circular" width={88} height={88} />
        <Stack spacing={0.8} sx={{ flex: 1, justifyContent: "center" }}>
          {[0, 1, 2, 3, 4, 5].map((idx) => (
            <Box key={idx} sx={{ display: "flex", gap: 0.75, alignItems: "center" }}>
              <Skeleton variant="rounded" width={`${36 + idx * 4}%`} height={10} />
              <Skeleton variant="rounded" width={`${54 - idx * 5}%`} height={10} />
            </Box>
          ))}
        </Stack>
      </Stack>
    </Stack>
  );
}

function SegmentedSkeleton() {
  return (
    <Stack spacing={1.5} sx={{ height: "100%", justifyContent: "center" }}>
      {[0, 1, 2].map((idx) => (
        <Stack key={idx} spacing={0.6}>
          <Skeleton variant="text" width={`${38 + idx * 10}%`} />
          <Box sx={{ display: "flex", gap: 0.5 }}>
            <Skeleton variant="rounded" width="42%" height={20} />
            <Skeleton variant="rounded" width="28%" height={20} />
            <Skeleton variant="rounded" width="30%" height={20} />
          </Box>
        </Stack>
      ))}
    </Stack>
  );
}

function StripSkeleton() {
  return (
    <Box sx={{ position: "relative", height: "100%", minHeight: 190, px: 1 }}>
      <Skeleton variant="rounded" height={2} width="100%" sx={{ position: "absolute", top: "55%" }} />
      {[12, 22, 31, 44, 58, 68, 76, 88].map((left, idx) => (
        <Skeleton
          key={`${left}-${idx}`}
          variant="circular"
          width={12}
          height={12}
          sx={{ position: "absolute", left: `${left}%`, top: `${42 + (idx % 3) * 10}%` }}
        />
      ))}
      <Skeleton variant="rounded" width={2} height="62%" sx={{ position: "absolute", left: "50%", top: "20%" }} />
    </Box>
  );
}

function SankeySkeleton() {
  return (
    <Box sx={{ position: "relative", height: "100%", minHeight: 220 }}>
      {[8, 42, 76].map((left) => (
        <Stack key={left} spacing={2} sx={{ position: "absolute", left: `${left}%`, top: 20, width: 74 }}>
          <Skeleton variant="rounded" height={42} />
          <Skeleton variant="rounded" height={58} />
          <Skeleton variant="rounded" height={34} />
        </Stack>
      ))}
      {[28, 52].map((left) => (
        <Skeleton
          key={left}
          variant="rounded"
          width="18%"
          height={14}
          sx={{ position: "absolute", left: `${left}%`, top: "43%", borderRadius: 999 }}
        />
      ))}
    </Box>
  );
}

function StatsSkeleton() {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 1.5 }}>
      {[0, 1, 2, 3].map((idx) => (
        <Stack key={idx} spacing={1} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, p: 1.5 }}>
          <Skeleton variant="text" width="60%" />
          <Skeleton variant="text" width="38%" height={34} />
          <Skeleton variant="text" width="72%" />
        </Stack>
      ))}
    </Box>
  );
}

export default function AuditChartSkeleton({
  variant = "bars",
  height = 220,
  label = "Loading chart",
}: AuditChartSkeletonProps) {
  const content = (() => {
    if (variant === "horizontalBars") return <BarsSkeleton horizontal />;
    if (variant === "radar" || variant === "radarGrid") return <RadarSkeleton />;
    if (variant === "pie") return <PieSkeleton />;
    if (variant === "pyramid") return <PyramidSkeleton />;
    if (variant === "segmented") return <SegmentedSkeleton />;
    if (variant === "strip") return <StripSkeleton />;
    if (variant === "sankey") return <SankeySkeleton />;
    if (variant === "stats") return <StatsSkeleton />;
    return <BarsSkeleton />;
  })();

  if (variant === "radarGrid") {
    return (
      <Box role="status" aria-label={label} sx={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 2 }}>
        {[0, 1, 2, 3].map((idx) => (
          <Box key={idx} sx={{ height, border: "1px solid", borderColor: "divider", borderRadius: 2, p: 1.5 }}>
            <RadarSkeleton />
          </Box>
        ))}
      </Box>
    );
  }

  return (
    <Box role="status" aria-label={label} sx={{ height, width: "100%" }}>
      {content}
    </Box>
  );
}
