import { ListMusic } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { usePlayer } from "../audio/player";
import { DigestCard } from "../components/DigestCard";
import { ErrorState, Loading } from "../components/States";
import { useApp } from "../settings";
import { digestTrack } from "../tracks";
import type { Digest } from "../types";

export function BriefingPage() {
  const { t, settings } = useApp();
  const player = usePlayer();
  const [data, setData] = useState<{ day: Digest; week: Digest; categories: Digest[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api.briefing().then(setData).catch((e) => setError(e.message));
  };
  useEffect(load, []);

  if (error) return <div className="page"><ErrorState message={error} onRetry={load} /></div>;
  if (!data) return <div className="page"><Loading /></div>;

  const categories = data.categories.filter((d) => d.stories.length > 0);
  const playAll = () => player.play([data.day, ...categories].map((d) => digestTrack(d, settings.lang)));

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
        <DigestCard digest={data.day} />
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
