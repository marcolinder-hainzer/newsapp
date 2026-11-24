/**
 * Natürliche Stimmen mit Piper (Open Source) – die Sprache wird direkt auf dem Gerät erzeugt.
 * Kostenlos, ohne Server und mit echten Damen- und Herrenstimmen für Deutsch und Englisch.
 * Die Stimmmodelle stammen aus dem offiziellen Piper-Stimmenarchiv (rhasspy/piper-voices).
 */
import type { Lang, Voice } from "../types";
import { chunkText } from "./speech";

const HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main";

export interface NaturalVoice {
  key: string;
  name: string;
  model: string;
  config: string;
  sizeMb: number;
}

function piperVoice(path: string, name: string, sizeMb = 63): NaturalVoice {
  const key = path.split("/").pop()!;
  return { key, name, model: `${HF}/${path}.onnx`, config: `${HF}/${path}.onnx.json`, sizeMb };
}

export const NATURAL_VOICES: Record<Lang, Record<Voice, NaturalVoice>> = {
  de: {
    female: piperVoice("de/de_DE/kerstin/low/de_DE-kerstin-low", "Kerstin"),
    male: piperVoice("de/de_DE/thorsten/medium/de_DE-thorsten-medium", "Thorsten"),
  },
  en: {
    female: piperVoice("en/en_US/lessac/medium/en_US-lessac-medium", "Lessac"),
    male: piperVoice("en/en_US/ryan/medium/en_US-ryan-medium", "Ryan"),
  },
};

export function naturalSupported(): boolean {
  return typeof Worker !== "undefined" && typeof WebAssembly === "object" && typeof BigInt64Array !== "undefined";
}

type Pending = {
  resolve: (value: any) => void;
  reject: (error: Error) => void;
  onProgress?: (fraction: number | null) => void;
};

/** Spricht mit dem Web Worker, der Piper ausführt. */
class PiperClient {
  private worker: Worker | null = null;
  private seq = 0;
  private pending = new Map<number, Pending>();
  private loaded = new Set<string>();

  private getWorker(): Worker {
    if (!this.worker) {
      this.worker = new Worker(`${import.meta.env.BASE_URL}piper-worker.js`);
      this.worker.onmessage = (event) => {
        const msg = event.data;
        const entry = this.pending.get(msg.id);
        if (!entry) return;
        if (msg.type === "progress") {
          entry.onProgress?.(msg.total ? msg.loaded / msg.total : null);
          return;
        }
        this.pending.delete(msg.id);
        if (msg.type === "error") entry.reject(new Error(msg.message));
        else entry.resolve(msg);
      };
      this.worker.onerror = (event) => {
        const error = new Error(event.message || "Sprachausgabe konnte nicht gestartet werden");
        this.pending.forEach((p) => p.reject(error));
        this.pending.clear();
        this.worker?.terminate();
        this.worker = null;
      };
    }
    return this.worker;
  }

  private request<T>(message: object, onProgress?: (fraction: number | null) => void): Promise<T> {
    const id = ++this.seq;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject, onProgress });
      this.getWorker().postMessage({ ...message, id });
    });
  }

  isLoaded(voice: NaturalVoice): boolean {
    return this.loaded.has(voice.key);
  }

  async load(voice: NaturalVoice, onProgress?: (fraction: number | null) => void): Promise<void> {
    if (this.loaded.has(voice.key)) return;
    await this.request({ type: "load", voice }, onProgress);
    this.loaded.add(voice.key);
  }

  async speak(voice: NaturalVoice, text: string): Promise<{ wav: ArrayBuffer; duration: number }> {
    return this.request({ type: "speak", voice, text, lengthScale: 1 });
  }
}

export const piper = new PiperClient();

/** Kurzes stilles WAV, um die Audiowiedergabe auf iPhone/iPad per Fingertipp freizuschalten. */
const SILENT_WAV = "data:audio/wav;base64,UklGRmQBAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YUABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==";

