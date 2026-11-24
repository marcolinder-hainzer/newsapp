import { Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { timeAgo } from "../i18n";
import { useApp } from "../settings";
import { digestTrack, storyTrack } from "../tracks";
import type { Digest } from "../types";
import { ListenButton } from "./ListenButton";
import { TrustBadge } from "./TrustBadge";

interface Props {
  digest: Digest;
  tabs?: React.ReactNode;
  compact?: boolean;
  link?: string;
}

export function DigestCard({ digest, tabs, compact = false, link }: Props) {
  const { t, settings } = useApp();
  const lang = settings.lang;
  const content = digest.content[lang] ?? digest.content.de ?? digest.content.en;
  const byId = new Map(digest.stories.map((s) => [s.id, s]));
  const items = (content?.items ?? []).filter((i) => byId.has(i.story_id)).slice(0, compact ? 4 : 8);

  return (
    <section className={`digest${compact ? " compact" : ""}`}>
      <header className="digest-head">
        <div>
          <p className="kicker">
            <Sparkles size={14} aria-hidden="true" />
            {t.generatedByTemplate}
            <span className="muted"> · {timeAgo(digest.generated_at, t)}</span>
          </p>
          <h2 className="digest-title">{link ? <Link to={link}>{content?.headline || digest.title[lang]}</Link> : content?.headline || digest.title[lang]}</h2>
        </div>
        {tabs}
      </header>
      {content?.overview && <p className="digest-overview">{content.overview}</p>}
      {items.length > 0 && (
        <ol className="digest-items">
          {items.map((item) => {
            const story = byId.get(item.story_id)!;
            return (
              <li key={item.story_id}>
                <Link to={`/meldung/${story.id}`} className="digest-item">
                  <span className="digest-text">{item.text}</span>
                  <span className="digest-item-meta">
                    <span className="muted small">{t.sources(story.source_count)}</span>
                    <TrustBadge score={story.trust.score} label={story.trust.label} />
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      )}
      <div className="digest-actions">
        <ListenButton trackKey={`digest-${digest.scope}-${lang}`} label={t.listenBriefing}
          tracks={() => [digestTrack(digest, lang)]} />
        {!compact && items.length > 1 && (
          <ListenButton trackKey={`story-${items[0].story_id}-${lang}`} label={t.listenAll}
            tracks={() => items.map((i) => storyTrack(byId.get(i.story_id)!, lang))} />
        )}
      </div>
    </section>
  );
}
