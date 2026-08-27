/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import type { CSSProperties } from "react";
import { motion as fm } from "framer-motion";
import {
  frostStyle,
  springOrInstant,
  springs,
  tapScale,
  useMotion,
  useReducedTransparency,
} from "@leo/design-system";
import { color, typography } from "@leo/design-system/tokens";

export function PhraseDetailSaveDock({
  mode,
  canSave,
  saving,
  exclude,
  onSave,
  onPublish,
  onSendBack,
  onDismiss,
}: {
  mode: "inbox" | "drafts" | "review";
  canSave: boolean;
  saving: boolean;
  exclude: boolean;
  onSave: () => void;
  onPublish?: () => void;
  onSendBack?: () => void;
  onDismiss?: () => void;
}) {
  const { reducedMotion } = useMotion();
  const frost = frostStyle(useReducedTransparency(), "light");
  const disabled = !canSave || saving;

  return (
    <div data-testid="phrase-save-dock" style={dockStyle(frost)}>
      <span style={dockHintStyle()}>Drafts do not change coding yet.</span>
      {mode === "review" ? (
        <ReviewDockButtons
          saving={saving}
          reducedMotion={reducedMotion}
          onPublish={onPublish}
          onSendBack={onSendBack}
        />
      ) : (
        <>
          {onDismiss ? (
            <fm.button
              type="button"
              data-testid="phrase-dismiss-queue"
              onClick={onDismiss}
              disabled={saving}
              whileTap={saving ? undefined : tapScale(reducedMotion)}
              transition={springOrInstant(reducedMotion, springs.press)}
              style={ghostBtn(color.status.danger)}
            >
              Remove from queue
            </fm.button>
          ) : null}
          <SaveDraftButton
            disabled={disabled}
            saving={saving}
            exclude={exclude}
            reducedMotion={reducedMotion}
            onSave={onSave}
          />
        </>
      )}
    </div>
  );
}

function ReviewDockButtons({
  saving,
  reducedMotion,
  onPublish,
  onSendBack,
}: {
  saving: boolean;
  reducedMotion: boolean;
  onPublish?: () => void;
  onSendBack?: () => void;
}) {
  return (
    <>
      <fm.button
        type="button"
        onClick={onSendBack}
        disabled={saving}
        whileTap={saving ? undefined : tapScale(reducedMotion)}
        transition={springOrInstant(reducedMotion, springs.press)}
        style={ghostBtn()}
      >
        Send back
      </fm.button>
      <fm.button
        type="button"
        onClick={onPublish}
        disabled={saving}
        whileTap={saving ? undefined : tapScale(reducedMotion)}
        transition={springOrInstant(reducedMotion, springs.press)}
        style={primaryBtn(color.brand.primary, saving)}
      >
        Publish
      </fm.button>
    </>
  );
}

function SaveDraftButton({
  disabled,
  saving,
  exclude,
  reducedMotion,
  onSave,
}: {
  disabled: boolean;
  saving: boolean;
  exclude: boolean;
  reducedMotion: boolean;
  onSave: () => void;
}) {
  const label = saving ? "Saving" : exclude ? "Save exclude draft" : "Save mapping draft";
  return (
    <fm.button
      type="button"
      onClick={onSave}
      disabled={disabled}
      whileTap={disabled ? undefined : tapScale(reducedMotion)}
      transition={springOrInstant(reducedMotion, springs.press)}
      style={primaryBtn(exclude ? color.status.danger : color.brand.primary, disabled)}
    >
      {label}
    </fm.button>
  );
}

function dockStyle(frost: CSSProperties): CSSProperties {
  return {
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: 12,
    margin: "0 -22px 0",
    padding: "12px 22px 16px",
    borderTop: "1px solid " + color.surface.divider,
    ...frost,
  };
}

function dockHintStyle(): CSSProperties {
  return {
    marginRight: "auto",
    fontSize: 13,
    color: color.text.caption,
    fontFamily: typography.fontFamily.body,
  };
}

function ghostBtn(colorOverride?: string): CSSProperties {
  return {
    border: "1px solid " + (colorOverride || color.surface.divider),
    background: color.surface.raised,
    borderRadius: 10,
    padding: "10px 14px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: typography.fontFamily.body,
    color: colorOverride || color.text.primary,
  };
}

function primaryBtn(background: string, disabled: boolean): CSSProperties {
  if (disabled) {
    return {
      minWidth: 168,
      padding: "10px 18px",
      border: "1px solid " + color.text.secondary,
      borderRadius: 10,
      background: color.surface.divider,
      color: color.text.secondary,
      fontWeight: 600,
      fontFamily: typography.fontFamily.body,
      cursor: "not-allowed",
    };
  }
  return {
    minWidth: 168,
    padding: "10px 18px",
    border: 0,
    borderRadius: 10,
    background,
    color: color.brand.onBrand,
    fontWeight: 600,
    fontFamily: typography.fontFamily.body,
    cursor: "pointer",
  };
}