/**
 * Liest Text mit einer natürlichen Stimme vor: erzeugt Satzgruppen nacheinander und spielt sie
 * lückenlos ab, während im Hintergrund schon der nächste Abschnitt entsteht.
 */
export class NaturalSpeaker {
  private audio: HTMLAudioElement;
  private token = 0;
  private chunks: string[] = [];
  private index = 0;
  private voice: NaturalVoice | null = null;
  private clips = new Map<number, Promise<string>>();
  private paused = false;
  rate = 1;
  onEnd: () => void = () => {};
  onProgress: (index: number, total: number) => void = () => {};
  onError: (message: string) => void = () => {};
  onLoading: (fraction: number | null) => void = () => {};

  constructor() {
    this.audio = new Audio();
    this.audio.preload = "auto";
    (this.audio as HTMLAudioElement & { preservesPitch?: boolean }).preservesPitch = true;
    this.audio.addEventListener("ended", () => {
      if (this.audio.src.startsWith("data:")) return;
      this.playIndex(this.index + 1, this.token);
    });
  }

  /** Muss direkt im Klick-Handler aufgerufen werden (iOS-Autoplay-Regeln). */
  unlock() {
    this.audio.src = SILENT_WAV;
    this.audio.play().catch(() => undefined);
  }

  async start(text: string, lang: Lang, gender: Voice) {
    this.stop();
    this.paused = false;
    const token = this.token;
    this.voice = NATURAL_VOICES[lang][gender];
    // Erster Abschnitt kurz halten, damit die Wiedergabe schnell beginnt
    const sentences = chunkText(text, 160);
    this.chunks = sentences.length ? sentences : [text];
    this.index = 0;
    try {
      if (!piper.isLoaded(this.voice)) {
        this.onLoading(0);
        await piper.load(this.voice, (fraction) => token === this.token && this.onLoading(fraction));
        if (token !== this.token) return;
        this.onLoading(null);
      }
      await this.playIndex(0, token);
    } catch (error) {
      if (token === this.token) this.onError((error as Error).message);
    }
  }

  private clip(i: number): Promise<string> {
    if (!this.clips.has(i)) {
      const voice = this.voice!;
      const promise = piper.speak(voice, this.chunks[i]).then(({ wav }) =>
        URL.createObjectURL(new Blob([wav], { type: "audio/wav" })));
      this.clips.set(i, promise);
    }
    return this.clips.get(i)!;
  }

  private async playIndex(i: number, token: number) {
    if (token !== this.token) return;
    if (i >= this.chunks.length) {
      this.onEnd();
      return;
    }
    this.index = i;
    try {
      const url = await this.clip(i);
      if (token !== this.token) return;
      if (i + 1 < this.chunks.length) this.clip(i + 1).catch(() => undefined); // schon vorbereiten
      this.audio.src = url;
      this.audio.playbackRate = this.rate;
      this.onProgress(i, this.chunks.length);
      if (!this.paused) await this.audio.play();
      this.audio.playbackRate = this.rate;
    } catch (error) {
      if (token === this.token) this.onError((error as Error).message);
    }
  }

  setRate(rate: number) {
    this.rate = rate;
    this.audio.playbackRate = rate;
  }

  pause() {
    this.paused = true;
    this.audio.pause();
  }

  resume() {
    this.paused = false;
    if (this.audio.src && !this.audio.src.startsWith("data:")) this.audio.play().catch(() => undefined);
  }

  stop() {
    this.token++;
    this.audio.pause();
    this.clips.forEach((p) => p.then((url) => URL.revokeObjectURL(url)).catch(() => undefined));
    this.clips.clear();
    this.chunks = [];
    this.index = 0;
  }

  /** Kurze Hörprobe (z. B. in den Einstellungen). */
  async preview(text: string, lang: Lang, gender: Voice) {
    await this.start(text, lang, gender);
  }
}
