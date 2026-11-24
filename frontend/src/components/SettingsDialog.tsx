import { Moon, Monitor, Play, Sun, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { DeviceSpeaker, listVoices, pickVoice, whenVoicesReady } from "../audio/speech";
import { useApp } from "../settings";
import type { Lang, Voice } from "../types";

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { t, settings, update } = useApp();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [voices, setVoices] = useState<Record<Lang, SpeechSynthesisVoice[]>>({ de: [], en: [] });
  const speaker = useRef(new DeviceSpeaker());

  useEffect(() => {
    dialogRef.current?.showModal();
    whenVoicesReady().then(() => setVoices({ de: listVoices("de"), en: listVoices("en") }));
    const s = speaker.current;
    return () => s.stop();
  }, []);

  const preview = (lang: Lang, voice: Voice) => {
    speaker.current.stop();
    speaker.current.rate = settings.rate;
    speaker.current.start(t.testSentenceFor(lang), lang, voice, settings.deviceVoices[`${lang}-${voice}`]);
  };

  return (
    <dialog ref={dialogRef} className="dialog" onClose={onClose} onClick={(e) => e.target === dialogRef.current && dialogRef.current?.close()}>
      <div className="dialog-body">
        <header className="dialog-head">
          <h2>{t.settings}</h2>
          <button className="icon-btn" onClick={() => dialogRef.current?.close()} aria-label={t.close}><X size={19} /></button>
        </header>

        <section className="setting">
          <h3>{t.language}</h3>
          <div className="segmented" role="group" aria-label={t.language}>
            <button className={settings.lang === "de" ? "active" : ""} onClick={() => update({ lang: "de" })}>Deutsch</button>
            <button className={settings.lang === "en" ? "active" : ""} onClick={() => update({ lang: "en" })}>English</button>
          </div>
        </section>

        <section className="setting">
          <h3>{t.theme}</h3>
          <div className="segmented" role="group" aria-label={t.theme}>
            <button className={settings.theme === "system" ? "active" : ""} onClick={() => update({ theme: "system" })}><Monitor size={15} /> {t.themeSystem}</button>
            <button className={settings.theme === "light" ? "active" : ""} onClick={() => update({ theme: "light" })}><Sun size={15} /> {t.themeLight}</button>
            <button className={settings.theme === "dark" ? "active" : ""} onClick={() => update({ theme: "dark" })}><Moon size={15} /> {t.themeDark}</button>
          </div>
        </section>

        <section className="setting">
          <h3>{t.voice}</h3>
          <div className="voice-cards">
            {(["female", "male"] as const).map((v) => (
              <button key={v} className={`voice-card${settings.voice === v ? " active" : ""}`} onClick={() => update({ voice: v })}
                aria-pressed={settings.voice === v}>
                <span className="voice-name">{v === "female" ? t.voiceFemale : t.voiceMale}</span>
                <span className="muted small">
                  {pickVoice(settings.lang, v, settings.deviceVoices[`${settings.lang}-${v}`])?.name ?? "—"}
                </span>
                <span className="voice-preview" role="button" tabIndex={0} aria-label={t.test}
                  onClick={(e) => { e.stopPropagation(); preview(settings.lang, v); }}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); preview(settings.lang, v); } }}>
                  <Play size={14} /> {t.test}
                </span>
              </button>
            ))}
          </div>
          <label className="setting-row">
            <span>{t.speed}</span>
            <input type="range" min={0.7} max={1.6} step={0.05} value={settings.rate}
              onChange={(e) => update({ rate: Number(e.target.value) })} />
            <span className="mono">{settings.rate.toFixed(2)}×</span>
          </label>
          <p className="muted small">{t.voiceHint}</p>
          {(["de", "en"] as const).map((lang) => (
            (["female", "male"] as const).map((v) => (
              <label className="setting-row" key={`${lang}-${v}`}>
                <span>{t.deviceVoice(lang.toUpperCase(), v === "female" ? t.voiceFemale : t.voiceMale)}</span>
                <select className="select" value={settings.deviceVoices[`${lang}-${v}`] ?? ""}
                  onChange={(e) => update({ deviceVoices: { ...settings.deviceVoices, [`${lang}-${v}`]: e.target.value } })}>
                  <option value="">{t.automatic}</option>
                  {voices[lang].map((voice) => <option key={voice.voiceURI} value={voice.voiceURI}>{voice.name} ({voice.lang})</option>)}
                </select>
              </label>
            ))
          ))}
        </section>
      </div>
    </dialog>
  );
}
