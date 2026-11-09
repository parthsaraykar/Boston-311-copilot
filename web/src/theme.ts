import { useEffect, useState } from 'react'

/** Resolve CSS color tokens for SVG charts and re-read them when the theme changes. */
export function useTokens(names: string[]): Record<string, string> {
  const read = () => {
    const cs = getComputedStyle(document.documentElement)
    return Object.fromEntries(names.map((n) => [n, cs.getPropertyValue(n).trim()]))
  }
  const [vals, setVals] = useState<Record<string, string>>(read)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setVals(read())
    mq.addEventListener('change', update)
    const obs = new MutationObserver(update)
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class'] })
    return () => { mq.removeEventListener('change', update); obs.disconnect() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return vals
}

export const CHART_TOKENS = ['--s-pw', '--s-bt', '--s-pk', '--s-is', '--grid', '--muted', '--text', '--text-2', '--band',
  '--accent', '--danger', '--neutral', '--surface', '--good']
