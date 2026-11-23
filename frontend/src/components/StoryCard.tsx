import { EyeOff } from "lucide-react";
import { Link } from "react-router-dom";
import { timeAgo, flag } from "../i18n";
import { useApp, useCategoryName } from "../settings";
import { storyTrack } from "../tracks";
import type { StoryItem } from "../types";
import { BiasBar } from "./BiasBar";
import { ListenButton } from "./ListenButton";
import { TrustBadge } from "./TrustBadge";

export function StoryCard({ story, featured = false }: { story: StoryItem; featured?: boolean }) {
  const { t, settings } = useApp();
  const categoryName = useCategoryName();
  const lang = settings.lang;
  const title = story.title[lang] || story.title.de || story.title.en;
  const teaser = story.teaser[lang];

  return (
    <article className={`story-card${featured ? " featured" : ""}`}>
      <Link to={`/meldung/${story.id}`} className="story-link" aria-label={title} />
      {story.image_url && (
        <div className="story-img">
          <img src={story.image_url} alt="" loading="lazy" referrerPolicy="no-referrer"
            onError={(e) => ((e.currentTarget.parentElement as HTMLElement).style.display = "none")} />
        </div>
      )}
      <div className="story-body">
        <div className="story-meta">
          <span className="chip-cat">{categoryName(story.category)}</span>
          <span className="muted">{timeAgo(story.last_updated, t)}</span>
          {story.countries.length > 0 && (
            <span className="flags" aria-hidden="true">{story.countries.slice(0, 4).map(flag).join(" ")}</span>
          )}
        </div>
        <h3 className="story-title" lang={story.title_is_original[lang] ? story.headline_lang ?? undefined : lang}>{title}</h3>
        {teaser && <p className="story-teaser">{teaser}</p>}
        {story.blindspot && (
          <p className="blindspot"><EyeOff size={14} aria-hidden="true" /> {story.blindspot === "left" ? t.blindspotLeft : t.blindspotRight}</p>
        )}
        <div className="story-footer">
          <div className="story-coverage">
            <BiasBar bias={story.bias} />
            <span className="muted small">
              {t.sources(story.source_count)}
              {story.top_sources.length > 0 && ` · ${story.top_sources.slice(0, 2).map((s) => s.name).join(", ")}`}
            </span>
          </div>
          <div className="story-actions">
            <TrustBadge score={story.trust.score} label={story.trust.label} />
            <ListenButton variant="icon" trackKey={`story-${story.id}-${lang}`} tracks={() => [storyTrack(story, lang)]} />
          </div>
        </div>
      </div>
    </article>
  );
}
