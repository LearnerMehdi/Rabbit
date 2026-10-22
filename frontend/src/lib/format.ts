export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Dialog titles: truncate past ~60 characters with … */
export function truncate(s: string, n = 60): string {
  return s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s;
}

export function titleFromFileName(name: string): string {
  return name
    .replace(/\.pdf$/i, "")
    .replace(/[_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
