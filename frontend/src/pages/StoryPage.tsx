import { ArrowLeft, ExternalLink, EyeOff, Info, LoaderCircle, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ttsUrl } from "../api";
import type { Track } from "../audio/player";
import { BiasBar } from "../components/BiasBar";
import { ListenButton } from "../components/ListenButton";
import { ErrorState, Loading } from "../components/States";
import { TrustBadge, TrustPanel } from "../components/TrustBadge";
import { countryName, flag, timeAgo } from "../i18n";
import { useApp, useCategoryName } from "../settings";
import type { Lang, StoryDetail } from "../types";

type BucketFilter = "all" | "left" | "center" | "right";

export function StoryPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t, settings, meta } = useApp();
  const categoryName = useCategoryName();
  const [story, setStory] = useState<StoryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [summaryLang, setSummaryLang] = useState<Lang>(settings.lang);
  const [bucket, setBucket] = useState<BucketFilter>("all");

  useEffect(() => setSummaryLang(settings.lang), [settings.lang]);

  useEffect(() => {
    let cancelled = false;
    setStory(null);
    setError(null);
    api.story(id!).then(async (s) => {
      if (cancelled) return;
      setStory(s);
      window.scrollTo({ top: 0 });
      // Fehlt eine KI-Zusammenfassung, wird sie beim Öffnen erstellt
      if (s.can_generate_summary && s.summary.generated_by !== "llm") {
        setGenerating(true);
        try {
          const updated = await api.summarize(s.id);
          if (!cancelled) setStory(updated);
        } catch {
          /* Auszug bleibt sichtbar */
        } finally {
          if (!cancelled) setGenerating(false);
        }
      }
    }).catch((e) => !cancelled && setError(e.status === 404 ? t.storyNotFound : e.message));
    return () => {
      cancelled = true;
    };
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const articles = useMemo(
    () => (story?.articles ?? []).filter((a) => bucket === "all" || a.source.bias_bucket === bucket),
    [story, bucket],
  );

  if (error) return <div className="page"><ErrorState message={error} /></div>;
  if (!story) return <div className="page"><Loading /></div>;

  const requested = story.summary[summaryLang];
  const fallbackLang: Lang = summaryLang === "de" ? "en" : "de";
  const part = requested?.available ? requested : story.summary[fallbackLang]?.available ? story.summary[fallbackLang] : null;
  const shownLang: Lang = requested?.available ? summaryLang : fallbackLang;
  const title = part?.title || story.title[summaryLang];

  const track: Track = {
    key: `story-${story.id}-${summaryLang}`,
    title,
    lang: summaryLang,
    href: `/meldung/${story.id}`,
    getSpeech: async () => story.speech[summaryLang],
    serverUrl: (voice) => ttsUrl.story(story.id, summaryLang, voice),
  };

  return (
    <div className="page story-page">
      <button className="link-btn back" onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/"))}>
        <ArrowLeft size={16} /> {t.back}
      </button>

      <div className="story-layout">
        <article className="story-main">
          <div className="story-meta">
            <Link to={`/kategorie/${story.category}`} className="chip-cat">{categoryName(story.category)}</Link>
            <span className="muted">{t.updated} {timeAgo(story.last_updated, t)}</span>
            <span className="muted">· {t.sources(story.source_count)} · {t.articles(story.article_count)}</span>
          </div>
          <h1 className="story-headline" lang={shownLang}>{title}</h1>

          <div className="story-badges">
            <TrustBadge score={story.trust.score} label={story.trust.label} />
            {story.blindspot && (
              <span className="blindspot"><EyeOff size={14} /> {story.blindspot === "left" ? t.blindspotLeft : t.blindspotRight}</span>
            )}
          </div>

          {story.image_url && (
            <figure className="story-hero">
              <img src={story.image_url} alt="" referrerPolicy="no-referrer"
                onError={(e) => ((e.currentTarget.parentElement as HTMLElement).style.display = "none")} />
            </figure>
          )}

          <section className="panel summary-panel" aria-labelledby="summary-heading">
            <div className="summary-head">
              <h2 id="summary-heading" className="panel-title">{t.summary}</h2>
              <div className="summary-tools">
                <div className="segmented small" role="tablist" aria-label={t.language}>
                  {(["de", "en"] as const).map((l) => (
                    <button key={l} role="tab" aria-selected={summaryLang === l} className={summaryLang === l ? "active" : ""}
                      onClick={() => setSummaryLang(l)}>{l === "de" ? "Deutsch" : "English"}</button>
                  ))}
                </div>
                <ListenButton trackKey={track.key} tracks={() => [track]} />
              </div>
            </div>

            {generating && (
              <p className="generating"><LoaderCircle size={16} className="spin" /> {t.generating}</p>
            )}
            {!requested?.available && part && (
              <p className="notice inline"><Info size={15} aria-hidden="true" /> {t.translationUnavailable(summaryLang)}</p>
            )}
            {part ? (
              <div lang={shownLang}>
                {part.summary && <p className="summary-text">{part.summary}</p>}
                {part.key_points && part.key_points.length > 0 && (
                  <>
                    <h3 className="sub-title">{t.keyPoints}</h3>
                    <ul className="key-points">
                      {part.key_points.map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  </>
                )}
                {part.context && (
                  <>
                    <h3 className="sub-title">{t.context}</h3>
                    <p className="summary-context">{part.context}</p>
                  </>
                )}
              </div>
            ) : (
              <p className="muted">{story.teaser[summaryLang]}</p>
            )}
            <p className="muted small summary-source">
              <Sparkles size={13} aria-hidden="true" />{" "}
              {story.summary.generated_by === "llm" ? `${t.aiSummary}${story.summary.model ? ` · ${story.summary.model}` : ""}` : t.extractiveSummary}
              {story.summary.generated_at && ` · ${timeAgo(story.summary.generated_at, t)}`}
            </p>
            {story.can_generate_summary && !generating && story.summary.generated_by === "llm" && meta?.llm.enabled && (
              <button className="link-btn" onClick={async () => {
                setGenerating(true);
                try { setStory(await api.summarize(story.id)); } finally { setGenerating(false); }
              }}>{t.generateSummary}</button>
            )}
          </section>
        </article>

        <aside className="story-side">
          <TrustPanel trust={story.trust} />
        </aside>

        <div className="story-coverage-area">
          <section className="panel coverage-panel" aria-labelledby="coverage-heading">
            <h2 id="coverage-heading" className="panel-title">{t.coverage}</h2>
            <p className="muted small">{t.biasDistribution}</p>
            <BiasBar bias={story.bias} variant="tall" />
            <div className="segmented coverage-tabs" role="tablist">
              {(["all", "left", "center", "right"] as const).map((b) => {
                const count = b === "all" ? story.articles.length : story.articles.filter((a) => a.source.bias_bucket === b).length;
                const label = b === "all" ? t.all : b === "left" ? t.biasLeft : b === "center" ? t.biasCenter : t.biasRight;
                return (
                  <button key={b} role="tab" aria-selected={bucket === b} className={bucket === b ? "active" : ""}
                    onClick={() => setBucket(b)} disabled={!count}>{label} ({count})</button>
                );
              })}
            </div>
            <ul className="article-list">
              {articles.map((a) => (
                <li key={a.id} className="article-item">
                  <div className="article-source">
                    <span className={`dot bias-${a.source.bias_bucket}`} aria-hidden="true" />
                    <strong>{a.source.name}</strong>
                    <span className="muted small" title={countryName(a.source.country ?? "", settings.lang)}>{flag(a.source.country)}</span>
                    <span className="muted small">{t.biasNames[a.source.bias]} · {t.factuality[a.source.factuality]}</span>
                    {a.is_opinion && <span className="tag">{t.opinion}</span>}
                  </div>
                  <a href={a.url} target="_blank" rel="noopener noreferrer" className="article-title" lang={a.language}>
                    {a.title} <ExternalLink size={13} aria-hidden="true" />
                  </a>
                  {a.description && <p className="article-desc" lang={a.language}>{a.description}</p>}
                  <span className="muted small">{timeAgo(a.published_at, t)}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
