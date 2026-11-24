import { LoaderCircle, Moon, Monitor, Play, Sun, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NATURAL_VOICES, NaturalSpeaker, naturalSupported } from "../audio/natural";
import { usePlayer } from "../audio/player";
import { DeviceSpeaker, listVoices, pickVoice, voiceGender, whenVoicesReady } from "../audio/speech";
import { useApp } from "../settings";
import type { Lang, Voice } from "../types";

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { t, settings, update } = useApp();
  const player = usePlayer();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [voices, setVoices] = useState<Record<Lang, SpeechSynthesisVoice[]>>({ de: [], en: [] });
  const [previewLoading, setPreviewLoading] = useState<number | null>(null);
  const device = useRef(new DeviceSpeaker());
  const natural = useRef<NaturalSpeaker | null>(naturalSupported() ? new NaturalSpeaker() : null);
  const naturalOn = settings.voiceEngine === "natural" && !!natural.current;

  useEffect(() => {
    dialogRef.current?.showModal();
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

  const langName = settings.lang === "de" ? "Deutsch" : "English";
  const hasDeviceMale = voices[settings.lang].some((v) => voiceGender(v) === "male");

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
          <h3>{t.voiceEngine}</h3>
          <div className="segmented" role="group" aria-label={t.voiceEngine}>
            <button className={settings.voiceEngine === "natural" ? "active" : ""} disabled={!natural.current}
              onClick={() => update({ voiceEngine: "natural" })}>{t.engineNatural}</button>
            <button className={settings.voiceEngine === "device" ? "active" : ""}
              onClick={() => update({ voiceEngine: "device" })}>{t.engineDevice}</button>
          </div>
          <p className="muted small">{naturalOn ? t.engineNaturalHint : t.engineDeviceHint}</p>
        </section>

        <section className="setting">
          <h3>{t.voice}</h3>
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
          <label className="setting-row">
            <span>{t.speed}</span>
            <input type="range" min={0.7} max={1.6} step={0.05} value={settings.rate}
              onChange={(e) => update({ rate: Number(e.target.value) })} />
            <span className="mono">{settings.rate.toFixed(2)}×</span>
          </label>
          {!naturalOn && (
            <>
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
            </>
          )}
        </section>
      </div>
    </dialog>
  );
}
