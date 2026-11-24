/*
 * Natürliche Sprachausgabe komplett im Browser – kostenlos und ohne Server.
 *
 * Verwendet Piper (Open-Source-Sprachsynthese, https://github.com/rhasspy/piper):
 *   - piper_phonemize (espeak-ng als WebAssembly) wandelt Text in Lautschrift um,
 *   - onnxruntime-web führt das neuronale Stimmmodell aus.
 * Stimmmodelle und Laufzeitdateien werden einmalig geladen und im Cache Storage des
 * Browsers gespeichert (funktioniert auch auf iPhone/iPad).
 *
 * Nachrichten an den Worker:
 *   { type: "load",  id, voice: { key, model, config } }
 *   { type: "speak", id, voice: { key, model, config }, text, lengthScale }
 * Antworten:
 *   { type: "progress", id, loaded, total }
 *   { type: "loaded", id }
 *   { type: "audio", id, wav: ArrayBuffer, duration }
 *   { type: "error", id, message }
 */
/* global ort, createPiperPhonemize */

const VENDOR = new URL("./vendor/", self.location).href;
const CACHE_NAME = "weitblick-voices-v1";

importScripts(VENDOR + "ort/ort.wasm.min.js");
importScripts(VENDOR + "piper/piper_phonemize.js");

ort.env.wasm.numThreads = 1; // GitHub Pages erlaubt kein SharedArrayBuffer
ort.env.wasm.wasmPaths = VENDOR + "ort/";

let phonemizerAssets = null;
const voices = new Map(); // key -> Promise<{ session, config }>

async function openCache() {
  try {
    return await caches.open(CACHE_NAME);
  } catch {
    return null; // z. B. privater Modus – dann ohne Zwischenspeicher
  }
}

async function cachedFetch(url, onProgress) {
  const cache = await openCache();
  if (cache) {
    const hit = await cache.match(url);
    if (hit) return hit.arrayBuffer();
  }
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Download fehlgeschlagen (${response.status}): ${url}`);
  const total = Number(response.headers.get("Content-Length")) || 0;
  let buffer;
  if (response.body && onProgress) {
    const reader = response.body.getReader();
    const chunks = [];
    let loaded = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      loaded += value.length;
      onProgress(loaded, total);
    }
    const bytes = new Uint8Array(loaded);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.length;
    }
    buffer = bytes.buffer;
  } else {
    buffer = await response.arrayBuffer();
  }
  if (cache) {
    try {
      await cache.put(url, new Response(buffer.slice(0), { headers: { "Content-Type": "application/octet-stream" } }));
    } catch {
      /* Speicher voll o. Ä. – dann eben ohne Zwischenspeicher */
    }
  }
  return buffer;
}

async function loadPhonemizer() {
  if (!phonemizerAssets) {
    phonemizerAssets = Promise.all([
      cachedFetch(VENDOR + "piper/piper_phonemize.wasm"),
      cachedFetch(VENDOR + "piper/piper_phonemize.data"),
    ]).then(([wasm, data]) => ({ wasm, data }));
  }
  return phonemizerAssets;
}

async function phonemize(text, espeakVoice) {
  const { wasm, data } = await loadPhonemizer();
  return new Promise((resolve, reject) => {
    let finished = false;
    createPiperPhonemize({
      wasmBinary: wasm,
      getPreloadedPackage: () => data.slice(0),
      locateFile: (path) => VENDOR + "piper/" + path,
      print: (line) => {
        if (finished) return;
        try {
          const parsed = JSON.parse(line);
          finished = true;
          resolve({ ids: parsed.phoneme_ids, phonemes: parsed.phonemes });
        } catch {
          /* andere Ausgaben ignorieren */
        }
      },
      printErr: () => {},
    })
      .then((module) => {
        module.callMain(["-l", espeakVoice, "--input", JSON.stringify([{ text }]), "--espeak_data", "/espeak-ng-data"]);
        if (!finished) setTimeout(() => !finished && reject(new Error("Lautschrift fehlgeschlagen")), 2000);
      })
      .catch(reject);
  });
}

function loadVoice(voice, onProgress) {
  if (!voices.has(voice.key)) {
    const promise = (async () => {
      const [configBuffer, modelBuffer] = await Promise.all([
        cachedFetch(voice.config),
        cachedFetch(voice.model, onProgress),
        loadPhonemizer(),
      ]);
      const config = JSON.parse(new TextDecoder().decode(configBuffer));
      const session = await ort.InferenceSession.create(new Uint8Array(modelBuffer), {
        executionProviders: ["wasm"],
        graphOptimizationLevel: "all",
      });
      return { session, config };
    })();
    promise.catch(() => voices.delete(voice.key));
    voices.set(voice.key, promise);
  }
  return voices.get(voice.key);
}

function toWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  // Lautstärke normalisieren (Piper-Ausgaben sind teils recht leise)
  let peak = 0;
  for (let i = 0; i < samples.length; i++) peak = Math.max(peak, Math.abs(samples[i]));
  const gain = peak > 0 ? Math.min(4, 0.95 / peak) : 1;
  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i] * gain));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

/** Lautschrift → Modell-IDs mit der Zuordnungstabelle des jeweiligen Stimmmodells. */
function phonemeIds(result, config) {
  const map = config.phoneme_id_map;
  if (!map || !result.phonemes) return result.ids;
  const pad = map["_"] || [0];
  const ids = [...(map["^"] || [1]), ...pad];
  for (const phoneme of result.phonemes) {
    const id = map[phoneme];
    if (!id) continue; // unbekannte Zeichen überspringen
    ids.push(...id, ...pad);
  }
  ids.push(...(map["$"] || [2]));
  return ids;
}

async function speak(voice, text, lengthScale) {
  const { session, config } = await loadVoice(voice);
  const ids = phonemeIds(await phonemize(text, config.espeak.voice), config);
  const inference = config.inference || {};
  const feeds = {
    input: new ort.Tensor("int64", BigInt64Array.from(ids, (v) => BigInt(v)), [1, ids.length]),
    input_lengths: new ort.Tensor("int64", BigInt64Array.from([BigInt(ids.length)]), [1]),
    scales: new ort.Tensor("float32", Float32Array.from([
      inference.noise_scale ?? 0.667,
      (inference.length_scale ?? 1) * (lengthScale || 1),
      inference.noise_w ?? 0.8,
    ]), [3]),
  };
  if ((config.num_speakers || 1) > 1) {
    feeds.sid = new ort.Tensor("int64", BigInt64Array.from([BigInt(voice.speaker || 0)]), [1]);
  }
  const result = await session.run(feeds);
  const samples = result.output.data;
  const sampleRate = config.audio.sample_rate;
  return { wav: toWav(samples, sampleRate), duration: samples.length / sampleRate };
}

self.onmessage = async (event) => {
  const { type, id, voice } = event.data;
  try {
    if (type === "load") {
      await loadVoice(voice, (loaded, total) => self.postMessage({ type: "progress", id, loaded, total }));
      self.postMessage({ type: "loaded", id });
    } else if (type === "speak") {
      const { wav, duration } = await speak(voice, event.data.text, event.data.lengthScale);
      self.postMessage({ type: "audio", id, wav, duration }, [wav]);
    }
  } catch (error) {
    self.postMessage({ type: "error", id, message: String((error && error.message) || error) });
  }
};
