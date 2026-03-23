"use client";

import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import type { AuditPlaceRow, AuditSectionResult } from "@/lib/analyticsApi";

const PLACE_DISPLAY: Record<string, string> = {
  gp_surgery: "GP Surgery",
  ae: "A&E",
  a_and_e: "A&E",
  "a&e": "A&E",
  hospital: "Hospital",
  pharmacy: "Pharmacy",
  "not recorded": "Not Recorded",
};

function formatPlace(raw: string): string {
  return PLACE_DISPLAY[raw.toLowerCase()] ?? raw;
}

interface Props {
  result: AuditSectionResult<AuditPlaceRow[]> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function PlaceOfPresentationSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice ?? [];
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  const chartData: ComparisonDataRow[] = practice.slice(0, 8).map((row) => {
    const label = formatPlace(row.place);
    const aRow = allianceLive?.find((r) => formatPlace(r.place) === label);
    const eRow = englandLive?.find((r) => formatPlace(r.place) === label);
    const isGP = label === "GP Surgery";
    const isAE = label.toLowerCase().includes("a&e") || label.toLowerCase().includes("ae");
    const metricKey = isGP ? "place_of_presentation.gp_surgery_pct" : isAE ? "place_of_presentation.ae_pct" : "";
    return {
      category: label,
      practice: row.pct,
      similar: aRow?.pct ?? null,
      alliance: eRow?.pct ?? null,
      national: metricKey ? resolveBenchmarkValue(bm, metricKey, orgSelected) : null,
    };
  });

  const gpLive = practice.find((r) => formatPlace(r.place) === "GP Surgery");
  const aeLive = practice.find((r) => formatPlace(r.place).toLowerCase().includes("a&e") || formatPlace(r.place).toLowerCase().includes("ae"));
  const gpAlive = allianceLive?.find((r) => formatPlace(r.place) === "GP Surgery");
  const aeAlive = allianceLive?.find((r) => formatPlace(r.place).toLowerCase().includes("a&e"));
  const gpElive = englandLive?.find((r) => formatPlace(r.place) === "GP Surgery");
  const aeElive = englandLive?.find((r) => formatPlace(r.place).toLowerCase().includes("a&e"));

  const tableRows = [
    {
      label: "GP Surgery (%)",
      unit: "%",
      practice: gpLive ? { value: gpLive.pct } : null,
      similar: gpAlive ? { value: gpAlive.pct } : null,
      alliance: gpElive ? { value: gpElive.pct } : { value: bm?.["place_of_presentation.gp_surgery_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "place_of_presentation.gp_surgery_pct", orgSelected) },
    },
    {
      label: "A&E (%)",
      unit: "%",
      practice: aeLive ? { value: aeLive.pct } : null,
      similar: aeAlive ? { value: aeAlive.pct } : null,
      alliance: aeElive ? { value: aeElive.pct } : { value: bm?.["place_of_presentation.ae_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "place_of_presentation.ae_pct", orgSelected) },
    },
  ];

  return (
    <SectionCard
      id="section-place-of-presentation"
      title="Place of Presentation"
      description="Where the patient first presented with symptoms that were ultimately related to the cancer diagnosis."
      availability="pipeline_pending"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        visibleKeys={visibleKeys}
        orgSelected={orgSelected}
        ariaLabel="Place of first presentation compared to alliance and national benchmarks"
      />
      <SummaryStatsTable
        rows={tableRows}
        visibleKeys={visibleKeys}
        orgSelected={orgSelected}
        caption="Place of first presentation — % of audited cases"
      />
    </SectionCard>
  );
}
