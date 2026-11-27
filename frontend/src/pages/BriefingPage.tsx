import { ListMusic } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { usePlayer } from "../audio/player";
import { DigestCard } from "../components/DigestCard";
import { ErrorState, Loading } from "../components/States";
import { useApp, useOrderedCategories } from "../settings";
import { digestTrack } from "../tracks";
import type { Briefing } from "../types";

export function BriefingPage() {
  const { t, settings } = useApp();
  const player = usePlayer();
  const [data, setData] = useState<Briefing | null>(null);
  const ordered = useOrderedCategories();
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api.briefing().then(setData).catch((e) => setError(e.message));
  };
  useEffect(load, []);

  if (error) return <div className="page"><ErrorState message={error} onRetry={load} /></div>;
  if (!data) return <div className="page"><Loading /></div>;

  // Kategorien in der eigenen Reihenfolge, ausgeblendete weglassen
  const bySlug = new Map(data.categories.map((d) => [d.scope.split(":")[1], d]));
  const categories = ordered.map((c) => bySlug.get(c.slug)).filter((d): d is NonNullable<typeof d> => !!d && d.stories.length > 0);
  const austria = data.austria && data.austria.stories.length > 0 ? data.austria : null;
  const top = settings.region === "AT" && austria ? [austria, data.day] : [data.day, ...(austria ? [austria] : [])];
  const playAll = () => player.play([...top, ...categories].map((d) => digestTrack(d, settings.lang)));

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">{t.briefingTitle}</h1>
          <p className="muted">{t.briefingIntro}</p>
        </div>
        <button className="pill-btn primary" onClick={playAll}><ListMusic size={17} /> {t.listenAll}</button>
      </div>
      <div className="briefing-top">
        {top.map((d) => <DigestCard key={d.scope} digest={d} />)}
        <DigestCard digest={data.week} />
      </div>
      <div className="briefing-grid">
        {categories.map((d) => (
          <DigestCard key={d.scope} digest={d} compact link={`/kategorie/${d.scope.split(":")[1]}`} />
        ))}
      </div>
    </div>
  );
}
