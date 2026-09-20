import { useState } from 'react'
import {
  Activity,
  ArrowRight,
  Boxes,
  CheckCircle2,
  Clock3,
  PackageCheck,
  Radio,
  Truck,
} from 'lucide-react'
import {
  type ApiHealth,
  type ControlTowerOverview,
  type FulfillmentFilter,
  type InventoryFilter,
  type ProcurementFilter,
  type SseConnectionState,
} from './api'
import ExceptionInvestigationPage from './ExceptionInvestigationPage'

const nf = new Intl.NumberFormat('en-US')

function fmt(value: number | undefined) {
  return value === undefined ? '—' : nf.format(value)
}

function fmtDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value.length === 10 ? value + 'T00:00:00' : value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtTimestamp(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function cleanDetail(value: string) {
  return value.replaceAll('/', '/').replaceAll('/', '/')
}

function statusLabel(status: ControlTowerOverview['domains'][number]['status']) {
  if (status === 'exception') return 'Exception'
  if (status === 'attention') return 'Attention'
  if (status === 'monitoring') return 'Monitoring'
  return 'Healthy'
}

function statusClass(status: ControlTowerOverview['domains'][number]['status']) {
  if (status === 'exception') return 'critical'
  if (status === 'attention') return 'warning'
  if (status === 'monitoring') return 'monitoring'
  return 'success'
}

type Target = 'Fulfillment' | 'Delivery' | 'Inventory' | 'Procurement' | 'Cold Chain' | 'Platform Health'

type NavigateOptions = {
  fulfillmentFilter?: FulfillmentFilter
  deliveryFilter?: 'all' | 'pending' | 'confirmed' | 'receiver_not_present' | 'overdue' | 'due_today'
  inventoryFilter?: InventoryFilter
  procurementFilter?: ProcurementFilter
  coldChainSensorKey?: string | null
  recordId?: number | null
}

type Props = {
  overview: ControlTowerOverview | null
  apiHealth: ApiHealth | null
  sseState: SseConnectionState
  error: string | null
  onNavigate: (target: Target, options?: NavigateOptions) => void
}

function activityDestination(
  eventType: string,
  entityId: string | null,
): { target: Target | null; title: string; options?: NavigateOptions } {
  const id = entityId ? Number(entityId) : null
  if (eventType === 'order.changed') {
    return { target: 'Fulfillment', title: 'Order' + (id ? ' #' + id : '') + ' updated', options: { recordId: id } }
  }
  if (eventType === 'delivery.changed') {
    return { target: 'Delivery', title: 'Invoice' + (id ? ' #' + id : '') + ' updated', options: { recordId: id } }
  }
  if (eventType === 'inventory.changed') {
    return { target: 'Inventory', title: 'Stock item' + (id ? ' #' + id : '') + ' updated', options: { recordId: id } }
  }
  if (eventType === 'procurement.changed') {
    return { target: 'Procurement', title: 'Purchase order' + (id ? ' #' + id : '') + ' updated', options: { recordId: id } }
  }
  if (eventType.startsWith('telemetry.')) {
    return {
      target: 'Cold Chain',
      title: 'Cold-chain telemetry refreshed',
      options: entityId ? { coldChainSensorKey: entityId } : undefined,
    }
  }
  return { target: null, title: eventType }
}

export default function ControlTowerPage({ overview, apiHealth, sseState, error, onNavigate }: Props) {
  const [alertCenterOpen, setAlertCenterOpen] = useState(false)

  const platformHealthy =
    apiHealth?.status === 'ok' &&
    apiHealth?.database === 'ok' &&
    apiHealth?.sse_listener === 'connected' &&
    overview?.platform.watermark_aligned === true &&
    overview?.platform.freshness.all_fresh === true &&
    overview?.platform.quality?.status === 'pass'

  const sseLabel =
    sseState === 'connected'
      ? 'Realtime connected'
      : sseState === 'reconnecting'
        ? 'Realtime reconnecting'
        : sseState === 'disconnected'
          ? 'Realtime disconnected'
          : 'Realtime connecting'

  const openAlertCenter = () => setAlertCenterOpen(true)

  const openDomain = (domain: ControlTowerOverview['domains'][number]) => {
    if (domain.target === 'Fulfillment') {
      onNavigate('Fulfillment', { fulfillmentFilter: 'overdue' })
      return
    }
    if (domain.target === 'Delivery') {
      onNavigate('Delivery', { deliveryFilter: overview && overview.kpis.delivery_overdue > 0 ? 'overdue' : 'pending' })
      return
    }
    if (domain.target === 'Inventory') {
      onNavigate('Inventory', { inventoryFilter: 'risk' })
      return
    }
    if (domain.target === 'Procurement') {
      onNavigate('Procurement', { procurementFilter: 'open' })
      return
    }
    onNavigate(domain.target)
  }

  const attentionCards = [
    {
      label: 'Fulfillment overdue',
      value: overview?.kpis.fulfillment_overdue,
      note: overview
        ? overview.workload.fulfillment_due_today + ' due today / investigate overdue orders'
        : 'Investigate overdue orders',
      icon: PackageCheck,
      tone: 'warning',
      action: () => onNavigate('Fulfillment', { fulfillmentFilter: 'overdue' }),
    },
    {
      label: 'Delivery overdue',
      value: overview?.kpis.delivery_overdue,
      note: overview
        ? overview.kpis.delivery_pending + ' awaiting confirmation / ' + overview.workload.delivery_due_today + ' due today'
        : 'Investigate overdue deliveries',
      icon: Truck,
      tone: 'critical',
      action: () => onNavigate('Delivery', { deliveryFilter: 'overdue' }),
    },
    {
      label: 'Inventory supply risk',
      value: overview?.kpis.inventory_watch,
      note: 'Projected coverage risk / trace affected orders and inbound supply',
      icon: Boxes,
      tone: 'accent',
      action: () => onNavigate('Inventory', { inventoryFilter: 'risk' }),
    },
  ]

  if ((overview?.workload.procurement_supply_risk_pos ?? 0) > 0) {
    attentionCards.push({
      label: 'Procurement supply risk',
      value: overview?.workload.procurement_supply_risk_pos,
      note: overview
        ? overview.workload.procurement_open + ' open PO / supports inventory with current coverage exposure'
        : 'Open inbound commitments linked to inventory coverage risk',
      icon: PackageCheck,
      tone: 'warning',
      action: () => onNavigate('Procurement', { procurementFilter: 'open' }),
    })
  }

  if (alertCenterOpen) {
    return (
      <ExceptionInvestigationPage
        affectedRecords={overview?.alert_summary.affected_records ?? 0}
        alertSignals={overview?.alert_summary.active ?? 0}
        critical={overview?.alert_summary.critical ?? 0}
        warning={overview?.alert_summary.warning ?? 0}
        info={overview?.alert_summary.info ?? 0}
        onBack={() => setAlertCenterOpen(false)}
        onNavigate={onNavigate}
      />
    )
  }

  return (
    <div className="overview-page control-tower-page ct-v2">
      <section className="overview-heading ct-heading">
        <div>
          <div className="overview-title-row">
            <h2>Operational command center</h2>
            <span className={'preview-pill sse-pill ' + sseState}>Live REST + SSE</span>
          </div>
          <p>Prioritized operational exposure with supporting context and direct investigation paths.</p>
        </div>
        <div className="overview-meta">
          <span><span className={'live-dot ' + (sseState === 'reconnecting' ? 'live-dot-warning' : '')} /> {sseLabel}</span>
          <span>Refreshed {fmtTimestamp(overview?.generated_at)}</span>
        </div>
      </section>

      {error && <div className="overview-error">Serving error: {error}</div>}

      <section className="control-status-strip ct-status-strip" aria-label="Data freshness and platform status">
        <div className="status-strip-item">
          <Clock3 size={17} />
          <span>Operational data through</span>
          <strong>{fmtDate(overview?.as_of_date)}</strong>
        </div>
        <div className="status-strip-item">
          <Radio size={17} />
          <span>Realtime channel</span>
          <strong>{sseState === 'connected' ? 'Connected' : sseState}</strong>
        </div>
        <div className="status-strip-item">
          <CheckCircle2 size={17} />
          <span>Quality gate</span>
          <strong>{overview?.platform.quality?.status?.toUpperCase() ?? '—'}</strong>
        </div>
        <button className="status-strip-item status-strip-action" onClick={() => onNavigate('Platform Health')}>
          <Activity size={17} />
          <span>Watermark</span>
          <strong>{overview?.platform.watermark_aligned ? 'Aligned' : overview ? 'Mismatch' : '—'}</strong>
          <ArrowRight size={15} />
        </button>
      </section>

      <section className="ct-attention-section">
        <div className="section-heading-inline ct-section-heading">
          <div>
            <span className="panel-kicker">Triage</span>
            <h3>Needs attention now</h3>
          </div>
          <small>Only actionable exposure is shown here.</small>
        </div>

        <div className="attention-kpi-grid ct-attention-grid" aria-label="Current actionable attention summary">
          {attentionCards.map(({ label, value, note, icon: Icon, tone, action }) => (
            <article
              className="kpi-card clickable-kpi ct-attention-card"
              key={label}
              onClick={action}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') action()
              }}
              role="button"
              tabIndex={0}
            >
              <div className={'kpi-icon tone-' + tone}><Icon size={22} strokeWidth={1.9} /></div>
              <div className="kpi-copy">
                <span>{label}</span>
                <strong>{fmt(value)}</strong>
                <small>{note}</small>
              </div>
              <ArrowRight className="ct-card-arrow" size={18} />
            </article>
          ))}
        </div>
      </section>

      <section className="ct-workbench-grid">
        <div className="ct-main-column">
          <article className="panel-card domain-card ct-domain-card">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">Cross-domain operating state</span>
                <h3>Domain status</h3>
              </div>
              <span className="panel-muted">Open a domain to investigate</span>
            </div>

            <div className="domain-list">
              {(overview?.domains ?? []).map((domain) => (
                <button
                  className="domain-row domain-row-action ct-domain-row"
                  key={domain.name}
                  onClick={() => openDomain(domain)}
                >
                  <div>
                    <strong>{domain.name}</strong>
                    <small>{cleanDetail(domain.headline)} / {cleanDetail(domain.detail)}</small>
                  </div>
                  <span className={'status-chip ' + statusClass(domain.status)}>{statusLabel(domain.status)}</span>
                  <ArrowRight size={17} className="domain-row-arrow" />
                </button>
              ))}
            </div>
          </article>

          <article className="panel-card activity-card ct-activity-card">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">Operational activity</span>
                <h3>Latest meaningful changes</h3>
              </div>
              <span className="panel-muted">Business-source events only</span>
            </div>

            <div className="alert-list ct-activity-list">
              {(overview?.latest_activity ?? []).slice(0, 4).map((activity, index) => {
                const destination = activityDestination(activity.event_type, activity.entity_id)
                return (
                  <button
                    className="alert-row activity-row-action ct-activity-row"
                    key={activity.event_type + activity.occurred_at_utc + index}
                    onClick={() => destination.target && onNavigate(destination.target, destination.options)}
                  >
                    <span className="activity-marker" />
                    <div className="alert-copy">
                      <strong>{destination.title}</strong>
                      <small>{destination.target ?? 'Control Tower'} / {activity.operation.toLowerCase()} / {activity.source_table}</small>
                    </div>
                    <span className="alert-time">{fmtTimestamp(activity.occurred_at_utc)}</span>
                    <ArrowRight size={15} className="ct-row-arrow" />
                  </button>
                )
              })}
              {overview && overview.latest_activity.length === 0 && (
                <div className="panel-empty">No recent business-source activity is available.</div>
              )}
            </div>
          </article>
        </div>

        <aside className="ct-side-column">
          <article className="panel-card compact-exception-card ct-exception-card">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">Exception engine</span>
                <h3>Active exceptions</h3>
              </div>
              <span className={'status-chip ' + ((overview?.alert_summary.active ?? 0) > 0 ? 'critical' : 'success')}>
                {(overview?.alert_summary.active ?? 0) > 0 ? 'Action required' : 'Clear'}
              </span>
            </div>

            <div className="ct-exception-state">
              <strong>{fmt(overview?.alert_summary.affected_records)}</strong>
              <span>{(overview?.alert_summary.active ?? 0) === 0 ? 'No active exceptions' : 'affected records'}</span>
            </div>
            {(overview?.alert_summary.active ?? 0) > 0 && (
              <div className="ct-exception-signal-note">{fmt(overview?.alert_summary.active)} active alert signals</div>
            )}

            <div className="exception-breakdown compact-breakdown ct-exception-breakdown">
              <div><span className="severity-dot critical" /><b>Critical</b><strong>{fmt(overview?.alert_summary.critical)}</strong></div>
              <div><span className="severity-dot warning" /><b>Warning</b><strong>{fmt(overview?.alert_summary.warning)}</strong></div>
              <div><span className="severity-dot info" /><b>Info</b><strong>{fmt(overview?.alert_summary.info)}</strong></div>
            </div>

            <button className="panel-action ct-wide-action" onClick={() => openAlertCenter()}>
              Investigate exceptions <ArrowRight size={15} />
            </button>
          </article>

          <article className="panel-card platform-card ct-platform-card">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">Platform context</span>
                <h3>Serving health</h3>
              </div>
              <span className={'status-chip ' + (platformHealthy ? 'success' : 'warning')}>
                {platformHealthy ? 'Healthy' : 'Check'}
              </span>
            </div>

            <div className="platform-health-list ct-platform-list">
              <div><span>Realtime API</span><strong>{apiHealth?.status === 'ok' ? 'Connected' : '—'}</strong></div>
              <div><span>Database</span><strong>{apiHealth?.database ?? '—'}</strong></div>
              <div><span>SSE listener</span><strong>{apiHealth?.sse_listener ?? '—'}</strong></div>
              <div><span>Data freshness</span><strong>{overview?.platform.freshness.all_fresh ? 'Fresh' : overview ? 'Check' : '—'}</strong></div>
            </div>

            <button className="panel-action ct-wide-action" onClick={() => onNavigate('Platform Health')}>
              Open Platform Health <ArrowRight size={15} />
            </button>
          </article>
        </aside>
      </section>

    </div>
  )
}

