import { useEffect, useRef, useState } from "react";
import { api, type BookProgress } from "../api";
import { getSettings, onSettings, type MockSettings } from "../api/settings";

export function useBookProgress(bookId: string, initial: BookProgress): BookProgress {
  const [p, setP] = useState(initial);
  useEffect(() => {
    setP(initial);
    return api.onBookProgress(bookId, setP);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId]);
  return p;
}

export function useMockSettings(): MockSettings {
  const [s, setS] = useState(getSettings);
  useEffect(() => onSettings(setS), []);
  return s;
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Calls fn at most once per `ms`, always delivering the latest arguments. */
export function useThrottled<A extends unknown[]>(fn: (...args: A) => void, ms: number) {
  const last = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const latest = useRef(fn);
  latest.current = fn;
  useEffect(() => () => clearTimeout(timer.current), []);
  return (...args: A) => {
    const wait = last.current + ms - Date.now();
    clearTimeout(timer.current);
    if (wait <= 0) {
      last.current = Date.now();
      latest.current(...args);
    } else {
      timer.current = setTimeout(() => {
        last.current = Date.now();
        latest.current(...args);
      }, wait);
    }
  };
}
