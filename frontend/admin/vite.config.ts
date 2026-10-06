import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * DEV ONLY — REMOVE IN T7 STAGE C (docs/plans/t7-hotspot.md §13.1 e).
 *
 * Until T8 provides GET /api/images/{id}, serve frontend/dev-images/{id}.png for that
 * route so a hotspot question can be authored under `vite` dev (copy of the host app's plugin). `apply: 'serve'` means
 * this plugin never runs in `vite build`; the PNGs live outside the app, so nothing
 * here can reach a production bundle. It rewrites the URL to Vite's documented /@fs/
 * file serving (allowed via server.fs.allow below) ahead of the /api proxy, so no Node
 * APIs are needed. A missing file falls through to Vite's HTML fallback, which
 * lib/images.ts rejects as "not an image" → the canvas shows "Image unavailable".
 */
function devImages(): Plugin {
  return {
    name: 'buzzer-dev-images',
    apply: 'serve',
    configureServer(server) {
      const devImagesDir = `${server.config.root.replace(/\/+$/, '').replace(/\/[^/]+$/, '')}/dev-images`;
      server.middlewares.use((req, _res, next) => {
        // The app has no @types/node, so Node's request type lacks `url`; it is there at runtime.
        const r = req as unknown as { url?: string };
        const match = r.url?.match(/^\/api\/images\/(\d+)(\?.*)?$/);
        if (match) r.url = `/@fs${devImagesDir}/${match[1]}.png`;
        next();
      });
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), devImages()],
  base: mode === 'production' ? '/admin/' : '/',
  server: {
    port: 5175,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
    // DEV ONLY (with devImages above): let /@fs/ serve ../dev-images. Remove in stage C.
    fs: { allow: ['.', '../dev-images'] },
  },
}));
