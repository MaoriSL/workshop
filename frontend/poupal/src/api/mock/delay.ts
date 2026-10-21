/** Simule la latence réseau pour rendre les états de chargement visibles. */
export function wait(ms = 500): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
