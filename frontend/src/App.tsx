import { useEffect } from "react";
import { BrowserRouter, HashRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { IS_STATIC } from "./api";
import { PlayerBar, PlayerProvider } from "./audio/player";
import { CategoryNav } from "./components/CategoryNav";
import { Header } from "./components/Header";
import { BriefingPage } from "./pages/BriefingPage";
import { HomePage } from "./pages/HomePage";
import { SettingsPage } from "./pages/SettingsPage";
import { SourcesPage } from "./pages/SourcesPage";
import { StoryPage } from "./pages/StoryPage";
import { AppProvider, useApp } from "./settings";

const START_KEY = "weitblick.started";

/** Gewählte Startseite einmal pro Sitzung öffnen – nur wenn die App ohne Unterseite/Filter aufgerufen wird. */
function useStartPage() {
  const { settings } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (sessionStorage.getItem(START_KEY)) return;
    sessionStorage.setItem(START_KEY, "1");
    if (location.pathname === "/" && !location.search && settings.startPage !== "/") {
      navigate(settings.startPage, { replace: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}

function Layout() {
  const location = useLocation();
  const { t, meta } = useApp();
  useStartPage();
  // beim Seitenwechsel nach oben (Sprungmarken wie #kategorien ausgenommen)
  useEffect(() => {
    if (!location.hash) window.scrollTo(0, 0);
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  const showCategories = location.pathname === "/" || location.pathname.startsWith("/kategorie/");
  return (
    <>
      <Header />
      {showCategories && <CategoryNav />}
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/kategorie/:slug" element={<HomePage />} />
          <Route path="/meldung/:id" element={<StoryPage />} />
          <Route path="/briefing" element={<BriefingPage />} />
          <Route path="/quellen" element={<SourcesPage />} />
          <Route path="/einstellungen" element={<SettingsPage />} />
          <Route path="*" element={<HomePage />} />
        </Routes>
      </main>
      <footer className="app-footer">
        <span>Weitblick {meta?.app.version}</span>
        <span>·</span>
        <span>{t.footerNote}</span>
      </footer>
      <PlayerBar />
    </>
  );
}

// GitHub Pages kennt keine Weiterleitung auf index.html – dort werden Hash-Links (#/meldung/1) genutzt
const Router = IS_STATIC ? HashRouter : BrowserRouter;

export default function App() {
  return (
    <AppProvider>
      <PlayerProvider>
        <Router>
          <Layout />
        </Router>
      </PlayerProvider>
    </AppProvider>
  );
}
