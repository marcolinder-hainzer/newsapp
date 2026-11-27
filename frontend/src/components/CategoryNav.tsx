import { Check, ChevronDown, Layers, SlidersHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useApp, useOrderedCategories } from "../settings";
import { CategoryIcon } from "./CategoryIcon";

/**
 * Leiste unter dem Kopfbereich: Ausklapp-Menü für die Kategorien und Schalter „Nur Österreich“.
 */
export function CategoryNav() {
  const { t, settings } = useApp();
  const categories = useOrderedCategories();
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const current = location.pathname.startsWith("/kategorie/") ? location.pathname.split("/")[2] : "";
  const currentCat = categories.find((c) => c.slug === current);
  const region = params.get("region") ?? settings.region;
  const austria = region === "AT";

  // Schließen bei Klick daneben oder Escape
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    listRef.current?.querySelector<HTMLElement>("[aria-selected='true']")?.focus();
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const choose = (slug: string) => {
    setOpen(false);
    const search = params.get("region") ? `?region=${params.get("region")}` : "";
    navigate(`${slug ? `/kategorie/${slug}` : "/"}${search}`);
  };

  const onListKey = (e: React.KeyboardEvent) => {
    const items = [...(listRef.current?.querySelectorAll<HTMLElement>("[role='option']") ?? [])];
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") items[Math.min(items.length - 1, index + 1)]?.focus();
    else if (e.key === "ArrowUp") items[Math.max(0, index - 1)]?.focus();
    else return;
    e.preventDefault();
  };

  const toggleAustria = () => {
    const next = new URLSearchParams(params);
    const target = austria ? "all" : "AT";
    if (target === settings.region) next.delete("region");
    else next.set("region", target);
    setParams(next, { replace: true });
  };

  const options = [{ slug: "", label: t.allCategories, icon: "" }, ...categories.map((c) => ({ slug: c.slug, label: c[settings.lang], icon: c.icon }))];

  return (
    <div className="cat-bar">
      <div className="cat-picker" ref={rootRef}>
        <button className="cat-picker-btn" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>
          {currentCat ? <CategoryIcon icon={currentCat.icon} size={17} /> : <Layers size={17} aria-hidden="true" />}
          <span className="cat-picker-label">
            <small>{t.category}</small>
            <span className="cat-picker-current">{currentCat ? currentCat[settings.lang] : t.allCategories}</span>
          </span>
          <ChevronDown size={18} className={`chev${open ? " open" : ""}`} aria-hidden="true" />
        </button>
        {open && (
          <div className="cat-menu">
            <ul role="listbox" aria-label={t.category} ref={listRef} onKeyDown={onListKey}>
              {options.map((o) => (
                <li key={o.slug || "all"} role="option" aria-selected={o.slug === current} tabIndex={0}
                  className={o.slug === current ? "selected" : ""}
                  onClick={() => choose(o.slug)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && choose(o.slug)}>
                  {o.slug ? <CategoryIcon icon={o.icon} size={17} /> : <Layers size={17} aria-hidden="true" />}
                  <span>{o.label}</span>
                  {o.slug === current && <Check size={16} className="check" aria-hidden="true" />}
                </li>
              ))}
            </ul>
            <Link to="/einstellungen#kategorien" className="cat-menu-footer" onClick={() => setOpen(false)}>
              <SlidersHorizontal size={15} aria-hidden="true" /> {t.customizeCategories}
            </Link>
          </div>
        )}
      </div>
      <button className={`region-toggle${austria ? " active" : ""}`} aria-pressed={austria} onClick={toggleAustria}
        title={t.onlyAustriaHint}>
        <span className="flag-at" aria-hidden="true" />
        <span className="hide-sm">{t.onlyAustria}</span>
        <span className="show-sm">{t.austria}</span>
      </button>
    </div>
  );
}
