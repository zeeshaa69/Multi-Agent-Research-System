import { KINDS } from '../labels'
import type { StatementKind } from '../types'

export function KindBadge({ kind }: { kind: StatementKind }) {
  const info = KINDS[kind]
  return (
    <span className={`badge ${info.className}`} title={info.explain}>
      <span aria-hidden="true">{info.icon}</span> {info.label}
    </span>
  )
}

export function Confidence({ value }: { value: number | null }) {
  if (value === null) return <span className="muted small">not sourced</span>
  return (
    <span className="confidence" title={`Confidence ${value.toFixed(2)} (heuristic, see README)`}>
      <span className="bar">
        <span style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      <span className="small">{value.toFixed(2)}</span>
    </span>
  )
}

export function Legend() {
  return (
    <div className="legend" aria-label="Statement legend">
      {(Object.keys(KINDS) as StatementKind[]).map((k) => (
        <div key={k} className="legend-item">
          <KindBadge kind={k} />
          <span className="small muted">{KINDS[k].explain}</span>
        </div>
      ))}
    </div>
  )
}
