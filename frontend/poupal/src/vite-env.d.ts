/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL de base de l'API REST (vide = mode mock). */
  readonly VITE_API_URL?: string
  /** "true" pour forcer les données factices. */
  readonly VITE_USE_MOCK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
