import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { dictionaries, type Dict } from "./i18n";
import type { Lang, Meta, Voice } from "./types";

export type Theme = "system" | "light" | "dark";

export interface Settings {
  lang: Lang;
  theme: Theme;
  voice: Voice;
  rate: number;
  /** Optional manuell gewählte Gerätestimmen, Schlüssel z. B. "de-female" → voiceURI */
  deviceVoices: Record<string, string>;
}

const DEFAULTS: Settings = {
  lang: navigator.language?.toLowerCase().startsWith("de") ? "de" : (navigator.language ? "en" : "de"),
  theme: "system",
  voice: "female",
  rate: 1,
  deviceVoices: {},
};

const STORAGE_KEY = "weitblick.settings.v1";

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    /* ignorieren */
  }
  return DEFAULTS;
}

interface AppContextValue {
  settings: Settings;
  update: (patch: Partial<Settings>) => void;
  t: Dict;
  meta: Meta | null;
  reloadMeta: () => Promise<Meta | null>;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [meta, setMeta] = useState<Meta | null>(null);

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const reloadMeta = useCallback(async () => {
    try {
      const m = await api.meta();
      setMeta(m);
      return m;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    reloadMeta();
    const id = window.setInterval(reloadMeta, 60_000);
    return () => window.clearInterval(id);
  }, [reloadMeta]);

  useEffect(() => {
    const root = document.documentElement;
    if (settings.theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", settings.theme);
    root.lang = settings.lang;
  }, [settings.theme, settings.lang]);

  const value = useMemo(
    () => ({ settings, update, t: dictionaries[settings.lang], meta, reloadMeta }),
    [settings, update, meta, reloadMeta],
  );
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp außerhalb von AppProvider");
  return ctx;
}

export function useCategoryName() {
  const { meta, settings } = useApp();
  return (slug: string) => meta?.categories.find((c) => c.slug === slug)?.[settings.lang] ?? slug;
}
