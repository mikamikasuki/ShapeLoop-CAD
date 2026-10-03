import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
const backend = process.env.SHAPELOOP_API_URL || "http://127.0.0.1:8765";
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: backend,
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (request) => request.removeHeader("origin"));
        },
      },
      "/artifacts": backend,
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
