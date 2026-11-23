import { useApp } from "../settings";

interface Props {
  bias: { left: number; center: number; right: number };
  variant?: "thin" | "tall";
}

/** Segmentierter Balken: Anteil der Quellen aus dem linken, mittleren und rechten Spektrum. */
export function BiasBar({ bias, variant = "thin" }: Props) {
  const { t } = useApp();
  const total = bias.left + bias.center + bias.right;
  const parts = [
    { key: "left", label: t.biasLeft, value: bias.left },
    { key: "center", label: t.biasCenter, value: bias.center },
    { key: "right", label: t.biasRight, value: bias.right },
  ].map((p) => ({ ...p, share: total ? Math.round((p.value / total) * 100) : 0 }));
  const description = `${t.biasDistribution}: ` + parts.map((p) => `${p.label} ${p.value} (${p.share} %)`).join(", ");

  if (!total) return null;
  return (
    <div className={`bias bias-${variant}`}>
      <div className="bias-track" role="img" aria-label={description} title={description}>
        {parts.filter((p) => p.value > 0).map((p) => (
          <div key={p.key} className={`bias-seg bias-${p.key}`} style={{ flexGrow: p.value }}>
            {variant === "tall" && p.share >= 14 && <span>{p.share}{"\u00a0"}%</span>}
          </div>
        ))}
      </div>
      {variant === "tall" && (
        <ul className="bias-legend">
          {parts.map((p) => (
            <li key={p.key}>
              <span className={`dot bias-${p.key}`} aria-hidden="true" />
              {p.label} <strong>{p.value}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
