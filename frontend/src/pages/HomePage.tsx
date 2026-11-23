import { Info, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { CategoryIcon } from "../components/CategoryIcon";
import { DigestCard } from "../components/DigestCard";
import { FilterBar, useFilters } from "../components/FilterBar";
import { ErrorState, SkeletonCards } from "../components/States";
import { StoryCard } from "../components/StoryCard";
import { useApp, useCategoryName } from "../settings";
import type { Digest, StoryItem } from "../types";

const PAGE = 24;

export function HomePage() {
  const { slug } = useParams();
  const { t, meta, reloadMeta } = useApp();
  const categoryName = useCategoryName();
  const [filters] = useFilters();
  const [period, setPeriod] = useState<"day" | "week">("day");
  const scope = slug ? `category:${slug}` : `top:${period}`;

  const [digest, setDigest] = useState<Digest | null>(null);
  const [stories, setStories] = useState<StoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [aiNoticeHidden, setAiNoticeHidden] = useState(() => localStorage.getItem("weitblick.aiNotice") === "hidden");
  const requestId = useRef(0);

  const query = { ...filters, category: slug };
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

  return (
    <div className="page">
      {meta && !meta.llm.enabled && !aiNoticeHidden && (
        <div className="notice">
          <Info size={16} aria-hidden="true" />
          <span>{t.aiOff}</span>
          <button className="icon-btn" aria-label={t.close} onClick={() => {
            localStorage.setItem("weitblick.aiNotice", "hidden");
            setAiNoticeHidden(true);
          }}><X size={16} /></button>
        </div>
      )}

      {slug && category && (
        <h1 className="page-title"><CategoryIcon icon={category.icon} size={26} /> {categoryName(slug)}</h1>
      )}

      {digest && (digest.stories.length > 0 || !slug) && (
        <DigestCard digest={digest} tabs={!slug && (
          <div className="segmented" role="tablist" aria-label={t.topStories}>
            <button role="tab" aria-selected={period === "day"} className={period === "day" ? "active" : ""}
              onClick={() => setPeriod("day")}>{t.topDay}</button>
            <button role="tab" aria-selected={period === "week"} className={period === "week" ? "active" : ""}
              onClick={() => setPeriod("week")}>{t.topWeek}</button>
          </div>
        )} />
      )}

      <FilterBar />

      {hasNews && (
        <button className="new-stories" onClick={() => loadStories(0)}>
          <RefreshCw size={15} /> {t.newStories}
        </button>
      )}

      {meta && (
        <p className="muted small stats-line">
          {t.stats(meta.stats.stories_24h, meta.stats.articles_24h, meta.stats.sources)}
          {meta.cycle_running && <> · {t.updating}</>}
        </p>
      )}

      {error && <ErrorState message={error} onRetry={() => loadStories(0)} />}
      {loading && stories.length === 0 && <SkeletonCards />}
      {waiting && <div className="state">{t.waitingFirstFetch}</div>}
      {!loading && !error && !waiting && stories.length === 0 && <div className="state">{t.noStories}</div>}

      {stories.length > 0 && (
        <div className="story-grid">
          {stories.map((s, i) => <StoryCard key={s.id} story={s} featured={i === 0 && filters.sort === "relevance"} />)}
        </div>
      )}
      {stories.length < total && (
        <div className="center">
          <button className="pill-btn" onClick={() => loadStories(stories.length)}>{t.loadMore}</button>
        </div>
      )}
    </div>
  );
}
