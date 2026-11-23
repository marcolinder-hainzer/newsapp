import { NavLink } from "react-router-dom";
import { useApp } from "../settings";
import { CategoryIcon } from "./CategoryIcon";

export function CategoryNav() {
  const { meta, settings, t } = useApp();
  if (!meta) return null;
  return (
    <nav className="cat-nav" aria-label="Kategorien">
      <NavLink to="/" end className={({ isActive }) => `cat-chip${isActive ? " active" : ""}`}>{t.all}</NavLink>
      {meta.categories.map((c) => (
        <NavLink key={c.slug} to={`/kategorie/${c.slug}`} className={({ isActive }) => `cat-chip${isActive ? " active" : ""}`}>
          <CategoryIcon icon={c.icon} size={15} />
          {c[settings.lang]}
        </NavLink>
      ))}
    </nav>
  );
}
