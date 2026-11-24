// Prüft die natürlichen Stimmen in echten Browser-Engines (Chromium und WebKit = Safari):
// lädt jedes in src/audio/natural.ts eingetragene Stimmmodell und erzeugt einen Testsatz.
// Aufruf (nach `npm run copy-vendor`):  node scripts/voice-check.mjs
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync } from "node:fs";
import { extname, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "playwright";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const publicDir = join(root, "public");
const source = readFileSync(join(root, "src/audio/natural.ts"), "utf8");
const HF = source.match(/const HF = "([^"]+)"/)[1];
const voices = [...source.matchAll(/piperVoice\("([^"]+)", "([^"]+)"\)/g)].map(([, path, name]) => ({
  key: path.split("/").pop(), name, model: `${HF}/${path}.onnx`, config: `${HF}/${path}.onnx.json`,
  lang: path.startsWith("de/") ? "de" : "en",
}));
const SENTENCES = {
  de: "Guten Tag. Der Bundestag hat heute über den Haushalt für das kommende Jahr beraten.",
  en: "Good evening. Parliament has debated the budget for the coming year.",
};

const TEST_PAGE = `<!doctype html><html><body><script>
window.check = (voice, text) => new Promise((resolve) => {
  const worker = new Worker('/piper-worker.js');
  const t0 = performance.now();
  let t1 = 0;
  worker.onmessage = (e) => {
    const m = e.data;
    if (m.type === 'loaded') { t1 = performance.now(); worker.postMessage({ type: 'speak', id: 2, voice, text, lengthScale: 1 }); }
    if (m.type === 'audio') { resolve({ ok: true, loadMs: Math.round(t1 - t0), synthMs: Math.round(performance.now() - t1), seconds: +m.duration.toFixed(2) }); worker.terminate(); }
    if (m.type === 'error') { resolve({ ok: false, error: m.message }); worker.terminate(); }
  };
  worker.onerror = (e) => resolve({ ok: false, error: 'worker: ' + e.message });
  worker.postMessage({ type: 'load', id: 1, voice });
});
</script></body></html>`;

const TYPES = { ".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm", ".data": "application/octet-stream" };
const server = createServer((req, res) => {
  const path = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (path === "/voice-test.html") {
    res.writeHead(200, { "Content-Type": "text/html" });
    return res.end(TEST_PAGE);
  }
  const file = join(publicDir, path);
  if (!file.startsWith(publicDir) || !existsSync(file) || statSync(file).isDirectory()) {
    res.writeHead(404);
    return res.end();
  }
  res.writeHead(200, { "Content-Type": TYPES[extname(file)] || "application/octet-stream" });
  res.end(readFileSync(file));
});
await new Promise((r) => server.listen(8123, r));

let failures = 0;
for (const [label, engine] of [["Chromium", chromium], ["WebKit (Safari)", webkit]]) {
  const browser = await engine.launch();
  const page = await browser.newPage();
  await page.goto("http://localhost:8123/voice-test.html");
  for (const voice of voices) {
    const result = await page.evaluate(([v, t]) => window.check(v, t), [voice, SENTENCES[voice.lang]]);
    if (!result.ok || result.seconds < 1) failures++;
    console.log(`${result.ok ? "OK  " : "FEHLER"} ${label.padEnd(16)} ${voice.key.padEnd(30)} ${voice.name.padEnd(9)} ` +
      (result.ok ? `Laden ${result.loadMs} ms, Erzeugen ${result.synthMs} ms, Audio ${result.seconds} s` : result.error));
  }
  await browser.close();
}
server.close();
console.log(failures ? `\n${failures} Prüfung(en) fehlgeschlagen.` : "\nAlle Stimmen funktionieren.");
process.exit(failures ? 1 : 0);
