"use client";

interface Props {
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: "danger" | "primary";
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  variant = "primary",
  onConfirm,
  onCancel,
}: Props) {
  const confirmStyle =
    variant === "danger"
      ? { background: "#dc2626", color: "#fff", border: "none" }
      : { background: "#4f46e5", color: "#fff", border: "none" };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 3000,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          borderRadius: 12,
          padding: 24,
          maxWidth: 420,
          boxShadow: "0 20px 60px rgba(0,0,0,0.2)",
        }}
      >
        <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12, color: "#0f172a" }}>
          {title}
        </h3>
        <p style={{ fontSize: 14, color: "#64748b", lineHeight: 1.6, marginBottom: 20 }}>
          {body}
        </p>
        <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            style={{
              padding: "8px 16px",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              background: "#fff",
              fontSize: 14,
              cursor: "pointer",
              color: "#475569",
            }}
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: "8px 16px",
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
              ...confirmStyle,
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
