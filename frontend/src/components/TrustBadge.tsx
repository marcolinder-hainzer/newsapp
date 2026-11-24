import { ShieldCheck, ShieldExclamationPoint, Shield } from "lucide-react";
import { useApp } from "../settings";
import type { TrustDetail, TrustLabel } from "../types";

function statusOf(label: TrustLabel): "good" | "warning" | "critical" {
  if (label === "very_high" || label === "high") return "good";
  if (label === "medium") return "warning";
  return "critical";
}

function StatusIcon({ label, size }: { label: TrustLabel; size: number }) {
  const status = statusOf(label);
  const Icon = status === "good" ? ShieldCheck : status === "warning" ? Shield : ShieldExclamationPoint;
  return <Icon size={size} className={`status-icon status-${status}`} aria-hidden="true" />;
}

export function TrustBadge({ score, label }: { score: number; label: TrustLabel }) {
  const { t } = useApp();
  return (
    <span className="trust-badge" title={`${t.trustScore}: ${score}/100 – ${t.trustLabels[label]}`}>
      <StatusIcon label={label} size={15} />
      <span className="trust-score">{score}</span>
      <span className="trust-label">{t.trustLabels[label]}</span>
    </span>
  );
}

const ORDER = ["reliability", "corroboration", "diversity", "content"] as const;

export function TrustPanel({ trust }: { trust: TrustDetail }) {
  const { t, settings } = useApp();
  const status = statusOf(trust.label);
  const notes = trust.notes?.[settings.lang] ?? [];
  return (
    <section className="panel trust-panel" aria-labelledby="trust-heading">
      <div className="trust-head">
        <div>
          <h2 id="trust-heading" className="panel-title">{t.trustScore}</h2>
          <div className="trust-hero">
            <StatusIcon label={trust.label} size={28} />
            <span className="trust-hero-value">{trust.score}</span>
            <span className="trust-hero-max">/100</span>
            <span className="trust-hero-label">{t.trustLabels[trust.label]}</span>
          </div>
        </div>
      </div>
      <div className={`meter meter-${status}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={trust.score}
        aria-label={t.trustScore}>
        <div style={{ width: `${trust.score}%` }} />
      </div>
      {trust.components && (
        <dl className="trust-components">
          {ORDER.map((key) => {
            const value = trust.components![key];
            const weight = Math.round((trust.weights?.[key] ?? 0) * 100);
            return (
              <div key={key} className="trust-component">
                <dt>
                  <span>{t.trustComponents[key]}</span>
                  <span className="muted small">{t.trustComponentHelp[key]}{weight ? ` · ${weight}\u00a0%` : ""}</span>
                </dt>
                <dd>
                  <div className="mini-meter" aria-hidden="true"><div style={{ width: `${value}%` }} /></div>
                  <span className="mini-value">{value}</span>
                </dd>
              </div>
            );
          })}
        </dl>
      )}
      {notes.length > 0 && (
        <ul className="trust-notes">
          {notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
      {trust.content_method && (
        <p className="muted small">{t.contentMethodHeuristic}</p>
      )}
    </section>
  );
}
