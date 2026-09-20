import { ArrowRight, GitBranch, Link2 } from 'lucide-react'
import type { WorkbenchTrace } from './api'

export type WorkbenchDomain =
  | 'Fulfillment'
  | 'Delivery'
  | 'Inventory'
  | 'Procurement'

type Props = {
  trace: WorkbenchTrace | null
  loading?: boolean
  onNavigate?: (domain: WorkbenchDomain, recordId: number) => void
}

const nf = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return nf.format(value)
  const raw=String(value)
  const date=new Date(raw.length===10 ? raw+'T00:00:00' : raw)
  if (
    !Number.isNaN(date.getTime()) &&
    /^\d{4}-\d{2}-\d{2}/.test(raw)
  ) {
    return raw.length===10
      ? date.toLocaleDateString([], { month:'short', day:'numeric', year:'numeric' })
      : date.toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
  }
  return raw
}

function tone(severity:string) {
  if (severity==='critical') return 'critical'
  if (severity==='warning') return 'warning'
  if (severity==='healthy') return 'success'
  return 'monitoring'
}

export default function ExceptionWorkbenchSections({
  trace,
  loading=false,
  onNavigate,
}:Props) {
  if (loading && !trace) {
    return <div className="panel-empty">Loading exception analysis…</div>
  }
  if (!trace) return null

  return (
    <div className="exception-workbench">
      <section className="workbench-issue">
        <div className="workbench-section-head">
          <div>
            <span className="panel-kicker">Issue</span>
            <h4>{trace.issue.title}</h4>
          </div>
          <span className={'status-chip '+tone(trace.issue.severity)}>
            {trace.issue.severity}
          </span>
        </div>
        <p>{trace.issue.summary}</p>
      </section>

      <section className="workbench-section">
        <div className="workbench-section-head">
          <div>
            <span className="panel-kicker">Business impact</span>
            <h4>Current exposure</h4>
          </div>
        </div>
        <div className="workbench-metric-grid">
          {trace.impact.map((item) => (
            <div key={item.label}>
              <span>{item.label}</span>
              <strong>{displayValue(item.value)}</strong>
              {item.detail && <small>{item.detail}</small>}
            </div>
          ))}
        </div>
      </section>

      <section className="workbench-section">
        <div className="workbench-section-head">
          <div>
            <span className="panel-kicker">Evidence</span>
            <h4>Verified operational signals</h4>
          </div>
        </div>
        <dl className="workbench-evidence-list">
          {trace.evidence.map((item) => (
            <div key={item.label}>
              <dt>{item.label}</dt>
              <dd>
                <strong>{displayValue(item.value)}</strong>
                {item.detail && <small>{item.detail}</small>}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="workbench-section workbench-cause">
        <div className="workbench-section-head">
          <div>
            <span className="panel-kicker">Derived cause</span>
            <h4>{trace.cause.title}</h4>
          </div>
        </div>
        <p>{trace.cause.explanation}</p>
        <small>{trace.cause.basis}</small>
      </section>

      <section className="workbench-section">
        <div className="workbench-section-head">
          <div>
            <span className="panel-kicker">Related records</span>
            <h4>Cross-domain trace</h4>
          </div>
          <GitBranch size={15} />
        </div>

        <div className="workbench-related-list">
          {trace.related_records.map((item,index) => {
            const id=Number(item.entity_id)
            const clickable=Boolean(
              onNavigate &&
              Number.isFinite(id) &&
              ['Fulfillment','Delivery','Inventory','Procurement'].includes(item.domain),
            )
            return (
              <button
                type="button"
                key={item.domain+'-'+item.entity_type+'-'+item.entity_id+'-'+index}
                disabled={!clickable}
                className={'workbench-related-row '+(clickable ? 'clickable' : '')}
                onClick={() => {
                  if (clickable) onNavigate?.(item.domain as WorkbenchDomain,id)
                }}
              >
                <span className="workbench-related-icon"><Link2 size={13} /></span>
                <div>
                  <strong>{item.label}</strong>
                  <small>{item.relationship}{item.detail ? ' / '+item.detail : ''}</small>
                </div>
                {item.status && <span className="workbench-related-status">{item.status}</span>}
                {clickable && <ArrowRight size={14} />}
              </button>
            )
          })}
          {trace.related_records.length===0 && (
            <div className="panel-empty">No linked operational records for this exception.</div>
          )}
        </div>
      </section>

      <section className="workbench-section">
        <div className="workbench-section-head">
          <div>
            <span className="panel-kicker">Timeline</span>
            <h4>Operational lifecycle</h4>
          </div>
        </div>

        <div className="workbench-timeline">
          {trace.timeline.map((item,index) => (
            <div className={'workbench-timeline-row '+item.state} key={item.label+'-'+index}>
              <i />
              <div>
                <strong>{item.label}</strong>
                <span>{displayValue(item.timestamp)}</span>
                {item.detail && <small>{item.detail}</small>}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
