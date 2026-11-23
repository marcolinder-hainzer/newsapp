import { LoaderCircle, RefreshCw } from "lucide-react";
import { useApp } from "../settings";

export function Loading() {
  const { t } = useApp();
  return (
    <div className="state" role="status">
      <LoaderCircle className="spin" size={22} /> <span>{t.loading}</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  const { t } = useApp();
  return (
    <div className="state state-error" role="alert">
      <span>{t.error}{message ? `: ${message}` : ""}</span>
      {onRetry && (
        <button className="pill-btn" onClick={onRetry}><RefreshCw size={15} /> {t.retry}</button>
      )}
    </div>
  );
}

export function SkeletonCards({ count = 6 }: { count?: number }) {
  return (
    <div className="story-grid" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="story-card skeleton">
          <div className="sk sk-img" />
          <div className="sk sk-line w60" />
          <div className="sk sk-line" />
          <div className="sk sk-line w80" />
        </div>
      ))}
    </div>
  );
}
