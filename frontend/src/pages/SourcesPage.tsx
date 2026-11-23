import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorState, Loading } from "../components/States";
import { countryName, flag } from "../i18n";
import { useApp } from "../settings";
import type { Source } from "../types";

export function SourcesPage() {
  const { t, settings } = useApp();
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.sources().then((r) => setSources(r.items)).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <h1 className="page-title">{t.sourcesTitle}</h1>
      <p className="lead">{t.sourcesIntro}</p>
      <div className="method-grid">
        <section className="panel"><h2 className="panel-title">{t.methodTrust}</h2><p>{t.methodTrustText}</p></section>
        <section className="panel"><h2 className="panel-title">{t.methodBias}</h2><p>{t.methodBiasText}</p></section>
        <section className="panel"><h2 className="panel-title">{t.methodSummary}</h2><p>{t.methodSummaryText}</p></section>
      </div>

      {error && <ErrorState message={error} />}
      {!sources && !error && <Loading />}
      {sources && (
        <div className="table-wrap">
          <table className="sources-table">
            <thead>
              <tr>
                <th scope="col">{settings.lang === "de" ? "Medium" : "Outlet"}</th>
                <th scope="col">{t.country}</th>
                <th scope="col">{t.perspective}</th>
                <th scope="col">{t.reliability}</th>
                <th scope="col" className="hide-sm">{settings.lang === "de" ? "Träger" : "Ownership"}</th>
                <th scope="col" className="num">{t.articles24h}</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id}>
                  <td>
                    <a href={s.homepage ?? "#"} target="_blank" rel="noopener noreferrer"><strong>{s.name}</strong></a>
                    {s.note && <div className="muted small">{s.note}</div>}
                    {!!s.errors && <div className="small warn-text">{t.feedErrors(s.errors)}</div>}
                  </td>
                  <td><span aria-hidden="true">{flag(s.country)}</span> {countryName(s.country ?? "", settings.lang)}</td>
                  <td><span className={`dot bias-${s.bias_bucket}`} aria-hidden="true" /> {t.biasNames[s.bias]}</td>
                  <td>
                    <div className="reliability">
                      <div className="mini-meter" aria-hidden="true"><div style={{ width: `${s.reliability}%` }} /></div>
                      <span className="mini-value">{s.reliability}</span>
                    </div>
                    <div className="muted small">{t.factuality[s.factuality]}</div>
                  </td>
                  <td className="hide-sm">{t.ownership[s.ownership ?? ""] ?? s.ownership}</td>
                  <td className="num">{s.articles_24h ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
