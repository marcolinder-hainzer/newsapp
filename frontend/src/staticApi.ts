/**
 * Statischer Datenzugriff für GitHub Pages: Die GitHub Action legt alle Daten als JSON-Dateien ab,
 * Filter, Suche und Sortierung laufen direkt im Browser (gleiche Logik wie im Backend).
 */
import type { StoryQuery } from "./api";
import type { Briefing, Digest, Meta, Source, StoryDetail, StoryItem, StoryList } from "./types";

export interface StaticStory extends StoryItem {
  coverage: number;
  source_ids: string[];
  search: string;
}

const DATA = `${import.meta.env.BASE_URL}data/`;

export class StaticApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function getJson<T>(path: string): Promise<T> {
  // "no-cache": immer beim Server nachfragen (ETag), damit neue Meldungen sofort sichtbar sind
  const res = await fetch(DATA + path, { cache: "no-cache" });
  if (!res.ok) throw new StaticApiError(res.status, res.status === 404 ? "Nicht gefunden" : res.statusText);
  return res.json() as Promise<T>;
}

const cache = new Map<string, { at: number; data: Promise<StaticStory[]> }>();

function loadList(file: "stories-recent.json" | "stories-older.json"): Promise<StaticStory[]> {
  const hit = cache.get(file);
  if (hit && Date.now() - hit.at < 60_000) return hit.data;
  const data = getJson<{ items: StaticStory[] }>(file).then((r) => r.items);
  cache.set(file, { at: Date.now(), data });
  data.catch(() => cache.delete(file));
  return data;
}

export function importance(s: StaticStory, now: number, halfLifeHours = 12): number {
  const last = Date.parse(s.last_updated) || now;
  const first = Date.parse(s.first_seen) || last;
  const ageH = Math.max(0, (0.6 * (now - last) + 0.4 * (now - first)) / 3_600_000);
  const trustFactor = 0.6 + (0.4 * (s.trust.score || 50)) / 100;
  return (s.coverage || 0) * trustFactor * 0.5 ** (ageH / halfLifeHours);
}

export function queryStories(all: StaticStory[], query: StoryQuery, now = Date.now()): StoryList {
  const minSources = Math.max(1, query.min_sources ?? 1);
  const hours = query.hours ?? 48;
  const categories = (query.category ?? "").split(",").filter(Boolean);
  const terms = (query.q ?? "").toLowerCase().split(/\s+/).filter(Boolean).slice(0, 6);
  const excluded = (query.exclude_sources ?? "").split(",").filter(Boolean);

  let items = all.filter((s) => {
    if (s.source_count < minSources) return false;
    if (hours && Date.parse(s.last_updated) < now - hours * 3_600_000) return false;
    if (categories.length && !categories.includes(s.category)) return false;
    if (query.min_trust && s.trust.score < query.min_trust) return false;
    if ((query.lang === "de" || query.lang === "en") && !s.languages.includes(query.lang)) return false;
    if (query.country && !s.countries.includes(query.country.toUpperCase())) return false;
    if (query.source && !s.source_ids.includes(query.source)) return false;
    if (query.region && !(s.regions ?? []).includes(query.region.toUpperCase())) return false;
    if (excluded.length && s.source_ids.every((id) => excluded.includes(id))) return false;
    if (terms.length) {
      const haystack = `${s.title.de} ${s.title.en} ${s.teaser.de} ${s.teaser.en} ${s.search}`.toLowerCase();
      if (!terms.every((t) => haystack.includes(t))) return false;
    }
    return true;
  });

  const { perspective = "all" } = query;
  if (perspective === "balanced") {
    items = items.filter((s) => s.bias.left && s.bias.center && s.bias.right);
  } else if (perspective === "left" || perspective === "right") {
    const other = perspective === "left" ? "right" : "left";
    items = items.filter((s) => {
      const total = s.bias.left + s.bias.center + s.bias.right;
      const own = s.bias[perspective];
      return (own > 0 && own >= 0.6 * total) || (own >= 2 && s.bias[other] === 0);
    });
  } else if (perspective === "blindspot") {
    items = items.filter((s) => s.blindspot);
  }

  const sort = query.sort ?? "relevance";
  if (sort === "latest") items.sort((a, b) => b.last_updated.localeCompare(a.last_updated));
  else if (sort === "sources") items.sort((a, b) => b.source_count - a.source_count || b.last_updated.localeCompare(a.last_updated));
  else if (sort === "trust") items.sort((a, b) => b.trust.score - a.trust.score || b.source_count - a.source_count);
  else items.sort((a, b) => importance(b, now) - importance(a, now));

  const offset = query.offset ?? 0;
  const limit = query.limit ?? 30;
  return { total: items.length, offset, limit, items: items.slice(offset, offset + limit) };
}

export const staticApi = {
  meta: () => getJson<Meta>("meta.json"),
  stories: async (query: StoryQuery): Promise<StoryList> => {
    const hours = query.hours ?? 48;
    const lists = [loadList("stories-recent.json")];
    if (!hours || hours > 48) lists.push(loadList("stories-older.json"));
    const all = (await Promise.all(lists)).flat();
    return queryStories(all, query);
  },
  story: (id: number | string) => getJson<StoryDetail>(`stories/${id}.json`),
  digest: (scope: string) => getJson<Digest>(`digests/${scope.replace(":", "-")}.json`),
  briefing: () => getJson<Briefing>("briefing.json"),
  sources: () => getJson<{ items: Source[] }>("sources.json"),
};
