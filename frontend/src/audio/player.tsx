import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { LoaderCircle, Pause, Play, SkipBack, SkipForward, X } from "lucide-react";
import { useApp } from "../settings";
import type { Lang } from "../types";
import { DeviceSpeaker } from "./speech";

/** Ein Vorlese-Titel. Vorgelesen wird kostenlos mit den Stimmen des Geräts. */
export interface Track {
  key: string;
  title: string;
  lang: Lang;
  /** Liefert Text und tatsächliche Sprache */
  getSpeech: () => Promise<{ text: string; lang: Lang }>;
  href?: string;
}

type Status = "idle" | "loading" | "playing" | "paused";

interface PlayerValue {
  queue: Track[];
  index: number;
  status: Status;
  current: Track | null;
  progress: number; // 0..1
  play: (tracks: Track[], start?: number) => void;
  toggle: () => void;
  stop: () => void;
  next: () => void;
  previous: () => void;
  isCurrent: (key: string) => boolean;
}

const PlayerContext = createContext<PlayerValue | null>(null);

export function usePlayer(): PlayerValue {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error("usePlayer außerhalb von PlayerProvider");
  return ctx;
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const { settings } = useApp();
  const [queue, setQueue] = useState<Track[]>([]);
  const [index, setIndex] = useState(0);
  const [status, setStatus] = useState<Status>("idle");
  const [progress, setProgress] = useState(0);

  const speakerRef = useRef<DeviceSpeaker | null>(null);
  if (!speakerRef.current) speakerRef.current = new DeviceSpeaker();
  const stateRef = useRef({ queue, index, status });
  stateRef.current = { queue, index, status };
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const attemptRef = useRef(0);
  const advanceRef = useRef<() => void>(() => {});

  const startTrack = useCallback(async (track: Track) => {
    const attempt = ++attemptRef.current;
    const speaker = speakerRef.current!;
    speaker.stop();
    setProgress(0);
    setStatus("loading");
    let speech = { text: track.title, lang: track.lang };
    try {
      speech = await track.getSpeech();
    } catch {
      /* dann wird nur der Titel vorgelesen */
    }
    if (attempt !== attemptRef.current) return; // inzwischen anderer Titel gewählt
    const s = settingsRef.current;
    speaker.rate = s.rate;
    setStatus("playing");
    await speaker.start(speech.text, speech.lang, s.voice, s.deviceVoices[`${speech.lang}-${s.voice}`]);
  }, []);

  useEffect(() => {
    const speaker = speakerRef.current!;
    speaker.onEnd = () => advanceRef.current();
    speaker.onProgress = (i, total) => setProgress(total ? i / total : 0);
    speaker.onError = () => advanceRef.current();
  }, []);

  const goTo = useCallback((i: number, q?: Track[]) => {
    const list = q ?? stateRef.current.queue;
    if (i < 0 || i >= list.length) {
      attemptRef.current++;
      speakerRef.current?.stop();
      setStatus("idle");
      setQueue([]);
      setIndex(0);
      setProgress(0);
      return;
    }
    setIndex(i);
    startTrack(list[i]);
  }, [startTrack]);

  advanceRef.current = () => goTo(stateRef.current.index + 1);

  const play = useCallback((tracks: Track[], start = 0) => {
    if (!tracks.length) return;
    setQueue(tracks);
    goTo(start, tracks);
  }, [goTo]);

  const toggle = useCallback(() => {
    const speaker = speakerRef.current!;
    const st = stateRef.current.status;
    if (st === "playing" || st === "loading") {
      speaker.pause();
      setStatus("paused");
    } else if (st === "paused") {
      speaker.resume();
      setStatus("playing");
    }
  }, []);

  const stop = useCallback(() => goTo(-1), [goTo]);
  const next = useCallback(() => goTo(stateRef.current.index + 1), [goTo]);
  const previous = useCallback(() => goTo(Math.max(0, stateRef.current.index - 1)), [goTo]);

  // Tempo live übernehmen (gilt ab dem nächsten Satz)
  useEffect(() => {
    if (speakerRef.current) speakerRef.current.rate = settings.rate;
  }, [settings.rate]);

  // Stimmenwechsel während der Wiedergabe: aktuellen Titel mit neuer Stimme neu starten
  const voiceRef = useRef(settings.voice);
  useEffect(() => {
    if (voiceRef.current === settings.voice) return;
    voiceRef.current = settings.voice;
    const { status: st, queue: q, index: i } = stateRef.current;
    if (st !== "idle" && q[i]) startTrack(q[i]);
  }, [settings.voice, startTrack]);

  const current = queue[index] ?? null;

  // Sperrbildschirm-/Medientasten-Steuerung
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    if (!current) {
      navigator.mediaSession.metadata = null;
      return;
    }
    navigator.mediaSession.metadata = new MediaMetadata({ title: current.title, artist: "Weitblick", album: "Nachrichten" });
    navigator.mediaSession.setActionHandler("play", toggle);
    navigator.mediaSession.setActionHandler("pause", toggle);
    navigator.mediaSession.setActionHandler("nexttrack", next);
    navigator.mediaSession.setActionHandler("previoustrack", previous);
    navigator.mediaSession.setActionHandler("stop", stop);
  }, [current, toggle, next, previous, stop]);

  const value = useMemo<PlayerValue>(() => ({
    queue, index, status, current, progress, play, toggle, stop, next, previous,
    isCurrent: (key: string) => !!current && current.key === key && status !== "idle",
  }), [queue, index, status, current, progress, play, toggle, stop, next, previous]);

  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}

