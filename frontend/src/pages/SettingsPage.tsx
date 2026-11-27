import { ArrowDown, ArrowUp, LoaderCircle, Moon, Monitor, Play, RotateCcw, Sun } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { api } from "../api";
import { NATURAL_VOICES, NaturalSpeaker, naturalSupported } from "../audio/natural";
import { usePlayer } from "../audio/player";
import { DeviceSpeaker, listVoices, pickVoice, voiceGender, whenVoicesReady } from "../audio/speech";
import { CategoryIcon } from "../components/CategoryIcon";
import { countryName, flag } from "../i18n";
import {
  CARD_ELEMENTS, FILTER_DEFAULTS, LOOK_KEYS, useApp, useOrderedCategories,
  type Accent, type CardElement, type HomeSection, type Settings,
} from "../settings";
import type { Lang, Source, Voice } from "../types";

const ACCENTS: Accent[] = ["blue", "teal", "green", "violet", "red", "orange", "graphite"];

function Section({ id, title, children, onReset }: { id: string; title: string; children: ReactNode; onReset?: () => void }) {
  const { t } = useApp();
  return (
    <section className="settings-section panel" id={id}>
      <header className="settings-head">
        <h2>{title}</h2>
        {onReset && (
          <button className="link-btn small" onClick={onReset}><RotateCcw size={14} /> {t.resetSection}</button>
        )}
      </header>
      {children}
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="settings-row">
      <div className="settings-label">
        <span>{label}</span>
        {hint && <small className="muted">{hint}</small>}
      </div>
      <div className="settings-control">{children}</div>
    </div>
  );
}

function Choice<T extends string | number>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="segmented wrap" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} className={o.value === value ? "active" : ""} aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button role="switch" aria-checked={checked} aria-label={label} className={`switch${checked ? " on" : ""}`}
      onClick={() => onChange(!checked)}>
      <span />
    </button>
  );
}

/** Liste mit Ein/Aus-Schalter und Pfeilen zum Umsortieren (wie „Anordnung & Inhalte“ in AlpinWetter). */
function ArrangeList<T extends string>({ items, order, hidden, label, onChange }: {
  items: { key: T; label: string; icon?: ReactNode }[];
  order: T[];
  hidden: T[];
  label: string;
  onChange: (order: T[], hidden: T[]) => void;
}) {
  const sorted = [...items].sort((a, b) => {
    const ia = order.indexOf(a.key);
    const ib = order.indexOf(b.key);
    return (ia < 0 ? 999 + items.indexOf(a) : ia) - (ib < 0 ? 999 + items.indexOf(b) : ib);
  });
  const keys = sorted.map((i) => i.key);
  const move = (index: number, delta: number) => {
    const next = [...keys];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    onChange(next, hidden);
  };
  return (
    <ul className="arrange-list" aria-label={label}>
      {sorted.map((item, index) => {
        const visible = !hidden.includes(item.key);
        return (
          <li key={item.key} className={visible ? "" : "is-hidden"}>
            {item.icon}
            <span className="arrange-label">{item.label}</span>
            <button className="icon-btn" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`${item.label} ↑`}>
              <ArrowUp size={16} />
            </button>
            <button className="icon-btn" disabled={index === sorted.length - 1} onClick={() => move(index, 1)}
              aria-label={`${item.label} ↓`}>
              <ArrowDown size={16} />
            </button>
            <Switch checked={visible} label={item.label}
              onChange={(on) => onChange(keys, on ? hidden.filter((h) => h !== item.key) : [...hidden, item.key])} />
          </li>
        );
      })}
    </ul>
  );
}

