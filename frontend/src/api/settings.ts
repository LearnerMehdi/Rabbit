/** Knobs for the mock backend, changed from the dev panel and kept in localStorage. */

export type ChatMode = "unavailable" | "echo" | "error";

export interface MockSettings {
  /** chat behaviour; "unavailable" is the default until the LLM is connected */
  chatMode: ChatMode;
  /** multiplier on simulated preparation time (1 = backend-like ~16 pages/s) */
  speed: number;
  /** the next added or re-indexed book fails during embedding */
  failNext: boolean;
  /** simulated round-trip latency for every call, ms */
  latencyMs: number;
}

export const DEFAULT_SETTINGS: MockSettings = {
  chatMode: "unavailable",
  speed: 1,
  failNext: false,
  latencyMs: 150,
};

const KEY = "orange-reader-mock-settings";
const listeners = new Set<(s: MockSettings) => void>();
let current: MockSettings = load();

function load(): MockSettings {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : { ...DEFAULT_SETTINGS };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function getSettings(): MockSettings {
  return current;
}

export function setSettings(patch: Partial<MockSettings>): void {
  current = { ...current, ...patch };
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    /* private mode: settings last for this tab only */
  }
  listeners.forEach((l) => l(current));
}

export function onSettings(cb: (s: MockSettings) => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}