const RATES = [0.8, 0.9, 1, 1.15, 1.3, 1.5];

export function PlayerBar() {
  const { t, settings, update } = useApp();
  const player = usePlayer();
  if (!player.current) return null;
  const { current, status, queue, index } = player;
  const playing = status === "playing" || status === "loading";
  return (
    <div className="player" role="region" aria-label={t.nowPlaying}>
      <div className="player-progress" aria-hidden="true">
        <div style={{ width: `${Math.round(player.progress * 100)}%` }} />
      </div>
      <div className="player-inner">
        <button className="icon-btn" onClick={player.previous} aria-label={t.previous} disabled={index === 0}>
          <SkipBack size={18} />
        </button>
        <button className="play-btn" onClick={player.toggle} aria-label={playing ? t.pause : t.resume}>
          {status === "loading" ? <LoaderCircle size={22} className="spin" /> : playing ? <Pause size={22} /> : <Play size={22} />}
        </button>
        <button className="icon-btn" onClick={player.next} aria-label={t.next} disabled={index >= queue.length - 1}>
          <SkipForward size={18} />
        </button>
        <div className="player-title">
          <span className="player-kicker">
            {t.nowPlaying}
            {queue.length > 1 && ` · ${index + 1}/${queue.length}`}
          </span>
          {current.href ? <Link to={current.href}>{current.title}</Link> : <span>{current.title}</span>}
        </div>
        <div className="player-controls">
          <div className="segmented small" role="group" aria-label={t.voice}>
            <button className={settings.voice === "female" ? "active" : ""} onClick={() => update({ voice: "female" })}
              aria-pressed={settings.voice === "female"} title={t.voiceFemale}>
              {settings.lang === "de" ? "Sie" : "She"}
            </button>
            <button className={settings.voice === "male" ? "active" : ""} onClick={() => update({ voice: "male" })}
              aria-pressed={settings.voice === "male"} title={t.voiceMale}>
              {settings.lang === "de" ? "Er" : "He"}
            </button>
          </div>
          <label className="rate">
            <span className="sr-only">{t.speed}</span>
            <select value={settings.rate} onChange={(e) => update({ rate: Number(e.target.value) })} aria-label={t.speed}>
              {RATES.map((r) => <option key={r} value={r}>{r.toString().replace(".", settings.lang === "de" ? "," : ".")}×</option>)}
            </select>
          </label>
          <button className="icon-btn" onClick={player.stop} aria-label={t.stop}>
            <X size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
