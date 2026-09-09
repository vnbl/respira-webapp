// LOCAL ONLY — for trying the dashboard against a local backend in a browser.
// Not part of the build; delete when you're done.
//
// Serves /api from the local Django instance so the browser sees a single
// origin, the same shape nginx gives it in production (and the same trick
// docker-compose.override.yml uses to consume demo without CORS).
import base from "./astro.config.mjs";

export default {
  ...base,
  vite: {
    ...base.vite,
    server: {
      ...(base.vite?.server ?? {}),
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8099",
          changeOrigin: false,
        },
      },
    },
  },
};
