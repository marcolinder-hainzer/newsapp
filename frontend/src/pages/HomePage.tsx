import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { CategoryIcon } from "../components/CategoryIcon";
import { DigestCard } from "../components/DigestCard";
import { FilterBar, useFilters } from "../components/FilterBar";
import { ErrorState, SkeletonCards } from "../components/States";
import { StoryCard } from "../components/StoryCard";
import { timeAgo } from "../i18n";
import { useApp, useCategoryName, useOrderedCategories, type HomeSection } from "../settings";
import type { Digest, StoryItem } from "../types";

const PAGE = 24;

export function HomePage() {
  const { slug } = useParams();
  const { t, meta, reloadMeta, settings } = useApp();
  const categoryName = useCategoryName();
  const visibleCategories = useOrderedCategories();
  const [filters] = useFilters();
  const austria = filters.region === "AT";
  const [period, setPeriod] = useState<"day" | "week">("day");
  const scope = slug ? `category:${slug}` : austria ? "region:AT" : `top:${period}`;

  const [digest, setDigest] = useState<Digest | null>(null);
  const [stories, setStories] = useState<StoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const requestId = useRef(0);

  // Ausgeblendete Kategorien erscheinen auch nicht unter „Alle Kategorien“
  const categoryFilter = slug
    ?? (settings.hiddenCategories.length && visibleCategories.length ? visibleCategories.map((c) => c.slug).join(",") : undefined);
  const query = {
    ...filters,
    region: austria ? "AT" : undefined,
    category: categoryFilter,
    exclude_sources: settings.hiddenSources.join(",") || undefined,
  };
  const queryKey = JSON.stringify(query);

  const loadStories = useCallback(async (offset = 0) => {
    const id = ++requestId.current;
    if (offset === 0) setLoading(true);
    setError(null);
    try {
      const res = await api.stories({ ...JSON.parse(queryKey), limit: PAGE, offset });
      if (id !== requestId.current) return;
      setStories((prev) => (offset === 0 ? res.items : [...prev, ...res.items]));
      setTotal(res.total);
      setLoadedAt(meta?.last_update ?? null);
    } catch (e) {
      if (id === requestId.current) setError((e as Error).message);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [queryKey, meta?.last_update]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadStories(0);
  }, [queryKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    setDigest(null);
    api.digest(scope).then((d) => !cancelled && setDigest(d)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [scope, loadedAt]);

  // Erster Start: warten, bis der erste Abruf durch ist
  const waiting = !meta?.last_update && !loading && stories.length === 0;
  useEffect(() => {
    if (!waiting) return;
    const id = window.setInterval(async () => {
      const m = await reloadMeta();
      if (m?.last_update) loadStories(0);
    }, 8000);
    return () => window.clearInterval(id);
  }, [waiting, reloadMeta, loadStories]);

  const hasNews = !!meta?.last_update && !!loadedAt && meta.last_update !== loadedAt;
  const category = meta?.categories.find((c) => c.slug === slug);

  const sections: Record<HomeSection, ReactNode> = {
    briefing: digest && (digest.stories.length > 0 || !slug) && (
      <DigestCard key="briefing" digest={digest} tabs={!slug && !austria && (
        <div className="segmented" role="tablist" aria-label={t.topStories}>
          <button role="tab" aria-selected={period === "day"} className={period === "day" ? "active" : ""}
            onClick={() => setPeriod("day")}>{t.topDay}</button>
          <button role="tab" aria-selected={period === "week"} className={period === "week" ? "active" : ""}
            onClick={() => setPeriod("week")}>{t.topWeek}</button>
        </div>
      )} />
    ),
    filters: (
      <div key="filters" className="home-section">
        <FilterBar />
        {hasNews && (
          <button className="new-stories" onClick={() => loadStories(0)}>
            <RefreshCw size={15} /> {t.newStories}
          </button>
        )}
      </div>
    ),
    stats: meta && (
      <p key="stats" className="muted small stats-line">
        {meta.last_update && <>{t.updated} {timeAgo(meta.last_update, t)} · </>}
        {t.stats(meta.stats.stories_24h, meta.stats.articles_24h, meta.stats.sources)}
        {meta.cycle_running && <> · {t.updating}</>}
      </p>
    ),
    stories: (
      <div key="stories" className="home-section">
        {error && <ErrorState message={error} onRetry={() => loadStories(0)} />}
        {loading && stories.length === 0 && <SkeletonCards />}
        {waiting && <div className="state">{t.waitingFirstFetch}</div>}
        {!loading && !error && !waiting && stories.length === 0 && <div className="state">{t.noStories}</div>}
        {stories.length > 0 && (
          <div className={`story-grid layout-${settings.cardLayout}`}>
            {stories.map((s, i) => (
              <StoryCard key={s.id} story={s}
                featured={i === 0 && filters.sort === "relevance" && settings.cardLayout === "grid"} />
            ))}
          </div>
        )}
        {stories.length < total && (
          <div className="center">
            <button className="pill-btn" onClick={() => loadStories(stories.length)}>{t.loadMore}</button>
          </div>
        )}
      </div>
    ),
  };

  return (
    <div className="page">
      {(slug && category) || austria ? (
        <h1 className="page-title">
          {slug && category ? <><CategoryIcon icon={category.icon} size={26} /> {categoryName(slug)}</> : null}
          {austria && <span className="title-region"><span className="flag-at" aria-hidden="true" />{t.austria}</span>}
        </h1>
      ) : null}
      {settings.homeOrder.filter((s) => !settings.hiddenHome.includes(s)).map((s) => sections[s])}
    </div>
  );
}
