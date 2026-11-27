import { Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { countryName, flag } from "../i18n";
import { useApp } from "../settings";

export interface Filters {
  q: string;
  sort: string;
  hours: number;
  lang: string;
  country: string;
  perspective: string;
  min_trust: number;
  min_sources: number;
  /** "all" oder "AT" (nur Themen aus Österreich) */
  region: string;
}

/**
 * Filter stehen in der Adresse (teilbar, Zurück-Taste funktioniert). Fehlt ein Wert,
 * gilt der in den Einstellungen gewählte Standard.
 */
export function useFilters(): [Filters, (patch: Partial<Filters>) => void, () => void, number] {
  const [params, setParams] = useSearchParams();
  const { settings } = useApp();
  const fd = settings.filterDefaults;
  const defaults: Filters = {
    q: "", sort: fd.sort, hours: fd.hours, lang: fd.lang, country: "", perspective: fd.perspective,
    min_trust: fd.min_trust, min_sources: fd.min_sources, region: settings.region,
  };
  const filters: Filters = {
    q: params.get("q") ?? defaults.q,
    sort: params.get("sort") ?? defaults.sort,
    hours: Number(params.get("hours") ?? defaults.hours),
    lang: params.get("lang") ?? defaults.lang,
    country: params.get("country") ?? defaults.country,
    perspective: params.get("perspective") ?? defaults.perspective,
    min_trust: Number(params.get("min_trust") ?? defaults.min_trust),
    min_sources: Number(params.get("min_sources") ?? defaults.min_sources),
    region: params.get("region") ?? defaults.region,
  };
  const set = (patch: Partial<Filters>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(patch)) {
      const def = defaults[key as keyof Filters];
      if (value === def || value === undefined || (value === "" && def === "")) next.delete(key);
      else next.set(key, String(value));
    }
    setParams(next, { replace: true });
  };
  const reset = () => {
    const next = new URLSearchParams();
    if (params.get("region")) next.set("region", params.get("region")!); // Region bleibt
    setParams(next, { replace: true });
  };
  const active = (["lang", "country", "perspective", "min_trust", "min_sources", "hours"] as const)
    .filter((k) => filters[k] !== defaults[k]).length;
  return [filters, set, reset, active];
}

function Segmented<T extends string | number>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} className={o.value === value ? "active" : ""} aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

export function FilterBar() {
  const { t, meta, settings } = useApp();
  const [filters, set, reset, activeCount] = useFilters();
  const [open, setOpen] = useState(activeCount > 0);
  const [query, setQuery] = useState(filters.q);

  useEffect(() => setQuery(filters.q), [filters.q]);
  useEffect(() => {
    const id = window.setTimeout(() => query !== filters.q && set({ q: query }), 350);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  return (
    <div className="filter-bar">
      <div className="filter-row">
        <label className="search">
          <Search size={17} aria-hidden="true" />
          <input type="search" value={query} placeholder={t.searchPlaceholder} onChange={(e) => setQuery(e.target.value)}
            aria-label={t.searchPlaceholder} />
          {query && <button className="clear" onClick={() => setQuery("")} aria-label={t.resetFilters}><X size={15} /></button>}
        </label>
        <select value={filters.sort} onChange={(e) => set({ sort: e.target.value })} aria-label={t.sort} className="select">
          <option value="relevance">{t.sortRelevance}</option>
          <option value="latest">{t.sortLatest}</option>
          <option value="sources">{t.sortSources}</option>
          <option value="trust">{t.sortTrust}</option>
        </select>
        <button className={`pill-btn${open ? " active" : ""}`} onClick={() => setOpen(!open)} aria-expanded={open}>
          <SlidersHorizontal size={16} /> {t.filters}
          {activeCount > 0 && <span className="badge">{activeCount}</span>}
        </button>
      </div>
      {open && (
        <div className="filter-panel">
          <div className="filter-group">
            <span className="filter-label">{t.timeRange}</span>
            <Segmented label={t.timeRange} value={filters.hours} onChange={(v) => set({ hours: v })} options={[
              { value: 6, label: t.hours6 }, { value: 24, label: t.hours24 }, { value: 48, label: t.hours48 },
              { value: 168, label: t.days7 },
            ]} />
          </div>
          <div className="filter-group">
            <span className="filter-label">{t.sourceLanguage}</span>
            <Segmented label={t.sourceLanguage} value={filters.lang} onChange={(v) => set({ lang: v })} options={[
              { value: "", label: t.all }, { value: "de", label: t.german }, { value: "en", label: t.english },
            ]} />
          </div>
          <div className="filter-group">
            <span className="filter-label">{t.perspective}</span>
            <select className="select" value={filters.perspective} onChange={(e) => set({ perspective: e.target.value })}
              aria-label={t.perspective}>
              <option value="all">{t.perspectiveAll}</option>
              <option value="balanced">{t.perspectiveBalanced}</option>
              <option value="left">{t.perspectiveLeft}</option>
              <option value="right">{t.perspectiveRight}</option>
              <option value="blindspot">{t.perspectiveBlindspot}</option>
            </select>
          </div>
          <div className="filter-group">
            <span className="filter-label">{t.country}</span>
            <select className="select" value={filters.country} onChange={(e) => set({ country: e.target.value })} aria-label={t.country}>
              <option value="">{t.all}</option>
              {(meta?.countries ?? []).map((c) => (
                <option key={c} value={c}>{flag(c)} {countryName(c, settings.lang)}</option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <label className="filter-label" htmlFor="min-trust">{t.minTrust}: <strong>{filters.min_trust || t.all}</strong></label>
            <input id="min-trust" type="range" min={0} max={90} step={10} value={filters.min_trust}
              onChange={(e) => set({ min_trust: Number(e.target.value) })} />
          </div>
          <div className="filter-group">
            <span className="filter-label">{t.minSources}</span>
            <Segmented label={t.minSources} value={filters.min_sources} onChange={(v) => set({ min_sources: v })} options={[
              { value: 1, label: "1+" }, { value: 2, label: "2+" }, { value: 3, label: "3+" }, { value: 5, label: "5+" },
            ]} />
          </div>
          {activeCount > 0 && (
            <button className="link-btn" onClick={() => { reset(); setQuery(""); }}>{t.resetFilters}</button>
          )}
        </div>
      )}
    </div>
  );
}
