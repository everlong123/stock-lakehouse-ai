import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      host: "127.0.0.1",
      proxy: {
        "/api/v1": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          secure: false,
        },
      },
    },
    build: {
      // WHY THE VENDOR IS SPLIT
      // -----------------------
      // The build produced a single 871 kB bundle (253 kB gzipped) that
      // the browser had to download before the first page appeared.
      // The pages are now split with `React.lazy`, but the libraries
      // they share - the charting library, the markdown renderer, the
      // query client - stayed in the main chunk.
      //
      // Splitting them by library means the browser downloads and
      // caches each library ONCE, and a change to an application page
      // does not invalidate the library cache.
      rollupOptions: {
        output: {
          manualChunks: {
            react: ["react", "react-dom", "react-router-dom"],
            charts: ["recharts"],
            query: ["@tanstack/react-query"],
          },
        },
      },
      // The charting library alone is larger than this. The warning was
      // only noise before the split; now it names a real, separate
      // chunk that the browser caches on its own.
      chunkSizeWarningLimit: 700,
    },
  };
});
