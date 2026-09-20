import { FormEvent, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  PackageCheck,
  Search,
  Truck,
} from 'lucide-react'
import {
  fetchProcurementDetail,
  fetchProcurementList,
  fetchProcurementOverview,
  fetchProcurementWorkbench,
  type ProcurementDetailResponse,
  type ProcurementFilter,
  type ProcurementListResponse,
  type ProcurementOverview,
  type ExceptionWorkbench as WorkbenchData,
  type SseConnectionState,
} from './api'
import RecordDetailDrawer from './RecordDetailDrawer'
import ExceptionWorkbench from './ExceptionWorkbench'

const nf = new Intl.NumberFormat('en-US')
const fmt = (value: number | undefined) => (value === undefined ? '-' : nf.format(value))

const fmtDate = (value: string | null | undefined) => {
  if (!value) return '-'
  const date = new Date(value.length === 10 ? value + 'T00:00:00' : value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

const fmtTs = (value: string | null | undefined) => {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '-'
    : date.toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
}

const stateLabel = (state: string, daysOverdue: number, daysUntilDue: number) => {
  if (state === 'overdue') return daysOverdue + 'd overdue'
  if (state === 'due_today') return 'Due today'
  if (state === 'awaiting_receipt') {
    return daysUntilDue > 0 ? daysUntilDue + 'd to due' : 'Awaiting receipt'
  }
  return 'Finalized'
}

const stateTone = (state: string) => {
  if (state === 'overdue') return 'critical'
  if (state === 'due_today') return 'warning'
  if (state === 'awaiting_receipt') return 'monitoring'
  return 'success'
}

const procurementPageCache: {
  overview: ProcurementOverview | null
  lists: Map<string, ProcurementListResponse>
} = {
  overview: null,
  lists: new Map(),
}

const procurementListKey = (
  filter: ProcurementFilter,
  page: number,
  search: string,
) => `${filter}|${page}|${search.trim().toLowerCase()}`

type Props = {
  sseState: SseConnectionState
  refreshSignal: number
  initialFilter?: ProcurementFilter
  initialRecordId?: number | null
  onNavigate?: (
    domain: 'Fulfillment' | 'Delivery' | 'Inventory' | 'Procurement',
    recordId: number,
  ) => void
}

const filters: Array<{ value: ProcurementFilter; label: string }> = [
  { value: 'open', label: 'Open' },
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'due_today', label: 'Due today' },
  { value: 'finalized', label: 'Finalized' },
  { value: 'all', label: 'All 30d' },
]

export default function ProcurementPage({
  sseState,
  refreshSignal,
  initialFilter = 'open',
  initialRecordId = null,
  onNavigate,
}: Props) {
  const initialListKey = procurementListKey(initialFilter, 1, '')
  const [data, setData] = useState<ProcurementOverview | null>(
    () => procurementPageCache.overview,
  )
  const [list, setList] = useState<ProcurementListResponse | null>(
    () => procurementPageCache.lists.get(initialListKey) ?? null,
  )
  const [filter, setFilter] = useState<ProcurementFilter>(initialFilter)
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [detail, setDetail] = useState<ProcurementDetailResponse | null>(null)
  const [workbench, setWorkbench] = useState<WorkbenchData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [listLoading, setListLoading] = useState(
    () => !procurementPageCache.lists.has(initialListKey),
  )
  const [detailLoading, setDetailLoading] = useState(false)
  const [workbenchLoading, setWorkbenchLoading] = useState(false)
  const requestSeq = useRef(0)
  const refreshSignalMounted = useRef(false)

  const load = async (
    showBusy = false,
    nextFilter = filter,
    nextPage = page,
    nextSearch = search,
  ) => {
    const requestId = ++requestSeq.current
    const key = procurementListKey(nextFilter, nextPage, nextSearch)
    const cachedRows = procurementPageCache.lists.get(key) ?? null

    if (procurementPageCache.overview) {
      setData(procurementPageCache.overview)
    }
    if (cachedRows) {
      setList(cachedRows)
      setListLoading(false)
    } else {
      setList(null)
      setListLoading(true)
    }
    if (showBusy) setRefreshing(true)

    try {
      const [overview, rows] = await Promise.all([
        fetchProcurementOverview(),
        fetchProcurementList(nextFilter, nextPage, 50, nextSearch),
      ])
      procurementPageCache.overview = overview
      procurementPageCache.lists.set(key, rows)
      if (requestId !== requestSeq.current) return
      setData(overview)
      setList(rows)
      setError(null)
    } catch (err) {
      if (requestId !== requestSeq.current) return
      setError(err instanceof Error ? err.message : 'Unable to load procurement data')
    } finally {
      if (requestId === requestSeq.current) {
        setListLoading(false)
        if (showBusy) setRefreshing(false)
      }
    }
  }

  const openDetail = async (id: number) => {
    setDetailLoading(true)
    setWorkbenchLoading(true)
    try {
      const [record, diagnostic] = await Promise.all([
        fetchProcurementDetail(id),
        fetchProcurementWorkbench(id),
      ])
      setDetail(record)
      setWorkbench(diagnostic)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load purchase-order detail')
    } finally {
      setDetailLoading(false)
      setWorkbenchLoading(false)
    }
  }

  const changeFilter = (nextFilter: ProcurementFilter) => {
    setFilter(nextFilter)
    setPage(1)
    setDetail(null)
    setWorkbench(null)
    void load(false, nextFilter, 1, search)
  }

  const changePage = (nextPage: number) => {
    setPage(nextPage)
    setDetail(null)
    setWorkbench(null)
    void load(false, filter, nextPage, search)
  }

  const submitSearch = (event: FormEvent) => {
    event.preventDefault()
    const nextSearch = searchInput.trim()
    setSearch(nextSearch)
    setPage(1)
    setDetail(null)
    setWorkbench(null)
    void load(false, filter, 1, nextSearch)
  }

  const clearSearch = () => {
    setSearchInput('')
    setSearch('')
    setPage(1)
    setDetail(null)
    setWorkbench(null)
    void load(false, filter, 1, '')
  }

  useEffect(() => {
    setFilter(initialFilter)
    setPage(1)
    setSearchInput('')
    setSearch('')
    setDetail(null)
    setWorkbench(null)
    void load(false, initialFilter, 1, '')
    if (initialRecordId) void openDetail(initialRecordId)
  }, [initialFilter, initialRecordId])

  useEffect(() => {
    if (!refreshSignalMounted.current) {
      refreshSignalMounted.current = true
      return
    }
    if (refreshSignal > 0) void load(false, filter, page, search)
  }, [refreshSignal])

  const selected = detail?.purchase_order
  const selectedLines = detail?.lines ?? []

  const listTitle =
    filter === 'open'
      ? 'Open purchase-order queue'
      : filter === 'upcoming'
        ? 'Upcoming open purchase orders'
        : filter === 'overdue'
          ? 'Overdue purchase-order queue'
          : filter === 'due_today'
            ? 'Due-today purchase-order queue'
            : filter === 'finalized'
              ? 'Finalized purchase orders'
              : 'All purchase orders'

  return (
    <div className="fulfillment-page fulfillment-v2 procurement-v2">
      <section className="overview-heading">
        <div>
          <div className="overview-title-row">
            <h2>Procurement control</h2>
            <span className={'preview-pill sse-pill ' + sseState}>Realtime channel</span>
          </div>
          <p>
            Prioritize inbound supply risk by supplier performance, due-date exposure,
            and the inventory and customer orders that depend on each purchase order.
          </p>
        </div>

        <div className="overview-meta">
          <span>
            <span className={'live-dot sse-' + sseState} />
            Realtime {sseState}
          </span>
          <span>Operational data through {fmtDate(data?.as_of_date)}</span>
        </div>
      </section>

      {error && <div className="overview-error">Procurement serving error: {error}</div>}

      <section className="kpi-grid fulfillment-kpi-grid">
        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('all')}>
          <div className="kpi-icon tone-cool"><ClipboardList size={20} /></div>
          <div className="kpi-copy">
            <span>Purchase orders 30d</span>
            <strong>{fmt(data?.kpis.po_30d)}</strong>
            <small>All POs in current operational window</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('open')}>
          <div className="kpi-icon tone-warning"><PackageCheck size={20} /></div>
          <div className="kpi-copy">
            <span>Open POs</span>
            <strong>{fmt(data?.kpis.open_po)}</strong>
            <small>Not finalized / awaiting receipt</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('overdue')}>
          <div className="kpi-icon tone-critical"><AlertTriangle size={20} /></div>
          <div className="kpi-copy">
            <span>Overdue</span>
            <strong>{fmt(data?.kpis.overdue)}</strong>
            <small>Open POs past expected delivery date</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('due_today')}>
          <div className="kpi-icon tone-accent"><CalendarClock size={20} /></div>
          <div className="kpi-copy">
            <span>Due today</span>
            <strong>{fmt(data?.kpis.due_today)}</strong>
            <small>Open POs due on {fmtDate(data?.as_of_date)}</small>
          </div>
        </article>
      </section>

      <section className="fulfillment-mid-grid">
        <article className="panel-card aging-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Open commitments</span>
              <h3>Outstanding supplier receipts</h3>
            </div>
            <span className={'status-chip ' + ((data?.kpis.overdue ?? 0) > 0 ? 'critical' : 'monitoring')}>
              {(data?.kpis.overdue ?? 0) > 0 ? fmt(data?.kpis.overdue) + ' overdue' : 'On schedule'}
            </span>
          </div>

          <div className="fulfillment-context-grid procurement-commitment-grid">
            <div>
              <span>Outstanding outers</span>
              <strong>{fmt(data?.operational_context.outstanding_open_outers)}</strong>
            </div>
            <div>
              <span>Outstanding lines</span>
              <strong>{fmt(data?.operational_context.outstanding_open_lines)}</strong>
            </div>
            <div>
              <span>Nearest open PO due</span>
              <strong>{fmtDate(data?.operational_context.nearest_open_due)}</strong>
            </div>
            <div>
              <span>Days to nearest due</span>
              <strong>
                {data?.operational_context.days_to_nearest_due == null
                  ? '-'
                  : data.operational_context.days_to_nearest_due + ' days'}
              </strong>
            </div>
          </div>

          <p className="fulfillment-context-note">
            Open commitment means the PO is not finalized. A future-due PO with zero receipts
            is awaiting receipt, not automatically an under-received exception.
          </p>
        </article>

        <article className="panel-card fulfillment-context-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">30-day receipt context</span>
              <h3>Receipt completion and supplier exposure</h3>
            </div>
            <span className="status-chip success">
              {data?.operational_context.receipt_rate_pct ?? 0}% received
            </span>
          </div>

          <div className="fulfillment-context-grid">
            <button className="context-stat-action" onClick={() => changeFilter('finalized')}>
              <span>Finalized POs</span>
              <strong>{fmt(data?.operational_context.finalized_po)}</strong>
            </button>
            <button className="context-stat-action" onClick={() => changeFilter('upcoming')}>
              <span>Upcoming open POs</span>
              <strong>{fmt(data?.operational_context.upcoming_open)}</strong>
            </button>
            <div>
              <span>Ordered outers</span>
              <strong>{fmt(data?.operational_context.ordered_outers)}</strong>
            </div>
            <div>
              <span>Received outers</span>
              <strong>{fmt(data?.operational_context.received_outers)}</strong>
            </div>
          </div>

          <div className="procurement-supplier-strip">
            {(data?.open_suppliers ?? []).map((supplier) => (
              <button
                key={supplier.supplier_id}
                className="procurement-supplier-row"
                onClick={() => {
                  setSearchInput(supplier.supplier_name ?? String(supplier.supplier_id))
                  setSearch(supplier.supplier_name ?? String(supplier.supplier_id))
                  setFilter('open')
                  setPage(1)
                  setDetail(null)
                  void load(
                    false,
                    'open',
                    1,
                    supplier.supplier_name ?? String(supplier.supplier_id),
                  )
                }}
              >
                <div>
                  <strong>{supplier.supplier_name ?? 'Supplier ' + supplier.supplier_id}</strong>
                  <small>
                    {fmt(supplier.open_po_count)} open PO / due {fmtDate(supplier.nearest_due)}
                    {' / OTIF '}
                    {supplier.otif_pct == null ? '-' : supplier.otif_pct + '%'}
                  </small>
                </div>
                <span>
                  {supplier.at_risk_sku_count > 0
                    ? fmt(supplier.at_risk_sku_count) + ' at-risk SKU / ' +
                      fmt(supplier.affected_order_links) + ' order links'
                    : 'No active inbound risk'}
                </span>
              </button>
            ))}
            {(data?.open_suppliers.length ?? 0) === 0 && (
              <div className="panel-empty healthy-empty">No open supplier commitments.</div>
            )}
          </div>
        </article>
      </section>

      <section className="panel-card fulfillment-table-card">
        <div className="panel-header fulfillment-queue-header">
          <div>
            <span className="panel-kicker">Operational purchase-order queue</span>
            <h3>{listTitle} / {fmt(list?.count)}</h3>
            <p className="procurement-queue-description">
              One row represents one purchase order. Downstream risk is shown only for
              open receipt commitments that supply inventory with current coverage exposure.
            </p>
          </div>

          <button
            className="panel-action"
            onClick={() => void load(true, filter, page, search)}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        <div className="fulfillment-queue-tools">
          <form className="fulfillment-search" onSubmit={submitSearch}>
            <Search size={16} />
            <input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search PO ID or supplier"
              aria-label="Search procurement records"
            />
            {search && <button type="button" onClick={clearSearch}>Clear</button>}
            <button type="submit">Search</button>
          </form>

          <div className="fulfillment-filter-row">
            {filters.map((item) => (
              <button
                key={item.value}
                className={'panel-action ' + (filter === item.value ? 'active' : '')}
                onClick={() => changeFilter(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div
          className={
            'fulfillment-table-wrap ' +
            (!listLoading && list && list.items.length === 0
              ? 'procurement-empty-wrap'
              : list && list.items.length <= 6
                ? 'procurement-compact-wrap'
                : '')
          }
        >
          <table className="fulfillment-table procurement-work-table">
            <thead>
              <tr>
                <th>PO</th>
                <th>Supplier</th>
                <th>Expected</th>
                <th>Operational state</th>
                <th>Receipt progress</th>
                <th>Supplier OTIF</th>
                <th>Downstream risk</th>
              </tr>
            </thead>
            <tbody>
              {(list?.items ?? []).map((po) => (
                <tr
                  key={po.purchase_order_id}
                  onClick={() => void openDetail(po.purchase_order_id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td className="mono-cell">
                    #{po.purchase_order_id}
                    <small>Ordered {fmtDate(po.order_date)}</small>
                  </td>
                  <td>
                    <strong>{po.supplier_name ?? 'Supplier ' + po.supplier_id}</strong>
                    <small>Supplier {po.supplier_id}</small>
                  </td>
                  <td>{fmtDate(po.expected_delivery_date)}</td>
                  <td>
                    <span className={'status-chip ' + stateTone(po.procurement_state)}>
                      {stateLabel(po.procurement_state, po.days_overdue, po.days_until_due)}
                    </span>
                  </td>
                  <td>
                    <strong>{fmt(po.received_outers)} / {fmt(po.ordered_outers)}</strong>
                    <small>{fmt(po.outstanding_outers)} outstanding / {fmt(po.outstanding_line_count)} lines open</small>
                  </td>
                  <td>
                    <strong>{po.supplier_otif_pct == null ? '-' : po.supplier_otif_pct + '%'}</strong>
                    <small>
                      {po.supplier_avg_delay_days == null
                        ? 'no 180d history'
                        : po.supplier_avg_delay_days + 'd avg delay'}
                    </small>
                  </td>
                  <td>
                    <strong>
                      {po.at_risk_sku_count > 0
                        ? fmt(po.at_risk_sku_count) + ' SKU'
                        : 'Clear'}
                    </strong>
                    <small>
                      {po.at_risk_sku_count > 0
                        ? fmt(po.at_risk_units) + ' inbound units / ' +
                          fmt(po.affected_order_links) + ' order-SKU links'
                        : 'No linked inventory coverage exception'}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {listLoading && <div className="panel-empty">Loading purchase-order queue...</div>}
          {!listLoading && list && list.items.length === 0 && (
            <div className="panel-empty healthy-empty">
              {search
                ? 'No purchase orders match this search and filter.'
                : filter === 'overdue'
                  ? 'No open purchase orders are overdue.'
                  : filter === 'due_today'
                    ? 'No open purchase orders are due today.'
                    : filter === 'open'
                      ? 'No open supplier commitments remain.'
                      : filter === 'upcoming'
                        ? 'No upcoming open purchase orders.'
                        : 'No purchase orders for this filter.'}
            </div>
          )}
        </div>

        {list && list.count > 0 && (
          <div className="fulfillment-pagination">
            <span>
              Showing {(list.page - 1) * list.page_size + 1}-
              {Math.min(list.page * list.page_size, list.count)} of {fmt(list.count)}
            </span>
            <div>
              <button
                className="panel-action"
                disabled={list.page <= 1}
                onClick={() => changePage(Math.max(1, list.page - 1))}
              >
                <ChevronLeft size={15} /> Previous
              </button>
              <span>Page {list.page} of {list.total_pages}</span>
              <button
                className="panel-action"
                disabled={list.page >= list.total_pages}
                onClick={() => changePage(Math.min(list.total_pages, list.page + 1))}
              >
                Next <ChevronRight size={15} />
              </button>
            </div>
          </div>
        )}
      </section>

      {(selected || detailLoading) && (
        <RecordDetailDrawer
          className="procurement-record-drawer"
          kicker="Purchase-order record"
          title={selected ? 'PO #' + selected.purchase_order_id : 'Loading...'}
          loading={detailLoading && !selected}
          onClose={() => {
            setDetail(null)
            setWorkbench(null)
          }}
          status={selected ? (
            <span className={'status-chip ' + stateTone(selected.procurement_state)}>
              {stateLabel(selected.procurement_state, selected.days_overdue, selected.days_until_due)}
            </span>
          ) : undefined}
        >
          {selected && (
            <>
              <ExceptionWorkbench
                data={workbench}
                loading={workbenchLoading}
                onNavigate={onNavigate}
              />
              <div className="record-detail-list">
                <div>
                  <span>Supplier</span>
                  <strong>{selected.supplier_name ?? 'Supplier ' + selected.supplier_id}</strong>
                </div>
                <div><span>Order date</span><strong>{fmtDate(selected.order_date)}</strong></div>
                <div><span>Expected delivery</span><strong>{fmtDate(selected.expected_delivery_date)}</strong></div>
                <div>
                  <span>Operational state</span>
                  <strong>{stateLabel(selected.procurement_state, selected.days_overdue, selected.days_until_due)}</strong>
                </div>
                <div><span>Ordered outers</span><strong>{fmt(selected.ordered_outers)}</strong></div>
                <div><span>Received outers</span><strong>{fmt(selected.received_outers)}</strong></div>
                <div><span>Outstanding outers</span><strong>{fmt(selected.outstanding_outers)}</strong></div>
                <div><span>Outstanding lines</span><strong>{fmt(selected.outstanding_line_count)}</strong></div>
                <div><span>Finalized</span><strong>{selected.is_order_finalized ? 'Yes' : 'No'}</strong></div>
                <div><span>Last source update</span><strong>{fmtTs(selected.last_edited_when)}</strong></div>
              </div>

              <section className="record-lines-section">
                <div className="record-lines-header">
                  <div>
                    <span className="panel-kicker">Purchase-order lines</span>
                    <h4>PO receipt expectations</h4>
                  </div>
                  <strong>{fmt(selectedLines.length)} lines</strong>
                </div>

                <div className="record-line-list">
                  {selectedLines.map((line) => (
                    <div className="record-line-row procurement-line-row" key={line.purchase_order_line_key}>
                      <div>
                        <strong>{line.stock_item_name}</strong>
                        <span>
                          Stock item #{line.stock_item_id}
                          {line.package_name ? ' / ' + line.package_name : ''}
                        </span>
                      </div>
                      <div>
                        <span>{fmt(line.received_outers)} / {fmt(line.ordered_outers)} received</span>
                        <strong>{fmt(line.outstanding_outers)} outstanding</strong>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </RecordDetailDrawer>
      )}
    </div>
  )
}
