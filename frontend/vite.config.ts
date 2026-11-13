import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react-swc";
import { defineConfig, loadEnv } from "vite";

// In development the browser talks only to Vite (port 3000). Vite forwards /api and /docs
// to the FastAPI backend, so the app always calls relative URLs and never needs CORS.
// In Docker, nginx does the same forwarding (see nginx.conf).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendUrl = env.VITE_BACKEND_URL?.trim() || "http://localhost:8080";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 3000,
      proxy: {
        "/api": { target: backendUrl, changeOrigin: true },
        "/docs": { target: backendUrl, changeOrigin: true },
        "/openapi.json": { target: backendUrl, changeOrigin: true },
      },
    },
  };
});
