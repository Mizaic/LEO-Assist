/** Unique React keys for context-card attribute rows. */

export function attributeRowKey(
  row: { name: string; id?: string },
  index: number,
): string {
  const base = row.id || row.name;
  return `${base}-${row.name}-${index}`;
}
