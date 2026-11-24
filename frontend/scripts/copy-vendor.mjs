// Kopiert die Laufzeitdateien für die natürliche Sprachausgabe (Piper) nach public/vendor,
// damit sie zusammen mit der App ausgeliefert werden (kein fremdes CDN nötig).
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const files = [
  ["node_modules/onnxruntime-web/dist/ort.wasm.min.js", "public/vendor/ort/ort.wasm.min.js"],
  ["node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs", "public/vendor/ort/ort-wasm-simd-threaded.mjs"],
  ["node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm", "public/vendor/ort/ort-wasm-simd-threaded.wasm"],
  ["node_modules/@diffusionstudio/piper-wasm/build/piper_phonemize.js", "public/vendor/piper/piper_phonemize.js"],
  ["node_modules/@diffusionstudio/piper-wasm/build/piper_phonemize.wasm", "public/vendor/piper/piper_phonemize.wasm"],
  ["node_modules/@diffusionstudio/piper-wasm/build/piper_phonemize.data", "public/vendor/piper/piper_phonemize.data"],
];
for (const [from, to] of files) {
  mkdirSync(dirname(join(root, to)), { recursive: true });
  copyFileSync(join(root, from), join(root, to));
}
console.log(`Sprachausgabe: ${files.length} Laufzeitdateien nach public/vendor kopiert`);
