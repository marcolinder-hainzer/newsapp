export type Lang = "de" | "en";
export type Voice = "female" | "male";
export type Bilingual<T = string> = Record<Lang, T>;

export interface Category {
  slug: string;
  de: string;
  en: string;
  icon: string;
}

export interface Meta {
  app: { name: string; version: string };
  categories: Category[];
  countries: string[];
  llm: { enabled: boolean; model: string | null };
  tts: { server: boolean; provider: string | null; label: string | null; voices: Record<Lang, Record<Voice, string>> | null };
  last_update: string | null;
  cycle_running: boolean;
  refresh_interval_minutes: number;
  stats: { stories_24h: number; articles_24h: number; sources: number };
}

export type TrustLabel = "very_high" | "high" | "medium" | "low";

export interface StoryItem {
  id: number;
  category: string;
  title: Bilingual;
  teaser: Bilingual;
  title_is_original: Bilingual<boolean>;
  headline_lang: Lang | null;
  image_url: string | null;
  first_seen: string;
  last_updated: string;
  article_count: number;
  source_count: number;
  languages: Lang[];
  countries: string[];
  bias: { left: number; center: number; right: number };
  blindspot: "left" | "right" | null;
  trust: { score: number; label: TrustLabel };
  summary_status: "none" | "extractive" | "llm";
  top_sources: { id: string; name: string }[];
}

export interface SummaryPart {
  available: boolean;
  title?: string;
  summary?: string;
  key_points?: string[];
  context?: string;
}

export interface Source {
  id: string;
  name: string;
  homepage: string | null;
  country: string | null;
  language: Lang;
  bias: "left" | "lean_left" | "center" | "lean_right" | "right";
  bias_bucket: "left" | "center" | "right";
  reliability: number;
  factuality: "very_high" | "high" | "mostly" | "mixed" | "low";
  ownership: string | null;
  type: string | null;
  note: string;
  articles_24h?: number;
  feeds?: number;
  errors?: number;
}

export interface Article {
  id: number;
  url: string;
  title: string;
  description: string | null;
  image_url: string | null;
  language: Lang;
  is_opinion: boolean;
  published_at: string;
  source: Source;
}

export interface TrustDetail {
  score: number;
  label: TrustLabel;
  components?: { reliability: number; corroboration: number; diversity: number; content: number };
  weights?: Record<string, number>;
  content_method?: "ai" | "heuristic";
  notes?: Bilingual<string[]>;
}

export interface StoryDetail extends Omit<StoryItem, "trust"> {
  summary: {
    generated_by: "llm" | "extractive" | null;
    model: string | null;
    generated_at: string | null;
    de: SummaryPart;
    en: SummaryPart;
  };
  trust: TrustDetail;
  articles: Article[];
  speech: Bilingual<{ text: string; lang: Lang }>;
  can_generate_summary: boolean;
}

export interface DigestContent {
  headline: string;
  overview: string;
  items: { story_id: number; text: string }[];
}

export interface Digest {
  scope: string;
  title: Bilingual;
  generated_at: string;
  generated_by: "llm" | "template";
  content: Partial<Record<Lang, DigestContent>>;
  stories: StoryItem[];
  speech: Bilingual;
}

export interface StoryList {
  total: number;
  offset: number;
  limit: number;
  items: StoryItem[];
}
