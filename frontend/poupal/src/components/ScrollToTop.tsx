import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/** Remonte en haut de page à chaque changement de route. */
export function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
  }, [pathname])
  return null
}
