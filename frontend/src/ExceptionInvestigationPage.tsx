import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Boxes,
  ChevronLeft,
  ChevronRight,
  Clock3,
  PackageCheck,
  Search,
  Truck,
  X,
} from 'lucide-react'
import {
  fetchExceptionCaseDetail,
  fetchExceptionCases,
  type ExceptionCaseDetail,
  type ExceptionCaseItem,
  type FulfillmentFilter,
  type InventoryFilter,
  type ProcurementFilter,
} from './api'

const nf = new Intl.NumberFormat('en-US')

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
  affectedRecords: number
  alertSignals: number
  critical: number
  warning: number
  info: number
  onBack: () => void
  onNavigate: (target: Target, options?: NavigateOptions) => void
}

function fmtTime(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function humanizeRule(ruleId: string) {
  return ruleId
    .split('.')
    .slice(1)
    .join(' ')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function entityLabel(entityType: string, entityId: string) {
  if (entityType === 'invoice') return `Invoice #${entityId}`
  if (entityType === 'order') return `Order #${entityId}`
  if (entityType === 'stock_item') return `Stock item #${entityId}`
  if (entityType === 'purchase_order') return `Purchase order #${entityId}`
  return `${entityType.replace(/_/g, ' ')} #${entityId}`
}

function domainLabel(domain: string) {
  if (domain === 'cold_chain') return 'Cold Chain'
  return domain.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function domainIcon(domain: string) {
  if (domain === 'delivery') return Truck
  if (domain === 'inventory') return Boxes
  return PackageCheck
}

function openRecord(caseDetail: ExceptionCaseDetail, onNavigate: Props['onNavigate']) {
  if (caseDetail.domain === 'cold_chain' || caseDetail.entity_type === 'sensor') {
    onNavigate('Cold Chain', { coldChainSensorKey: caseDetail.entity_id })
    return
  }

  const id = Number(caseDetail.entity_id)
  if (!Number.isFinite(id)) return

  if (caseDetail.entity_type === 'invoice') {
    onNavigate('Delivery', { recordId: id })
    return
  }
  if (caseDetail.entity_type === 'order') {
    onNavigate('Fulfillment', { recordId: id })
    return
  }
  if (caseDetail.entity_type === 'stock_item') {
    onNavigate('Inventory', { recordId: id })
    return
  }
  if (caseDetail.entity_type === 'purchase_order') {
    onNavigate('Procurement', { recordId: id })
  }
}

export default function ExceptionInvestigationPage({
  affectedRecords,
  alertSignals,
  critical,
  warning,
  info,
  onBack,
  onNavigate,
}: Props) {
  const [page, setPage] = useState(1)
  const [domain, setDomain] = useState('all')
  const [severity, setSeverity] = useState('all')
  const [status, setStatus] = useState('active')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [items, setItems] = useState<ExceptionCaseItem[]>([])
  const [total, setTotal] = useState(affectedRecords)
  const [totalPages, setTotalPages] = useState(Math.max(1, Math.ceil(affectedRecords / 50)))
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [selected, setSelected] = useState<ExceptionCaseDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setListError(null)

    fetchExceptionCases({ page, pageSize: 50, domain, severity, status, search })
      .then((response) => {
        if (!active) return
        setItems(response.items)
        setTotal(response.total)
        setTotalPages(response.total_pages)
        setSelected((current) => {
          if (!current) return null
          const stillVisible = response.items.some(
            (item) =>
              item.entity_type === current.entity_type &&
              item.entity_id === current.entity_id,
          )
          return stillVisible ? current : null
        })
      })
      .catch((error) => {
        if (!active) return
        setListError(error instanceof Error ? error.message : 'Unable to load exception cases.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [page, domain, severity, status, search, alertSignals])

  const firstRecord = total === 0 ? 0 : (page - 1) * 50 + 1
  const lastRecord = Math.min(page * 50, total)

  const pageNumbers = useMemo(() => {
    const start = Math.max(1, Math.min(page - 2, Math.max(1, totalPages - 4)))
    const end = Math.min(totalPages, start + 4)
    return Array.from({ length: Math.max(0, end - start + 1) }, (_, index) => start + index)
  }, [page, totalPages])

  const openCase = async (item: ExceptionCaseItem) => {
    setDetailLoading(true)
    setSelected(null)
    try {
      const response = await fetchExceptionCaseDetail(item.entity_type, item.entity_id)
      setSelected(response.case)
    } finally {
      setDetailLoading(false)
    }
  }

  const explanationAlerts = selected?.alerts ?? []
  const whyItems = Array.from(new Set(
    explanationAlerts.map((alert) => alert.why_it_matters).filter((value): value is string => Boolean(value))
  ))
  const evidence = Array.from(
    new Map(
      explanationAlerts
        .flatMap((alert) => alert.business_evidence ?? [])
        .map((item) => [item.label + '::' + item.value, item] as const)
    ).values()
  )
  const sourceEventIds = Array.from(new Set(
    explanationAlerts.map((alert) => alert.source_event_id).filter((value): value is string => Boolean(value))
  ))

  return (
    <div className="exception-workspace">
      <header className="exception-workspace-header">
        <div className="exception-heading-copy">
          <div className="exception-breadcrumb-row">
            <button className="exception-back" onClick={onBack}>
              <ArrowLeft size={17} /> Back to Control Tower
            </button>
            <span className="exception-breadcrumb-separator">/</span>
            <span className="panel-kicker">Exception investigation</span>
          </div>
          <h2>Active exceptions</h2>
          <p>Investigate affected business records, grouped so one record is handled as one case.</p>
        </div>

        <div className="exception-summary-strip">
          <div><strong>{nf.format(affectedRecords)}</strong><span>Affected records</span></div>
          <div><strong>{nf.format(alertSignals)}</strong><span>Alert signals</span></div>
          <div><strong>{nf.format(critical)}</strong><span>Critical</span></div>
          <div><strong>{nf.format(warning)}</strong><span>Warning</span></div>
          <div><strong>{nf.format(info)}</strong><span>Info</span></div>
        </div>
      </header>

      <section className="exception-toolbar">
        <form
          className="exception-search"
          onSubmit={(event) => {
            event.preventDefault()
            setPage(1)
            setSearch(searchInput)
          }}
        >
          <Search size={17} />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search invoice, order, stock item, or rule"
          />
          <button type="submit">Search</button>
        </form>

        <label>
          <span>Domain</span>
          <select value={domain} onChange={(event) => { setDomain(event.target.value); setPage(1) }}>
            <option value="all">All domains</option>
            <option value="fulfillment">Fulfillment</option>
            <option value="delivery">Delivery</option>
            <option value="inventory">Inventory</option>
            <option value="procurement">Procurement</option>
            <option value="cold_chain">Cold Chain</option>
          </select>
        </label>

        <label>
          <span>Severity</span>
          <select value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1) }}>
            <option value="all">All severities</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
        </label>

        <label>
          <span>Status</span>
          <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}>
            <option value="active">Open + acknowledged</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
          </select>
        </label>
      </section>

      <section className="exception-table-card">
        <div className="exception-table-head">
          <div>
            <strong>{nf.format(total)} affected records</strong>
            <span>{firstRecord}-{lastRecord} shown on this page</span>
          </div>
          <span>Grouped by business record</span>
        </div>

        {loading && <div className="exception-empty">Loading exception cases...</div>}
        {listError && <div className="exception-empty error">{listError}</div>}
        {!loading && !listError && items.length === 0 && (
          <div className="exception-empty">No exception cases match the current filters.</div>
        )}

        {!loading && !listError && items.length > 0 && (
          <div className="exception-case-list">
            {items.map((item) => {
              const Icon = domainIcon(item.domain)
              return (
                <button
                  className="exception-case-row"
                  key={item.domain + ':' + item.entity_type + ':' + item.entity_id}
                  onClick={() => void openCase(item)}
                >
                  <div className={'exception-case-icon tone-' + (item.severity === 'critical' ? 'critical' : item.severity === 'warning' ? 'warning' : 'accent')}>
                    <Icon size={18} />
                  </div>

                  <div className="exception-case-main">
                    <strong>{entityLabel(item.entity_type, item.entity_id)}</strong>
                    <span>{domainLabel(item.domain)} / {item.signal_count} active signal{item.signal_count === 1 ? '' : 's'}</span>
                  </div>

                  <div className="exception-case-reasons">
                    {item.signals.slice(0, 2).map((signal) => (
                      <span key={signal.alert_id}>{humanizeRule(signal.rule_id)}</span>
                    ))}
                    {item.signal_count > 2 && <small>+{item.signal_count - 2} more</small>}
                  </div>

                  <span className={'status-chip ' + (item.severity === 'critical' ? 'critical' : item.severity === 'warning' ? 'warning' : 'monitoring')}>
                    {item.severity}
                  </span>

                  <div className="exception-case-time">
                    <Clock3 size={14} />
                    <span>{fmtTime(item.last_observed_at)}</span>
                  </div>

                  <ArrowRight size={17} />
                </button>
              )
            })}
          </div>
        )}

        <footer className="exception-pagination">
          <span>Showing {firstRecord}-{lastRecord} of {nf.format(total)}</span>
          <div>
            <button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
              <ChevronLeft size={16} />
            </button>

            {pageNumbers.map((number) => (
              <button
                key={number}
                className={number === page ? 'active' : ''}
                onClick={() => setPage(number)}
              >
                {number}
              </button>
            ))}

            <button disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>
              <ChevronRight size={16} />
            </button>
          </div>
        </footer>
      </section>

      {(selected || detailLoading) && (
        <>
          <button
            className="exception-drawer-backdrop"
            aria-label="Close exception detail"
            onClick={() => setSelected(null)}
          />

          <aside className="exception-drawer" aria-label="Exception detail">
            <div className="exception-drawer-header">
              <div>
                <span className="panel-kicker">Operational case</span>
                <h3>{selected ? entityLabel(selected.entity_type, selected.entity_id) : 'Loading...'}</h3>
              </div>
              <button className="icon-button" onClick={() => setSelected(null)}>
                <X size={18} />
              </button>
            </div>

            {detailLoading && !selected && <div className="exception-empty">Loading case detail...</div>}

            {selected && (
              <div className="exception-drawer-body">
                <div className="exception-drawer-badges">
                  <span className={'status-chip ' + (selected.severity === 'critical' ? 'critical' : selected.severity === 'warning' ? 'warning' : 'monitoring')}>
                    {selected.severity}
                  </span>
                  <span className="status-chip monitoring">{selected.status}</span>
                  <span>{domainLabel(selected.domain)}</span>
                </div>

                <section className="exception-detail-section">
                  <span className="panel-kicker">Incident summary</span>
                  <div className="exception-explanation-list">
                    {explanationAlerts.map((alert) => (
                      <div key={alert.alert_id}>
                        <div className="exception-explanation-meta">
                          <strong>{humanizeRule(alert.rule_id)}</strong>
                          {!alert.evidence_verified && (
                            <span className="fallback">Evidence incomplete</span>
                          )}
                        </div>
                        <p className="exception-detail-lead">{alert.what_happened ?? alert.description}</p>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="exception-detail-section">
                  <span className="panel-kicker">Attention rationale</span>
                  <div className="exception-why-list">
                    {whyItems.map((item) => <p key={item}>{item}</p>)}
                  </div>
                </section>

                <section className="exception-detail-section">
                  <div className="exception-detail-section-head">
                    <span className="panel-kicker">Active signals</span>
                    <strong>{selected.signal_count}</strong>
                  </div>

                  <div className="exception-signal-list">
                    {selected.alerts.map((alert) => (
                      <div key={alert.alert_id}>
                        <AlertTriangle size={15} />
                        <div>
                          <strong>{humanizeRule(alert.rule_id)}</strong>
                          <span>{alert.description}</span>
                        </div>
                        <small>{fmtTime(alert.last_observed_at)}</small>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="exception-detail-section">
                  <span className="panel-kicker">Business evidence</span>
                  <dl className="exception-evidence-list">
                    {evidence.length > 0 ? evidence.map((item) => (
                      <div key={item.label + item.value}>
                        <dt>{item.label}</dt>
                        <dd>{item.value}</dd>
                      </div>
                    )) : (
                      <div>
                        <dt>Evidence</dt>
                        <dd>No normalized business evidence is available for this rule.</dd>
                      </div>
                    )}

                    <div><dt>Opened</dt><dd>{fmtTime(selected.opened_at)}</dd></div>
                    <div><dt>Last observed</dt><dd>{fmtTime(selected.last_observed_at)}</dd></div>
                    {sourceEventIds.map((eventId) => (
                      <div key={eventId}><dt>Source event</dt><dd className="mono">{eventId}</dd></div>
                    ))}
                  </dl>
                </section>

                <button className="exception-open-record" onClick={() => openRecord(selected, onNavigate)}>
                  Open {domainLabel(selected.domain)} record <ArrowRight size={16} />
                </button>

                <details className="exception-technical">
                  <summary>Technical evidence</summary>
                  <pre>{JSON.stringify({
                    alerts: selected.alerts.map((alert) => ({
                      alert_id: alert.alert_id,
                      rule_id: alert.rule_id,
                      observed_value: alert.observed_value,
                      threshold_value: alert.threshold_value,
                      source_event_id: alert.source_event_id,
                    })),
                  }, null, 2)}</pre>
                </details>
              </div>
            )}
          </aside>
        </>
      )}
    </div>
  )
}
