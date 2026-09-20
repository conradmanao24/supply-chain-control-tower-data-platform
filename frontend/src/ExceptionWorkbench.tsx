import { ArrowRight, Link2, Route, ShieldAlert, Target } from 'lucide-react'
import type { ExceptionWorkbench as WorkbenchData } from './api'

type Domain = 'Fulfillment' | 'Delivery' | 'Inventory' | 'Procurement'

type Props = {
  data: WorkbenchData | null
  loading?: boolean
  onNavigate?: (domain: Domain, recordId: number) => void
}

const nf = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

function fmtValue(value: string | number | boolean | null) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'number') return nf.format(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (/^\d{4}-\d{2}-\d{2}(T|$)/.test(value)) {
    const date = new Date(value.length === 10 ? value + 'T00:00:00' : value)
    if (!Number.isNaN(date.getTime())) {
      return value.length === 10
        ? date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
        : date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    }
  }
  return value
}

function severityTone(severity: string) {
  if (severity === 'critical') return 'critical'
  if (severity === 'warning') return 'warning'
  if (severity === 'monitoring') return 'monitoring'
  return 'success'
}

export default function ExceptionWorkbench({ data, loading = false, onNavigate }: Props) {
  if (loading && !data) {
    return <div className="workbench-loading">Building cross-domain evidence...</div>
  }
  if (!data) return null

  return (
    <section className="exception-workbench">
      <div className={'workbench-issue ' + severityTone(data.issue.severity)}>
        <div className="workbench-issue-icon"><ShieldAlert size={18} /></div>
        <div>
          <span className="panel-kicker">Exception workbench</span>
          <h4>{data.issue.title}</h4>
          <p>{data.issue.summary}</p>
        </div>
        <span className={'status-chip ' + severityTone(data.issue.severity)}>
          {data.issue.severity}
        </span>
      </div>

      <div className="workbench-grid">
        <section className="workbench-block">
          <div className="workbench-block-heading">
            <Target size={15} />
            <div>
              <span className="panel-kicker">Business impact</span>
              <h5>Exposure summary</h5>
            </div>
          </div>
          <div className="workbench-metric-grid">
            {data.impact.map((item) => (
              <div className="workbench-metric" key={item.label}>
                <span>{item.label}</span>
                <strong>{fmtValue(item.value)}</strong>
                {item.detail && <small>{item.detail}</small>}
              </div>
            ))}
          </div>
        </section>

        <section className="workbench-block">
          <div className="workbench-block-heading">
            <ShieldAlert size={15} />
            <div>
              <span className="panel-kicker">Derived cause</span>
              <h5>{data.cause.title}</h5>
            </div>
          </div>
          <p className="workbench-copy">{data.cause.explanation}</p>
          <small className="workbench-basis">{data.cause.basis}</small>
        </section>
      </div>

      <section className="workbench-block">
        <div className="workbench-block-heading">
          <Route size={15} />
          <div>
            <span className="panel-kicker">Evidence</span>
            <h5>Evidence basis</h5>
          </div>
        </div>
        <div className="workbench-evidence-grid">
          {data.evidence.map((item) => (
            <div className="workbench-evidence" key={item.label}>
              <span>{item.label}</span>
              <strong>{fmtValue(item.value)}</strong>
              {item.detail && <small>{item.detail}</small>}
            </div>
          ))}
        </div>
      </section>

      {data.related_records.length > 0 && (
        <section className="workbench-block">
          <div className="workbench-block-heading">
            <Link2 size={15} />
            <div>
              <span className="panel-kicker">Cross-domain trace</span>
              <h5>Related operational records</h5>
            </div>
          </div>
          <div className="workbench-related-list">
            {data.related_records.map((item, index) => {
              const target = item.domain as Domain
              const id = Number(item.entity_id)
              const clickable =
                onNavigate &&
                Number.isFinite(id) &&
                ['Fulfillment', 'Delivery', 'Inventory', 'Procurement'].includes(target)
              return (
                <button
                  key={item.domain + ':' + item.entity_type + ':' + item.entity_id + ':' + index}
                  className="workbench-related-row"
                  disabled={!clickable}
                  onClick={() => clickable && onNavigate(target, id)}
                >
                  <div>
                    <span className="workbench-domain">{item.domain}</span>
                    <strong>{item.label}</strong>
                    <small>{item.relationship}{item.detail ? ' / ' + item.detail : ''}</small>
                  </div>
                  <div className="workbench-related-action">
                    {item.status && <span className="status-chip monitoring">{item.status}</span>}
                    {clickable && <ArrowRight size={15} />}
                  </div>
                </button>
              )
            })}
          </div>
        </section>
      )}

      {data.timeline.length > 0 && (
        <section className="workbench-block">
          <div className="workbench-block-heading">
            <Route size={15} />
            <div>
              <span className="panel-kicker">Timeline</span>
              <h5>Observed and planned milestones</h5>
            </div>
          </div>
          <div className="workbench-timeline">
            {data.timeline.map((item, index) => (
              <div className={'workbench-timeline-row ' + item.state} key={item.label + ':' + index}>
                <span className="workbench-timeline-dot" />
                <div>
                  <strong>{item.label}</strong>
                  <span>{fmtValue(item.timestamp)}</span>
                  {item.detail && <small>{item.detail}</small>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </section>
  )
}
