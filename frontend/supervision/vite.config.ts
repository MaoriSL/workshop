import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// Configuration Vite du dashboard de supervision.
// `base` = '/supervision/' : l'application est servie par la gateway sous ce
// chemin (les assets sont donc référencés en /supervision/assets/...).
export default defineConfig({
  base: '/supervision/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  server: { port: 5174, host: true },
  preview: { port: 4174 },
})
