import { Settings as SettingsIcon } from "lucide-react";
import { Link, NavLink } from "react-router-dom";
import { useApp } from "../settings";

export function Header() {
  const { t, settings, update } = useApp();
  return (
    <header className="app-header">
      <div className="header-inner">
        <Link to="/" className="brand" aria-label="Weitblick">
          <img src={`${import.meta.env.BASE_URL}icon.svg`} alt="" width={30} height={30} />
          <span className="brand-text">
            <strong>Weitblick</strong>
            <small>{t.tagline}</small>
          </span>
        </Link>
        <nav className="main-nav">
          <NavLink to="/" end>{t.navLatest}</NavLink>
          <NavLink to="/briefing">{t.navBriefing}</NavLink>
          <NavLink to="/quellen">{t.navSources}</NavLink>
        </nav>
        <div className="header-actions">
          <div className="segmented small" role="group" aria-label={t.language}>
            {(["de", "en"] as const).map((l) => (
              <button key={l} className={settings.lang === l ? "active" : ""} aria-pressed={settings.lang === l}
                onClick={() => update({ lang: l })}>{l.toUpperCase()}</button>
            ))}
          </div>
          <NavLink to="/einstellungen" className="icon-btn" aria-label={t.settings} title={t.settings}>
            <SettingsIcon size={19} />
          </NavLink>
        </div>
      </div>
    </header>
  );
}
