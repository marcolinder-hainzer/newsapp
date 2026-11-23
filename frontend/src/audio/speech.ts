/**
 * Vorlesen mit den Stimmen des Geräts (Web Speech API).
 * Wählt automatisch die natürlichste verfügbare Damen- bzw. Herrenstimme je Sprache.
 */
import type { Lang, Voice } from "../types";

const FEMALE = [
  "female", "frau", "weiblich", "seraphina", "katja", "amala", "louisa", "tanja", "vicki", "petra", "anna",
  "helena", "hedda", "marlene", "ingrid", "elke", "klara", "gisela", "maja", "ava", "aria", "jenny", "emma",
  "michelle", "samantha", "karen", "moira", "tessa", "serena", "victoria", "allison", "susan", "zira", "hazel",
  "libby", "sonia", "natasha", "sara", "joanna", "kendra", "kimberly", "salli", "ivy", "nicole", "amy",
  "google deutsch", "google us english", "google uk english female", "sabina", "lena", "julia",
];
const MALE = [
  "male", "mann", "männlich", "conrad", "florian", "killian", "kasper", "markus", "yannick", "stefan", "hans",
  "klaus", "ralf", "jonas", "bernd", "christoph", "guy", "andrew", "brian", "davis", "eric", "christopher",
  "roger", "steffan", "daniel", "alex", "fred", "tom", "aaron", "arthur", "oliver", "ryan", "thomas", "george",
  "david", "mark", "james", "matthew", "justin", "joey", "russell", "brandon", "google uk english male",
];
const QUALITY = /natural|neural|online|premium|enhanced|multilingual|wavenet|studio|siri/i;
const NOVELTY = /\b(bad news|bells|boing|bubbles|cellos|good news|jester|organ|superstar|trinoids|whisper|wobble|zarvox|albert|bahh|grandma|grandpa|rocko|shelley|flo|sandy|eddy|reed)\b/i;

function matches(name: string, list: string[]): boolean {
  const lower = name.toLowerCase();
  return list.some((w) => lower.includes(w));
}

export function voiceGender(v: SpeechSynthesisVoice): Voice | null {
  if (matches(v.name, MALE) && !/female/i.test(v.name)) return "male";
  if (matches(v.name, FEMALE)) return "female";
  return null;
}

export function listVoices(lang: Lang): SpeechSynthesisVoice[] {
  if (typeof speechSynthesis === "undefined") return [];
  return speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith(lang));
}

function score(v: SpeechSynthesisVoice, lang: Lang, gender: Voice): number {
  let s = 0;
  const g = voiceGender(v);
  if (g === gender) s += 20;
  else if (g === null) s += 5;
  else s -= 20;
  if (QUALITY.test(v.name)) s += 10;
  if (NOVELTY.test(v.name)) s -= 30;
  const region = v.lang.toLowerCase();
  if ((lang === "de" && region === "de-de") || (lang === "en" && (region === "en-us" || region === "en-gb"))) s += 3;
  if (!v.localService) s += 1; // Cloud-Stimmen sind meist natürlicher
  return s;
}

export function pickVoice(lang: Lang, gender: Voice, preferredURI?: string): SpeechSynthesisVoice | null {
  const voices = listVoices(lang);
  if (preferredURI) {
    const chosen = voices.find((v) => v.voiceURI === preferredURI);
    if (chosen) return chosen;
  }
  if (!voices.length) return null;
  return [...voices].sort((a, b) => score(b, lang, gender) - score(a, lang, gender))[0];
}

export function whenVoicesReady(): Promise<void> {
  if (typeof speechSynthesis === "undefined") return Promise.resolve();
  if (speechSynthesis.getVoices().length) return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      speechSynthesis.removeEventListener("voiceschanged", done);
      resolve();
    };
    speechSynthesis.addEventListener("voiceschanged", done);
    window.setTimeout(done, 1500);
  });
}

export function chunkText(text: string, maxLen = 220): string[] {
  const sentences = text.match(/[^.!?…]+[.!?…]+["“”»«')]*\s*|[^.!?…]+$/g) ?? [text];
  const chunks: string[] = [];
  let current = "";
  for (const raw of sentences) {
    const sentence = raw.trim();
    if (!sentence) continue;
    if ((current + " " + sentence).length > maxLen && current) {
      chunks.push(current);
      current = sentence;
    } else {
      current = current ? `${current} ${sentence}` : sentence;
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

/** Spricht Text satzweise; Pause/Fortsetzen funktioniert zuverlässig über Neustart des aktuellen Abschnitts. */
export class DeviceSpeaker {
  private chunks: string[] = [];
  private index = 0;
  private token = 0;
  private lang: Lang = "de";
  private voice: SpeechSynthesisVoice | null = null;
  rate = 1;
  onEnd: () => void = () => {};
  onProgress: (index: number, total: number) => void = () => {};
  onError: (message: string) => void = () => {};

  get supported(): boolean {
    return typeof speechSynthesis !== "undefined";
  }

  async start(text: string, lang: Lang, gender: Voice, preferredURI?: string) {
    this.stop();
    await whenVoicesReady();
    this.chunks = chunkText(text);
    this.index = 0;
    this.lang = lang;
    this.voice = pickVoice(lang, gender, preferredURI);
    this.speakCurrent();
  }

  private speakCurrent() {
    if (!this.supported) {
      this.onError("speechSynthesis not supported");
      return;
    }
    const token = ++this.token;
    if (this.index >= this.chunks.length) {
      this.onEnd();
      return;
    }
    this.onProgress(this.index, this.chunks.length);
    const utterance = new SpeechSynthesisUtterance(this.chunks[this.index]);
    utterance.lang = this.voice?.lang ?? (this.lang === "de" ? "de-DE" : "en-US");
    if (this.voice) utterance.voice = this.voice;
    utterance.rate = this.rate;
    utterance.onend = () => {
      if (token !== this.token) return;
      this.index += 1;
      this.speakCurrent();
    };
    utterance.onerror = (event) => {
      if (token !== this.token || event.error === "interrupted" || event.error === "canceled") return;
      this.onError(event.error);
    };
    speechSynthesis.speak(utterance);
  }

  pause() {
    this.token++;
    if (this.supported) speechSynthesis.cancel();
  }

  resume() {
    this.speakCurrent();
  }

  stop() {
    this.token++;
    this.chunks = [];
    this.index = 0;
    if (this.supported) speechSynthesis.cancel();
  }

  skip(delta: number) {
    this.token++;
    if (this.supported) speechSynthesis.cancel();
    this.index = Math.max(0, Math.min(this.chunks.length, this.index + delta));
    this.speakCurrent();
  }
}
