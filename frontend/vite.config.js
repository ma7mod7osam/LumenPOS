import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Build straight into the Frappe app's public folder with fixed filenames so
// lumenpos/www/pos.html can reference /assets/lumenpos/pos/pos.js and pos.css.
export default defineConfig({
  plugins: [vue()],
  base: '/assets/lumenpos/pos/',
  build: {
    outDir: '../lumenpos/public/pos',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'pos.js',
        chunkFileNames: 'chunk-[name].js',
        assetFileNames: (assetInfo) =>
          assetInfo.name && assetInfo.name.endsWith('.css') ? 'pos.css' : 'asset-[name][extname]',
      },
    },
  },
  server: {
    port: 8080,
    proxy: {
      '^/(api|assets|files)': {
        target: 'http://localhost:8000', // local bench during development
        changeOrigin: true,
      },
    },
  },
})