export function SettingsPage() {
  const { t, settings, update, reset } = useApp();
  const categories = useOrderedCategories(true);
  const player = usePlayer();
  const location = useLocation();
  const [sources, setSources] = useState<Source[]>([]);
  const [voices, setVoices] = useState<Record<Lang, SpeechSynthesisVoice[]>>({ de: [], en: [] });
  const [previewLoading, setPreviewLoading] = useState<number | null>(null);
  const device = useRef(new DeviceSpeaker());
  const natural = useRef<NaturalSpeaker | null>(naturalSupported() ? new NaturalSpeaker() : null);
  const naturalOn = settings.voiceEngine === "natural" && !!natural.current;

  useEffect(() => {
    api.sources().then((r) => setSources(r.items)).catch(() => undefined);
    whenVoicesReady().then(() => setVoices({ de: listVoices("de"), en: listVoices("en") }));
    const d = device.current;
    const n = natural.current;
    if (n) {
      n.onLoading = (fraction) => setPreviewLoading(fraction);
      n.onProgress = () => setPreviewLoading(null);
      n.onError = () => setPreviewLoading(null);
    }
    return () => {
      d.stop();
      n?.stop();
    };
  }, []);

  // Sprungmarke (#kategorien usw.) anspringen
  useEffect(() => {
    const id = location.hash.replace("#", "") || location.pathname.split("#")[1];
    if (id) window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }), 50);
  }, [location]);

  const preview = (lang: Lang, voice: Voice) => {
    device.current.stop();
    natural.current?.stop();
    if (player.status !== "idle") player.stop();
    const sentence = t.testSentenceFor(lang);
    if (naturalOn) {
      natural.current!.unlock();
      natural.current!.rate = settings.rate;
      natural.current!.start(sentence, lang, voice);
      return;
    }
    device.current.rate = settings.rate;
    device.current.start(sentence, lang, voice, settings.deviceVoices[`${lang}-${voice}`]);
  };

  const fd = settings.filterDefaults;
  const setFilter = (patch: Partial<Settings["filterDefaults"]>) => update({ filterDefaults: { ...fd, ...patch } });
  const langName = settings.lang === "de" ? "Deutsch" : "English";
  const hasDeviceMale = voices[settings.lang].some((v) => voiceGender(v) === "male");

  const sourcesByCountry = useMemo(() => {
    const groups = new Map<string, Source[]>();
    for (const s of sources) groups.set(s.country ?? "", [...(groups.get(s.country ?? "") ?? []), s]);
    return [...groups.entries()].sort(([a], [b]) => (a === "AT" ? -1 : b === "AT" ? 1 : a === "DE" ? -1 : b === "DE" ? 1 : a.localeCompare(b)));
  }, [sources]);

  const startOptions = [
    { value: "/", label: t.navLatest },
    { value: "/briefing", label: t.navBriefing },
    ...categories.map((c) => ({ value: `/kategorie/${c.slug}`, label: `${t.category}: ${c[settings.lang]}` })),
  ];

  const homeItems: { key: HomeSection; label: string }[] = [
    { key: "briefing", label: t.homeSections.briefing },
    { key: "filters", label: t.homeSections.filters },
    { key: "stats", label: t.homeSections.stats },
    { key: "stories", label: t.homeSections.stories },
  ];

  return (
    <div className="page settings-page">
      <div className="page-head">
        <div>
          <h1 className="page-title">{t.settings}</h1>
          <p className="muted">{t.settingsIntro}</p>
        </div>
      </div>
      <nav className="settings-toc" aria-label={t.settings}>
        {[["allgemein", t.sectionGeneral], ["aussehen", t.sectionLook], ["startseite", t.sectionHome],
          ["kategorien", t.sectionCategories], ["standards", t.sectionDefaults], ["quellen", t.sectionSources],
          ["vorlesen", t.sectionVoice]].map(([id, label]) => (
          <a key={id} href={`#${id}`} onClick={(e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); }}>{label}</a>
        ))}
      </nav>

      <Section id="allgemein" title={t.sectionGeneral}>
        <Row label={t.language}>
          <Choice label={t.language} value={settings.lang} onChange={(v) => update({ lang: v })}
            options={[{ value: "de", label: "Deutsch" }, { value: "en", label: "English" }]} />
        </Row>
        <Row label={t.startPage} hint={t.startPageHint}>
          <select className="select" value={settings.startPage} onChange={(e) => update({ startPage: e.target.value })}>
            {startOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Row>
        <Row label={t.regionDefault} hint={t.regionDefaultHint}>
          <Choice label={t.regionDefault} value={settings.region} onChange={(v) => update({ region: v })}
            options={[{ value: "all", label: t.regionAll }, { value: "AT", label: <><span className="flag-at" aria-hidden="true" />{t.austria}</> }]} />
        </Row>
      </Section>

      <Section id="aussehen" title={t.sectionLook} onReset={() => reset(LOOK_KEYS)}>
        <Row label={t.theme}>
          <Choice label={t.theme} value={settings.theme} onChange={(v) => update({ theme: v })} options={[
            { value: "system", label: <><Monitor size={15} /> {t.themeSystem}</> },
            { value: "light", label: <><Sun size={15} /> {t.themeLight}</> },
            { value: "dark", label: <><Moon size={15} /> {t.themeDark}</> },
          ]} />
        </Row>
        <Row label={t.accent}>
          <div className="swatches" role="radiogroup" aria-label={t.accent}>
            {ACCENTS.map((a) => (
              <button key={a} role="radio" aria-checked={settings.accent === a} aria-label={t.accents[a]} title={t.accents[a]}
                className={`swatch swatch-${a}${settings.accent === a ? " active" : ""}`} onClick={() => update({ accent: a })} />
            ))}
          </div>
        </Row>
        <Row label={t.corners}>
          <Choice label={t.corners} value={settings.corners} onChange={(v) => update({ corners: v })} options={[
            { value: "square", label: t.cornersSquare }, { value: "round", label: t.cornersRound }, { value: "extra", label: t.cornersExtra },
          ]} />
        </Row>
        <Row label={t.cardStyle}>
          <Choice label={t.cardStyle} value={settings.cardStyle} onChange={(v) => update({ cardStyle: v })} options={[
            { value: "shadow", label: t.cardShadow }, { value: "border", label: t.cardBorder }, { value: "flat", label: t.cardFlat },
          ]} />
        </Row>
        <Row label={t.fontScale}>
          <Choice label={t.fontScale} value={settings.fontScale} onChange={(v) => update({ fontScale: v })} options={[
            { value: "s", label: "A−" }, { value: "m", label: "A" }, { value: "l", label: "A+" }, { value: "xl", label: "A++" },
          ]} />
        </Row>
        <Row label={t.density}>
          <Choice label={t.density} value={settings.density} onChange={(v) => update({ density: v })} options={[
            { value: "compact", label: t.densityCompact }, { value: "normal", label: t.densityNormal }, { value: "airy", label: t.densityAiry },
          ]} />
        </Row>
        <Row label={t.cardLayout}>
          <Choice label={t.cardLayout} value={settings.cardLayout} onChange={(v) => update({ cardLayout: v })} options={[
            { value: "grid", label: t.layoutGrid }, { value: "list", label: t.layoutList },
          ]} />
        </Row>
        <Row label={t.cardElements} hint={t.cardElementsHint}>
          <div className="check-grid">
            {CARD_ELEMENTS.map((el: CardElement) => (
              <label key={el} className="check-item">
                <input type="checkbox" checked={!settings.hiddenCardElements.includes(el)}
                  onChange={(e) => update({
                    hiddenCardElements: e.target.checked
                      ? settings.hiddenCardElements.filter((x) => x !== el)
                      : [...settings.hiddenCardElements, el],
                  })} />
                {t.cardElementNames[el]}
              </label>
            ))}
          </div>
        </Row>
      </Section>

      <Section id="startseite" title={t.sectionHome} onReset={() => reset(["homeOrder", "hiddenHome"])}>
        <p className="muted small">{t.sectionHomeHint}</p>
        <ArrangeList label={t.sectionHome} items={homeItems} order={settings.homeOrder} hidden={settings.hiddenHome}
          onChange={(order, hidden) => update({ homeOrder: order, hiddenHome: hidden })} />
      </Section>

      <Section id="kategorien" title={t.sectionCategories} onReset={() => reset(["categoryOrder", "hiddenCategories"])}>
        <p className="muted small">{t.sectionCategoriesHint}</p>
        <ArrangeList label={t.sectionCategories}
          items={categories.map((c) => ({ key: c.slug, label: c[settings.lang], icon: <CategoryIcon icon={c.icon} size={17} /> }))}
          order={settings.categoryOrder.length ? settings.categoryOrder : categories.map((c) => c.slug)}
          hidden={settings.hiddenCategories}
          onChange={(order, hidden) => update({ categoryOrder: order, hiddenCategories: hidden })} />
      </Section>

      <Section id="standards" title={t.sectionDefaults} onReset={() => update({ filterDefaults: FILTER_DEFAULTS })}>
        <p className="muted small">{t.sectionDefaultsHint}</p>
        <Row label={t.timeRange}>
          <Choice label={t.timeRange} value={fd.hours} onChange={(v) => setFilter({ hours: v })} options={[
            { value: 6, label: t.hours6 }, { value: 24, label: t.hours24 }, { value: 48, label: t.hours48 }, { value: 168, label: t.days7 },
          ]} />
        </Row>
        <Row label={t.sort}>
          <select className="select" value={fd.sort} onChange={(e) => setFilter({ sort: e.target.value })}>
            <option value="relevance">{t.sortRelevance}</option>
            <option value="latest">{t.sortLatest}</option>
            <option value="sources">{t.sortSources}</option>
            <option value="trust">{t.sortTrust}</option>
          </select>
        </Row>
        <Row label={t.sourceLanguage}>
          <Choice label={t.sourceLanguage} value={fd.lang} onChange={(v) => setFilter({ lang: v })} options={[
            { value: "", label: t.all }, { value: "de", label: t.german }, { value: "en", label: t.english },
          ]} />
        </Row>
        <Row label={t.minTrust} hint={fd.min_trust ? `${fd.min_trust}` : t.all}>
          <input type="range" min={0} max={90} step={10} value={fd.min_trust} onChange={(e) => setFilter({ min_trust: Number(e.target.value) })} />
        </Row>
        <Row label={t.minSources}>
          <Choice label={t.minSources} value={fd.min_sources} onChange={(v) => setFilter({ min_sources: v })} options={[
            { value: 1, label: "1+" }, { value: 2, label: "2+" }, { value: 3, label: "3+" }, { value: 5, label: "5+" },
          ]} />
        </Row>
        <Row label={t.perspective}>
          <select className="select" value={fd.perspective} onChange={(e) => setFilter({ perspective: e.target.value })}>
            <option value="all">{t.perspectiveAll}</option>
            <option value="balanced">{t.perspectiveBalanced}</option>
            <option value="left">{t.perspectiveLeft}</option>
            <option value="right">{t.perspectiveRight}</option>
            <option value="blindspot">{t.perspectiveBlindspot}</option>
          </select>
        </Row>
      </Section>

      <Section id="quellen" title={t.sectionSources} onReset={() => reset(["hiddenSources"])}>
        <p className="muted small">{t.sectionSourcesHint}</p>
        {sourcesByCountry.map(([country, list]) => (
          <div key={country} className="source-group">
            <h3>{flag(country)} {countryName(country, settings.lang)}</h3>
            <div className="check-grid">
              {list.map((s) => (
                <label key={s.id} className="check-item">
                  <input type="checkbox" checked={!settings.hiddenSources.includes(s.id)}
                    onChange={(e) => update({
                      hiddenSources: e.target.checked
                        ? settings.hiddenSources.filter((x) => x !== s.id)
                        : [...settings.hiddenSources, s.id],
                    })} />
                  <span className={`dot bias-${s.bias_bucket}`} aria-hidden="true" />
                  {s.name}
                </label>
              ))}
            </div>
          </div>
        ))}
      </Section>

      <Section id="vorlesen" title={t.sectionVoice}>
        <Row label={t.voiceEngine} hint={naturalOn ? t.engineNaturalHint : t.engineDeviceHint}>
          <Choice label={t.voiceEngine} value={settings.voiceEngine} onChange={(v) => update({ voiceEngine: v })} options={[
            ...(natural.current ? [{ value: "natural" as const, label: t.engineNatural }] : []),
            { value: "device" as const, label: t.engineDevice },
          ]} />
        </Row>
        <div className="voice-cards">
          {(["female", "male"] as const).map((v) => (
            <button key={v} className={`voice-card${settings.voice === v ? " active" : ""}`} onClick={() => update({ voice: v })}
              aria-pressed={settings.voice === v}>
              <span className="voice-name">{v === "female" ? t.voiceFemale : t.voiceMale}</span>
              <span className="muted small">
                {naturalOn
                  ? NATURAL_VOICES[settings.lang][v].name
                  : pickVoice(settings.lang, v, settings.deviceVoices[`${settings.lang}-${v}`])?.name ?? "—"}
              </span>
              <span className="voice-preview" role="button" tabIndex={0} aria-label={t.test}
                onClick={(e) => { e.stopPropagation(); preview(settings.lang, v); }}
                onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); preview(settings.lang, v); } }}>
                <Play size={14} /> {t.test}
              </span>
            </button>
          ))}
        </div>
        {previewLoading !== null && (
          <p className="muted small"><LoaderCircle size={13} className="spin" /> {t.loadingVoice}
            {previewLoading > 0 && ` ${Math.round(previewLoading * 100)} %`}</p>
        )}
        {!naturalOn && voices[settings.lang].length > 0 && !hasDeviceMale && (
          <p className="small warn-text">{t.noMaleDeviceVoice(langName)}</p>
        )}
        <Row label={t.speed}>
          <div className="range-row">
            <input type="range" min={0.7} max={1.6} step={0.05} value={settings.rate}
              onChange={(e) => update({ rate: Number(e.target.value) })} />
            <span className="mono">{settings.rate.toFixed(2)}×</span>
          </div>
        </Row>
        {!naturalOn && (["de", "en"] as const).map((lang) => (["female", "male"] as const).map((v) => (
          <Row key={`${lang}-${v}`} label={t.deviceVoice(lang.toUpperCase(), v === "female" ? t.voiceFemale : t.voiceMale)}>
            <select className="select" value={settings.deviceVoices[`${lang}-${v}`] ?? ""}
              onChange={(e) => update({ deviceVoices: { ...settings.deviceVoices, [`${lang}-${v}`]: e.target.value } })}>
              <option value="">{t.automatic}</option>
              {voices[lang].map((voice) => <option key={voice.voiceURI} value={voice.voiceURI}>{voice.name} ({voice.lang})</option>)}
            </select>
          </Row>
        )))}
      </Section>

      <div className="center">
        <button className="pill-btn" onClick={() => window.confirm(t.resetAllConfirm) && reset()}>
          <RotateCcw size={15} /> {t.resetAll}
        </button>
      </div>
      <p className="muted small center-text">{t.settingsStoredLocally}</p>
    </div>
  );
}
