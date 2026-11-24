import { staticApi } from "./staticApi";
import type { Digest, Meta, Source, StoryDetail, StoryList } from "./types";

/** true, wenn die App als statische Seite (GitHub Pages) gebaut wurde */
export const IS_STATIC = import.meta.env.VITE_STATIC === "1";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" }, ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignorieren */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export interface StoryQuery {
  category?: string;
  q?: string;
  lang?: string;
  country?: string;
  source?: string;
  perspective?: string;
  min_trust?: number;
  min_sources?: number;
  hours?: number;
  sort?: string;
  limit?: number;
  offset?: number;
}

function qs(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const str = search.toString();
  return str ? `?${str}` : "";
}

const serverApi = {
  meta: () => request<Meta>("/api/meta"),
  stories: (query: StoryQuery) => request<StoryList>(`/api/stories${qs(query)}`),
  story: (id: number | string) => request<StoryDetail>(`/api/stories/${id}`),
  digest: (scope: string) => request<Digest>(`/api/digest${qs({ scope })}`),
  briefing: () => request<{ day: Digest; week: Digest; categories: Digest[] }>("/api/briefing"),
  sources: () => request<{ items: Source[] }>("/api/sources"),
};

export const api: typeof serverApi = IS_STATIC ? staticApi : serverApi;
