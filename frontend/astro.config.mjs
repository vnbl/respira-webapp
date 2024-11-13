import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";
import react from "@astrojs/react";
import lottie from "astro-integration-lottie";
import svgr from "vite-plugin-svgr"
import node from "@astrojs/node";
import { loadEnv } from "vite";
const { SITE_URL } = loadEnv(process.env.NODE_ENV, process.cwd(), "");

// https://astro.build/config
export default defineConfig({
  vite: {
    server: {
      watch: {
        usePolling: true,
      },
    },
    plugins: [
      svgr({
        include: '**/*.svg?react',
        svgrOptions: {
          plugins: ['@svgr/plugin-svgo', '@svgr/plugin-jsx'],
          svgoConfig: {
            plugins: ['preset-default', 'removeTitle', 'removeDesc', 'removeDoctype', 'cleanupIds'],
          },
          icon: true,
          
        },
      }),
    ],
  },

  site: SITE_URL || "http://localhost",
  base: "/",
  output: "hybrid",
  srcDir: "./src",
  integrations: [react(), tailwind(), lottie()],
  adapter: node({
    mode: "standalone",
  }),
});
