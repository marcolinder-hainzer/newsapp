import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Für GitHub Pages: VITE_BASE=/<repository-name>/
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
