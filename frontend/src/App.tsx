import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { PlayerBar, PlayerProvider } from "./audio/player";
import { CategoryNav } from "./components/CategoryNav";
import { Header } from "./components/Header";
import { BriefingPage } from "./pages/BriefingPage";
import { HomePage } from "./pages/HomePage";
import { SourcesPage } from "./pages/SourcesPage";
import { StoryPage } from "./pages/StoryPage";
import { AppProvider, useApp } from "./settings";

function Layout() {
  const location = useLocation();
  const { t, meta } = useApp();
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

export default function App() {
  return (
    <AppProvider>
      <PlayerProvider>
        <BrowserRouter>
          <Layout />
        </BrowserRouter>
      </PlayerProvider>
    </AppProvider>
  );
}
