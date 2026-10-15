"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * A per-browser convenience value (sidebar state, panel width, selected portfolio) kept in
 * localStorage and shared between components and tabs. It never holds account data or tokens; when
 * storage is unavailable the value simply is not remembered.
 */
const EVENT = "ws-local-storage";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function useStored(key: string): [string | null, (value: string) => void] {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const listener = (e: Event) => {
        if (e.type === EVENT || (e as StorageEvent).key === key) onChange();
      };
      window.addEventListener("storage", listener);
      window.addEventListener(EVENT, listener);
      return () => {
        window.removeEventListener("storage", listener);
        window.removeEventListener(EVENT, listener);
      };
    },
    [key],
  );
  const value = useSyncExternalStore(subscribe, () => read(key), () => null);
  const set = useCallback(
    (next: string) => {
      try {
        localStorage.setItem(key, next);
      } catch {
        // Not remembered.
      }
      window.dispatchEvent(new Event(EVENT));
    },
    [key],
  );
  return [value, set];
}
