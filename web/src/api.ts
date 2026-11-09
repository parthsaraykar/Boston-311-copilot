export const API = import.meta.env.VITE_API ?? (import.meta.env.DEV ? '/api' : '')

export async function get<T = any>(path: string): Promise<T> {
  const r = await fetch(API + path)
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json()
}

export async function post<T = any>(path: string, body: unknown = {}): Promise<T> {
  const r = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`)
  return r.json()
}

export const DEPTS = ['Public Works', 'Transportation', 'Parks', 'Inspectional Services'] as const
export const DEPT_VAR: Record<string, string> = {
  'Public Works': '--s-pw', Transportation: '--s-bt', Parks: '--s-pk', 'Inspectional Services': '--s-is',
}
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export const money = (x: number | null | undefined, digits = 0) =>
  x == null ? '–' : '$' + x.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })
export const moneyM = (x: number | null | undefined) => (x == null ? '–' : `$${(x / 1e6).toFixed(2)}M`)
export const pct = (x: number | null | undefined, d = 1) => (x == null ? '–' : `${(x * 100).toFixed(d)}%`)
export const num = (x: number | null | undefined) => (x == null ? '–' : Math.round(x).toLocaleString('en-US'))

export const SHORT: Record<string, string> = { 'Public Works': 'Public Works', Transportation: 'Transportation', Parks: 'Parks', 'Inspectional Services': 'Inspections' }
