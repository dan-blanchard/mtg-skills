import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// base "./" keeps asset URLs relative so FastAPI can serve the built bundle from
// the site root. In dev, proxy the API + SSE stream to the backend hub.
export default defineConfig({
  plugins: [svelte()],
  base: "./",
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        // Disable buffering so the SSE event stream flows through immediately.
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => proxyReq.setHeader("accept-encoding", "identity"));
        },
      },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
