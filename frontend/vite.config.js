import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard calls /api/... ; in development Vite forwards those calls to the backend.
const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true, proxy: { "/api": backend } },
  preview: { port: 5173, proxy: { "/api": backend } },
});
