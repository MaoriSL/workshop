import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// Configuration Vite de la console d'attaque.
//
// Choix de `base: './'` : la console est servie par SON PROPRE nginx, à la
// racine de son origine (pas de préfixe). Les assets sont donc référencés en
// relatif, ce qui rend le conteneur déplaçable sans rebuild. L'intégrateur
// peut publier ce conteneur où il veut (gateway, sous-domaine…).
//
// L'orchestrateur est appelé en MÊME ORIGINE sous `VITE_API_BASE` (défaut
// `/api`). En développement il tourne sur http://localhost:8099 : le proxy
// ci-dessous transmet `/api` (y compris le flux SSE `/api/events`) vers lui,
// ce qui évite tout problème de CORS. En mode mock (VITE_USE_MOCK=true) aucun
// réseau n'est sollicité, le proxy est donc sans effet.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  server: {
    port: 5175,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8099',
        changeOrigin: true,
      },
    },
  },
  preview: { port: 4175 },
})
