/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   UN: UN-72B60B2D
 *   DI: DI-47D2CD86, DI-D90542E5, DI-6BD7B681
 *   DO: DO-5A88E0B9
 *   VT: VT-8DE34E84
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import CategoryOutlinedIcon from "@mui/icons-material/CategoryOutlined";
import HistoryIcon from "@mui/icons-material/History";
import TextFieldsOutlinedIcon from "@mui/icons-material/TextFieldsOutlined";

import {
  EmptyState,
  SegmentedTabs,
  SpringSwap,
  StatHero,
  StickyChrome,
  ToolbarActions,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";
import { color } from "@leo/design-system/tokens";

import { LiveDictionaryPane } from "./LiveDictionaryPane";
import { PhraseChangeLogDialog } from "./PhraseChangeLogDialog";
import { PhraseDetailPane } from "./PhraseDetailPane";
import { PhraseQueueList } from "./PhraseQueueList";
import { draftNeedsTermFix } from "./termNeedsFix";
import { usePhraseMappings, type PhraseMode } from "./usePhraseMappings";

export default function PhraseMappingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [liveSearch, setLiveSearch] = useState(
    searchParams?.get("q") || searchParams?.get("phrase_key") || "",
  );
  const [auditOpen, setAuditOpen] = useState(false);
  const state = usePhraseMappings();

  useEffect(() => {
    if (searchParams?.get("createLocal") === "1") {
      router.replace("/admin/guidance/local-concepts");
    }
  }, [searchParams, router]);

  const tiles: StatTile[] = useMemo(
    () => [
      { id: "inbox", label: "Inbox", value: String(state.counts.inbox) },
      { id: "drafts", label: "My drafts", value: String(state.counts.my_drafts) },
      { id: "review", label: "Review", value: String(state.counts.review) },
    ],
    [state.counts],
  );

  const toolbarActions: ToolbarAction[] = [
    {
      id: "create-local-concept",
      label: "Create local concept",
      icon: <CategoryOutlinedIcon fontSize="small" />,
      variant: "secondary",
      onClick: () => router.push("/admin/guidance/local-concepts"),
    },
    {
      id: "audit-log",
      label: "Change log",
      icon: <HistoryIcon fontSize="small" />,
      variant: "secondary",
      onClick: () => setAuditOpen(true),
    },
  ];

  return (
    <div data-testid="phrase-mappings-workspace">
      <StatHero stats={tiles} />
      <StickyChrome testId="phrase-mappings-chrome">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <SegmentedTabs
            aria-label="Workspaces"
            value={state.mode}
            onChange={(id) => state.setMode(id as PhraseMode)}
            tabs={[
              { id: "inbox", label: "Inbox", count: state.counts.inbox },
              { id: "drafts", label: "My drafts", count: state.counts.my_drafts },
              { id: "review", label: "Review", count: state.counts.review },
              { id: "live", label: "Live dictionary" },
            ]}
          />
          <ToolbarActions actions={toolbarActions} />
        </div>
      </StickyChrome>
      {state.mode === "drafts" ? (
        <DraftsSubmitBar
          saving={state.saving}
          draftCount={state.counts.my_drafts}
          termFixCount={state.items.filter(draftNeedsTermFix).length}
          onSubmit={() => void state.handleSubmit()}
        />
      ) : null}
      {state.notice ? (
        <p style={{ color: color.status.success, fontSize: 14 }}>{state.notice}</p>
      ) : null}
      <SpringSwap swapKey={state.mode}>
        <WorkspaceBody
          state={state}
          liveSearch={liveSearch}
          onLiveSearch={setLiveSearch}
        />
      </SpringSwap>
      <PhraseChangeLogDialog open={auditOpen} onClose={() => setAuditOpen(false)} />
    </div>
  );
}

function DraftsSubmitBar({
  saving,
  draftCount,
  termFixCount,
  onSubmit,
}: {
  saving: boolean;
  draftCount: number;
  termFixCount: number;
  onSubmit: () => void;
}) {
  return (
    <>
      <ToolbarActions
        actions={[
          {
            id: "submit-drafts",
            label: "Submit for review",
            variant: "primary",
            onClick: onSubmit,
            disabled: saving || draftCount === 0 || termFixCount > 0,
          },
        ]}
      />
      {termFixCount ? (
        <p data-testid="term-fix-submit-hint" style={{ color: color.status.warning, fontSize: 14 }}>
          Confirm the preferred term on {termFixCount} draft
          {termFixCount === 1 ? "" : "s"} before submit.
        </p>
      ) : null}
    </>
  );
}

function WorkspaceBody({
  state,
  liveSearch,
  onLiveSearch,
}: {
  state: ReturnType<typeof usePhraseMappings>;
  liveSearch: string;
  onLiveSearch: (value: string) => void;
}) {
  if (state.mode === "live") {
    return (
      <LiveDictionaryPane
        search={liveSearch}
        onSearchChange={onLiveSearch}
      />
    );
  }
  if (state.items.length === 0) {
    return (
      <EmptyState
        icon={<TextFieldsOutlinedIcon />}
        title={emptyTitle(state.mode)}
        body={emptyBody(state.mode)}
      />
    );
  }
  return (
    <div
      data-testid="phrase-split"
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 38%) minmax(0, 1fr)",
        minHeight: 420,
        minWidth: 0,
        gap: 20,
        overflow: "hidden",
      }}
    >
      <PhraseQueueList
        items={state.items}
        selectedKey={state.selected?.phrase_key || null}
        onSelect={state.setSelected}
      />
      {state.selected ? (
        <SpringSwap swapKey={state.selected.phrase_key}>
          <PhraseDetailPane
            phrase={state.selected}
            mode={state.mode}
            saving={state.saving}
            error={state.error}
            onSave={state.handleSave}
            onPublish={() => void state.handlePublish()}
            onSendBack={() => void state.handleSendBack()}
            onDismiss={() => void state.handleDismiss()}
          />
        </SpringSwap>
      ) : null}
    </div>
  );
}

function emptyTitle(mode: PhraseMode): string {
  if (mode === "drafts") return "No drafts yet";
  if (mode === "review") return "Nothing waiting for publish";
  return "Inbox is clear";
}

function emptyBody(mode: PhraseMode): string {
  if (mode === "drafts") {
    return "Save a mapping or an exclude from the inbox. Drafts do not change coding yet.";
  }
  if (mode === "review") {
    return "Submitted drafts land here so a different person can publish them.";
  }
  return "When the pipeline cannot code a phrase, it lands here grouped by the words.";
}
