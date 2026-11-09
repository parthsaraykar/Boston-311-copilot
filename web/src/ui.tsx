import { Fragment, type ReactNode } from 'react'
import { ArrowDownRight, ArrowUpRight, Info, Loader2, X } from 'lucide-react'

export function PageHeader({ title, description, actions, eyebrow }: { title: string; description?: ReactNode; actions?: ReactNode; eyebrow?: string }) {
  return (
    <div className="flex flex-wrap items-end gap-4 mb-6">
      <div className="mr-auto min-w-0">
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        <h1 className="h-page">{title}</h1>
        {description && <p className="t-2 mt-1 max-w-3xl">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Card({ title, description, actions, children, className = '', bodyClass = 'card-b', id }: {
  title?: ReactNode; description?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string; bodyClass?: string; id?: string
}) {
  return (
    <section className={`card ${className}`} aria-labelledby={id && title ? `${id}-h` : undefined}>
      {(title || actions) && (
        <div className="card-h">
          <div className="mr-auto min-w-0">
            {title && <h2 id={id ? `${id}-h` : undefined} className="h-card">{title}</h2>}
            {description && <p className="t-xs t-muted mt-0.5">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 flex-wrap justify-end">{actions}</div>}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, delta, deltaGood, foot, loading }: {
  label: string; value: ReactNode; delta?: string; deltaGood?: boolean; foot?: ReactNode; loading?: boolean
}) {
  return (
    <div className="card p-4">
      <div className="eyebrow">{label}</div>
      {loading ? <div className="skeleton h-8 w-28 mt-2" /> : (
        <div className="flex items-baseline gap-2 mt-1">
          <div className="num" style={{ fontSize: '1.65rem', fontWeight: 600, letterSpacing: '-0.02em' }}>{value}</div>
          {delta && (
            <span className={`badge ${deltaGood ? 'badge-good' : 'badge-danger'}`}>
              {deltaGood ? <ArrowDownRight size={12} /> : <ArrowUpRight size={12} />}{delta}
            </span>
          )}
        </div>
      )}
      {foot && <div className="t-xs t-muted mt-1">{foot}</div>}
    </div>
  )
}

export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; label: string
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  )
}

export function Slider({ label, value, min, max, step, onChange, format }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; format: (v: number) => string
}) {
  const id = 'sl-' + label.replace(/\W/g, '')
  const fill = `${((value - min) / (max - min)) * 100}%`
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label htmlFor={id} className="t-sm t-2">{label}</label>
        <span className="t-sm num font-medium">{format(value)}</span>
      </div>
      <input id={id} type="range" min={min} max={max} step={step} value={value} style={{ ['--fill' as any]: fill }}
        onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  )
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-3 cursor-pointer t-sm t-2">
      <span>{label}</span>
      <button type="button" role="switch" aria-checked={checked} className="switch" onClick={() => onChange(!checked)} />
    </label>
  )
}

export function DeptDot({ dept }: { dept: string }) {
  const v: Record<string, string> = { 'Public Works': '--s-pw', Transportation: '--s-bt', Parks: '--s-pk', 'Inspectional Services': '--s-is' }
  return <span aria-hidden style={{ width: 8, height: 8, borderRadius: 2, background: `var(${v[dept] || '--neutral'})`, display: 'inline-block', flex: 'none' }} />
}

export function Spinner({ label }: { label?: string }) {
  return <span className="inline-flex items-center gap-2 t-sm t-muted"><Loader2 size={15} className="animate-spin" />{label}</span>
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="text-center py-10 px-6">
      {icon && <div className="mx-auto mb-3 w-10 h-10 grid place-items-center rounded-lg inset t-muted">{icon}</div>}
      <div className="font-medium">{title}</div>
      {children && <div className="t-sm t-muted mt-1 max-w-sm mx-auto">{children}</div>}
    </div>
  )
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <div className="flex gap-2.5 p-3 rounded-lg t-sm t-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
      <Info size={16} className="flex-none mt-0.5 t-muted" /><div>{children}</div>
    </div>
  )
}

export function Drawer({ open, onClose, title, children, width = 520 }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: number }) {
  return (
    <div aria-hidden={!open} className="fixed inset-0 z-[1000]" style={{ pointerEvents: open ? 'auto' : 'none' }}>
      <div onClick={onClose} className="absolute inset-0 transition-opacity" style={{ background: 'rgba(9,9,11,.35)', opacity: open ? 1 : 0 }} />
      <aside role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'Panel'}
        className="absolute right-0 top-0 h-full flex flex-col transition-transform"
        style={{ width: `min(${width}px, 100vw)`, background: 'var(--surface)', borderLeft: '1px solid var(--border)', boxShadow: 'var(--shadow-md)',
          transform: open ? 'translateX(0)' : 'translateX(100%)' }}>
        <div className="flex items-center gap-2 px-4 h-14 border-b" style={{ borderColor: 'var(--border)' }}>
          <div className="h-card mr-auto">{title}</div>
          <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close panel"><X /></button>
        </div>
        <div className="flex-1 min-h-0 flex flex-col">{open && children}</div>
      </aside>
    </div>
  )
}

export function KV({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(110px,auto)_1fr] gap-x-4 gap-y-2 t-sm">
      {items.map(([k, v], i) => (<Fragment key={i}><dt className="t-muted">{k}</dt><dd className="min-w-0">{v}</dd></Fragment>))}
    </dl>
  )
}
