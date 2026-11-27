import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { dictionaries, type Dict } from "./i18n";
import type { Lang, Meta, Voice } from "./types";

export type Theme = "system" | "light" | "dark";
export type VoiceEngine = "natural" | "device";
export type Accent = "blue" | "teal" | "green" | "violet" | "red" | "orange" | "graphite";
export type Corners = "square" | "round" | "extra";
export type CardStyle = "shadow" | "border" | "flat";
export type FontScale = "s" | "m" | "l" | "xl";
export type Density = "compact" | "normal" | "airy";
export type CardLayout = "grid" | "list";
export type Region = "all" | "AT";
export type HomeSection = "briefing" | "filters" | "stats" | "stories";
export type CardElement = "image" | "teaser" | "bias" | "trust" | "sources";

export interface FilterDefaults {
  hours: number;
  sort: string;
  min_trust: number;
  min_sources: number;
  lang: string;
  perspective: string;
}

/** Alle Einstellungen – gespeichert nur auf diesem Gerät (localStorage). */
export interface Settings {
  lang: Lang;
  theme: Theme;
  // Vorlesen
  voice: Voice;
  rate: number;
  voiceEngine: VoiceEngine;
  deviceVoices: Record<string, string>;
  // Start & Inhalte
  startPage: string;
  region: Region;
  categoryOrder: string[];
  hiddenCategories: string[];
  homeOrder: HomeSection[];
  hiddenHome: HomeSection[];
  hiddenSources: string[];
  filterDefaults: FilterDefaults;
  // Aussehen
  accent: Accent;
  corners: Corners;
  cardStyle: CardStyle;
  fontScale: FontScale;
  density: Density;
  cardLayout: CardLayout;
  hiddenCardElements: CardElement[];
}

export const HOME_SECTIONS: HomeSection[] = ["briefing", "filters", "stats", "stories"];
export const CARD_ELEMENTS: CardElement[] = ["image", "teaser", "bias", "trust", "sources"];
export const FILTER_DEFAULTS: FilterDefaults = {
  hours: 48, sort: "relevance", min_trust: 0, min_sources: 1, lang: "", perspective: "all",
};

export const DEFAULTS: Settings = {
  lang: navigator.language?.toLowerCase().startsWith("de") ? "de" : (navigator.language ? "en" : "de"),
  theme: "system",
  voice: "female",
  rate: 1,
  voiceEngine: "natural",
  deviceVoices: {},
  startPage: "/",
  region: "all",
  categoryOrder: [],
  hiddenCategories: [],
  homeOrder: HOME_SECTIONS,
  hiddenHome: [],
  hiddenSources: [],
  filterDefaults: FILTER_DEFAULTS,
  accent: "blue",
  corners: "round",
  cardStyle: "shadow",
  fontScale: "m",
  density: "normal",
  cardLayout: "grid",
  hiddenCardElements: [],
};

export const LOOK_KEYS = ["theme", "accent", "corners", "cardStyle", "fontScale", "density", "cardLayout",
  "hiddenCardElements"] as const;

const STORAGE_KEY = "weitblick.settings.v1";

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const stored = JSON.parse(raw);
      const merged = { ...DEFAULTS, ...stored, filterDefaults: { ...FILTER_DEFAULTS, ...(stored.filterDefaults ?? {}) } };
      // neue Startseiten-Bereiche ergänzen, die es in älteren Einstellungen noch nicht gab
      merged.homeOrder = [...merged.homeOrder.filter((s: HomeSection) => HOME_SECTIONS.includes(s)),
        ...HOME_SECTIONS.filter((s) => !merged.homeOrder.includes(s))];
      return merged;
    }
  } catch {
    /* ignorieren */
  }
  return DEFAULTS;
}

interface AppContextValue {
  settings: Settings;
  update: (patch: Partial<Settings>) => void;
  reset: (keys?: readonly (keyof Settings)[]) => void;
  t: Dict;
  meta: Meta | null;
  reloadMeta: () => Promise<Meta | null>;
}

const AppContext = createContext<AppContextValue | null>(null);

/** Darstellung als data-Attribute am <html>-Element – die Farben & Formen stehen in styles.css. */
export function applyLook(s: Pick<Settings, "theme" | "accent" | "corners" | "cardStyle" | "fontScale" | "density" | "lang">) {
  const root = document.documentElement;
  if (s.theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", s.theme);
  root.dataset.accent = s.accent;
  root.dataset.corners = s.corners;
  root.dataset.card = s.cardStyle;
  root.dataset.font = s.fontScale;
  root.dataset.density = s.density;
  root.lang = s.lang;
}

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

  const reset = useCallback((keys?: readonly (keyof Settings)[]) => {
    setSettings((prev) => {
      const next = { ...prev };
      for (const key of keys ?? (Object.keys(DEFAULTS) as (keyof Settings)[])) {
        if (key === "lang") continue; // Sprache bleibt erhalten
        (next as Record<string, unknown>)[key] = DEFAULTS[key];
      }
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

  useEffect(() => applyLook(settings), [settings]);

  const value = useMemo(
    () => ({ settings, update, reset, t: dictionaries[settings.lang], meta, reloadMeta }),
    [settings, update, reset, meta, reloadMeta],
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

/** Kategorien in der vom Nutzer gewählten Reihenfolge (ausgeblendete optional weglassen). */
export function useOrderedCategories(includeHidden = false) {
  const { meta, settings } = useApp();
  const all = meta?.categories ?? [];
  const order = settings.categoryOrder;
  const sorted = [...all].sort((a, b) => {
    const ia = order.indexOf(a.slug);
    const ib = order.indexOf(b.slug);
    return (ia < 0 ? 999 + all.indexOf(a) : ia) - (ib < 0 ? 999 + all.indexOf(b) : ib);
  });
  return includeHidden ? sorted : sorted.filter((c) => !settings.hiddenCategories.includes(c.slug));
}
