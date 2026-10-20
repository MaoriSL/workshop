import { useEffect } from 'react'

/** Met à jour le titre de l'onglet : usePageTitle('Tableau de bord') */
export function usePageTitle(title: string): void {
  useEffect(() => {
    const previous = document.title
    document.title = `${title} · Poupal`
    return () => {
      document.title = previous
    }
  }, [title])
}
