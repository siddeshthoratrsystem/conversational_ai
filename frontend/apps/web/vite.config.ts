/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  server: { proxy: { "/api": "http://localhost:8000" } },
  // Spec 009: the hidden page used for silent sign-in is a second entry next to the app.
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(import.meta.dirname, "index.html"),
        silent: path.resolve(import.meta.dirname, "silent-callback.html"),
      },
    },
  },
  // The theme test reads principal.css as text; Vitest skips CSS unless included.
  test: { environment: "jsdom", css: { include: [/principal\.css/] } },
});
