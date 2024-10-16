import { defineConfig } from 'astro/config';
import tailwind from "@astrojs/tailwind";
import react from '@astrojs/react';

import inoxToolsRequestNanostores from "@inox-tools/request-nanostores";

// https://astro.build/config
export default defineConfig({
  vite: {
    server: {
      watch: {
        usePolling: true
      }
    }
  },
  site: 'https://http://claraberendsen.github.io',
  base: '/air-quality-asuncion',
  output: 'static',
  srcDir: './src',
  integrations: [react(), tailwind(), inoxToolsRequestNanostores()]
});