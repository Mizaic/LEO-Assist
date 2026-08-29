export function initials(nameOrEmail: string): string {
  const parts = nameOrEmail.split(/[\s@.]+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");
}

export function avatarColor(str: string): string {
  const palette = [
    "#1565c0",
    "#2e7d32",
    "#6a1b9a",
    "#c62828",
    "#e65100",
    "#00695c",
    "#37474f",
  ];
  let h = 0;
  for (let i = 0; i < str.length; i++) h = str.charCodeAt(i) + ((h << 5) - h);
  return palette[Math.abs(h) % palette.length];
}

export function relativeTime(isoStr?: string | null): string {
  if (!isoStr) return "Never";
  const mins = Math.floor((Date.now() - new Date(isoStr).getTime()) / 60_000);
  if (mins < 2) return "Just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function friendlyRole(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
