import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Clock3,
  PackageCheck,
  RefreshCw,
  Search,
} from 'lucide-react'
import {
  fetchFulfillmentDetail,
  fetchFulfillmentList,
  fetchFulfillmentOverview,
  fetchFulfillmentWorkbench,
  type FulfillmentDetailResponse,
  type FulfillmentFilter,
  type FulfillmentListResponse,
  type FulfillmentOverview,
  type ExceptionWorkbench as WorkbenchData,
  type SseConnectionState,
} from './api'
import RecordDetailDrawer from './RecordDetailDrawer'
import ExceptionWorkbench from './ExceptionWorkbench'

const nf = new Intl.NumberFormat('en-US')
const valueFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const fmt = (value: number | undefined) =>
  value === undefined ? '-' : nf.format(value)

const fmtValue = (value: number | undefined) =>
  value === undefined ? '-' : valueFormatter.format(value)

const fmtDate = (value: string | null | undefined) => {
  if (!value) return '-'
  const d = new Date(value.length === 10 ? value + 'T00:00:00' : value)
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

const fmtTimestamp = (value: string | null | undefined) => {
  if (!value) return '-'
  const d = new Date(value)
  return Number.isNaN(d.getTime())
    ? '-'
    : d.toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
}

type Props = {
  sseState: SseConnectionState
  refreshSignal: number
  initialFilter?: FulfillmentFilter
  initialRecordId?: number | null
  onNavigate?: (
    domain: 'Fulfillment' | 'Delivery' | 'Inventory' | 'Procurement',
    recordId: number,
  ) => void
}

const filters: Array<{ value: FulfillmentFilter; label: string }> = [
  { value: 'open', label: 'Open' },
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'due_today', label: 'Due today' },
  { value: 'backorder', label: 'Backorder' },
  { value: 'completed', label: 'Completed' },
  { value: 'all', label: 'All 30d' },
]

const agingFilter = (bucket: string): FulfillmentFilter => {
  if (bucket === '1-2 days') return 'overdue_1_2'
  if (bucket === '3-7 days') return 'overdue_3_7'
  if (bucket === '8-14 days') return 'overdue_8_14'
  return 'overdue_15_plus'
}

function riskLabel(state: string, daysOverdue: number) {
  if (state === 'overdue') return daysOverdue + 'd overdue'
  if (state === 'due_today') return 'Due today'
  if (state === 'completed') return 'Completed'
  return 'Upcoming'
}

const fulfillmentPageCache: {
  overview: FulfillmentOverview | null
  lists: Map<string, FulfillmentListResponse>
} = {
  overview: null,
  lists: new Map(),
}

const fulfillmentListKey = (
  filter: FulfillmentFilter,
  page: number,
  search: string,
) => `${filter}|${page}|${search.trim().toLowerCase()}`

export default function FulfillmentPage({
  sseState,
  refreshSignal,
  initialFilter = 'open',
  initialRecordId = null,
  onNavigate,
}: Props) {
  const initialListKey = fulfillmentListKey(initialFilter, 1, '')
  const [data, setData] = useState<FulfillmentOverview | null>(
    () => fulfillmentPageCache.overview,
  )
  const [list, setList] = useState<FulfillmentListResponse | null>(
    () => fulfillmentPageCache.lists.get(initialListKey) ?? null,
  )
  const [filter, setFilter] = useState<FulfillmentFilter>(initialFilter)
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [detail, setDetail] = useState<FulfillmentDetailResponse | null>(null)
  const [workbench, setWorkbench] = useState<WorkbenchData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [workbenchLoading, setWorkbenchLoading] = useState(false)
  const [listLoading, setListLoading] = useState(
    () => !fulfillmentPageCache.lists.has(initialListKey),
  )
  const requestSeq = useRef(0)
  const refreshSignalMounted = useRef(false)

  const load = async (
    showBusy = false,
    nextFilter = filter,
    nextPage = page,
    nextSearch = search,
  ) => {
    const requestId = ++requestSeq.current
    const key = fulfillmentListKey(nextFilter, nextPage, nextSearch)
    const cachedRows = fulfillmentPageCache.lists.get(key) ?? null

    if (fulfillmentPageCache.overview) {
      setData(fulfillmentPageCache.overview)
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
        fetchFulfillmentOverview(),
        fetchFulfillmentList(nextFilter, nextPage, 50, nextSearch),
      ])
      fulfillmentPageCache.overview = overview
      fulfillmentPageCache.lists.set(key, rows)
      if (requestId !== requestSeq.current) return
      setData(overview)
      setList(rows)
      setError(null)
    } catch (err) {
      if (requestId !== requestSeq.current) return
      setError(err instanceof Error ? err.message : 'Unable to load fulfillment data')
    } finally {
      if (requestId === requestSeq.current) {
        setListLoading(false)
        if (showBusy) setRefreshing(false)
      }
    }
  }

  const openDetail = async (orderId: number) => {
    setDetailLoading(true)
    setWorkbenchLoading(true)
    try {
      const [record, diagnostic] = await Promise.all([
        fetchFulfillmentDetail(orderId),
        fetchFulfillmentWorkbench(orderId),
      ])
      setDetail(record)
      setWorkbench(diagnostic)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load order detail')
    } finally {
      setDetailLoading(false)
      setWorkbenchLoading(false)
    }
  }

  const changeFilter = (nextFilter: FulfillmentFilter) => {
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

  const maxAging = useMemo(
    () => Math.max(1, ...(data?.aging.map((item) => item.value) ?? [1])),
    [data],
  )

  const selected = detail?.order
  const selectedLines = detail?.lines ?? []

  const listTitle =
    filter === 'open'
      ? 'Open order queue'
      : filter === 'upcoming'
        ? 'Upcoming open orders'
        : filter === 'completed'
          ? 'Completed orders'
          : filter === 'overdue'
            ? 'Overdue order queue'
            : filter === 'overdue_1_2'
              ? 'Overdue orders / 1-2 days'
              : filter === 'overdue_3_7'
                ? 'Overdue orders / 3-7 days'
                : filter === 'overdue_8_14'
                  ? 'Overdue orders / 8-14 days'
                  : filter === 'overdue_15_plus'
                    ? 'Overdue orders / 15+ days'
                    : filter === 'due_today'
                      ? 'Due-today queue'
                      : filter === 'backorder'
                        ? 'Active backorders'
                        : 'All fulfillment records'

  return (
    <div className="fulfillment-page fulfillment-v2">
      <section className="overview-heading">
        <div>
          <div className="overview-title-row">
            <h2>Fulfillment control</h2>
            <span className={'preview-pill sse-pill ' + sseState}>Realtime channel</span>
          </div>
          <p>
            Work the current order queue: identify overdue and due-today orders,
            then open the exact customer and order-line evidence.
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

      {error && (
        <div className="overview-error">Fulfillment serving error: {error}</div>
      )}

      <section className="kpi-grid fulfillment-kpi-grid">
        <article
          className="kpi-card clickable-kpi"
          onClick={() => changeFilter('open')}
        >
          <div className="kpi-icon tone-accent">
            <PackageCheck size={20} />
          </div>
          <div className="kpi-copy">
            <span>Open orders</span>
            <strong>{fmt(data?.kpis.open_orders)}</strong>
            <small>Picking not completed / open queue</small>
          </div>
        </article>

        <article
          className="kpi-card clickable-kpi"
          onClick={() => changeFilter('overdue')}
        >
          <div className="kpi-icon tone-critical">
            <AlertTriangle size={20} />
          </div>
          <div className="kpi-copy">
            <span>Overdue</span>
            <strong>{fmt(data?.kpis.overdue_orders)}</strong>
            <small>Expected delivery date has passed</small>
          </div>
        </article>

        <article
          className="kpi-card clickable-kpi"
          onClick={() => changeFilter('due_today')}
        >
          <div className="kpi-icon tone-warning">
            <CalendarClock size={20} />
          </div>
          <div className="kpi-copy">
            <span>Due today</span>
            <strong>{fmt(data?.kpis.due_today)}</strong>
            <small>Due on {fmtDate(data?.as_of_date)}</small>
          </div>
        </article>

        <article
          className="kpi-card clickable-kpi"
          onClick={() => changeFilter('backorder')}
        >
          <div className="kpi-icon tone-cool">
            <RefreshCw size={20} />
          </div>
          <div className="kpi-copy">
            <span>Active backorders</span>
            <strong>{fmt(data?.kpis.backorders)}</strong>
            <small>Open orders with a backorder reference</small>
          </div>
        </article>
      </section>

      <section className="fulfillment-mid-grid">
        <article className="panel-card aging-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Overdue aging</span>
              <h3>Current exposure aging</h3>
            </div>
            <span className="panel-muted">
              {fmt(data?.kpis.overdue_orders)} overdue orders
            </span>
          </div>

          <div className="aging-list">
            {(data?.aging ?? []).map((item) => (
              <button
                type="button"
                className="aging-row aging-row-action"
                key={item.bucket}
                onClick={() => changeFilter(agingFilter(item.bucket))}
                aria-label={'Open overdue orders aged ' + item.bucket}
              >
                <div className="aging-label">
                  <span>{item.bucket}</span>
                  <strong>{fmt(item.value)}</strong>
                </div>
                <div className="aging-track">
                  <i
                    style={{
                      width:
                        Math.max(
                          6,
                          Math.round((item.value / maxAging) * 100),
                        ) + '%',
                    }}
                  />
                </div>
              </button>
            ))}
          </div>
        </article>

        <article className="panel-card fulfillment-context-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Operational snapshot</span>
              <h3>Operational attention profile</h3>
            </div>
            <span className="status-chip warning">
              {data?.operational_context.overdue_rate ?? 0}% overdue
            </span>
          </div>

          <div className="fulfillment-context-grid">
            <div>
              <span>Median overdue age</span>
              <strong>{fmt(data?.operational_context.median_days_overdue)} days</strong>
            </div>
            <div>
              <span>Oldest overdue</span>
              <strong>{fmt(data?.operational_context.oldest_days_overdue)} days</strong>
            </div>
            <div>
              <span>Orders with supply exposure</span>
              <strong>{fmt(data?.operational_context.supply_exposed_orders)}</strong>
            </div>
            <div>
              <span>Critical supply-linked orders</span>
              <strong>{fmt(data?.operational_context.critical_supply_orders)}</strong>
            </div>
          </div>

          <p className="fulfillment-context-note">
            Overdue share is calculated from the current open-order queue, not
            from historical backlog.
          </p>
        </article>
      </section>

      <section className="panel-card fulfillment-table-card">
        <div className="panel-header fulfillment-queue-header">
          <div>
            <span className="panel-kicker">Operational order queue</span>
            <h3>{listTitle} / {fmt(list?.count)}</h3>
            <p className="fulfillment-queue-description">
              One row represents one customer order. Use promise status, picking progress,
              and linked supply exposure to prioritize investigation.
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
              placeholder="Search order ID or customer"
              aria-label="Search fulfillment orders"
            />
            {search && (
              <button type="button" onClick={clearSearch}>
                Clear
              </button>
            )}
            <button type="submit">Search</button>
          </form>

          <div className="fulfillment-filter-row">
            {filters.map((item) => (
              <button
                key={item.value}
                className={
                  'panel-action ' + (filter === item.value ? 'active' : '')
                }
                onClick={() => changeFilter(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="fulfillment-table-wrap">
          <table className="fulfillment-table fulfillment-work-table">
            <thead>
              <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Promise</th>
                <th>Status</th>
                <th>Picking / size</th>
                <th>Order value</th>
                <th>Risk / supply</th>
              </tr>
            </thead>
            <tbody>
              {(list?.items ?? []).map((order) => (
                <tr
                  key={order.order_id}
                  onClick={() => void openDetail(order.order_id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td className="mono-cell">#{order.order_id}</td>
                  <td>
                    <strong>{order.customer_name}</strong>
                    <small>Customer {order.customer_id}</small>
                  </td>
                  <td>
                    {fmtDate(order.expected_delivery_date)}
                    <small>Ordered {fmtDate(order.order_date)}</small>
                  </td>
                  <td>
                    <span
                      className={
                        'status-chip ' +
                        (order.risk_state === 'overdue'
                          ? 'critical'
                          : order.risk_state === 'due_today'
                            ? 'warning'
                            : order.risk_state === 'completed'
                              ? 'success'
                              : 'monitoring')
                      }
                    >
                      {riskLabel(order.risk_state, order.days_overdue)}
                    </span>
                  </td>
                  <td>
                    <strong>
                      {fmt(order.picked_lines)} / {fmt(order.line_count)} line{order.line_count === 1 ? '' : 's'}
                    </strong>
                    <small>
                      {order.line_count > 0
                        ? Math.round((order.picked_lines / order.line_count) * 100) + '% picked'
                        : 'No lines'}
                      {' · '}{fmt(order.units_ordered)} units
                    </small>
                  </td>
                  <td className="value-cell">{fmtValue(order.order_value)}</td>
                  <td>
                    <span
                      className={
                        'status-chip ' +
                        (order.exception_priority === 'high'
                          ? 'critical'
                          : order.exception_priority === 'medium'
                            ? 'warning'
                            : 'success')
                      }
                    >
                      {order.exception_priority.toUpperCase()}
                    </span>
                    <small>
                      {order.supply_exposed_sku_count > 0
                        ? order.supply_exposed_sku_count + ' supply-exposed SKU'
                        : order.active_backorder
                          ? 'Backorder #' + order.backorder_order_id
                          : 'No verified upstream supply issue'}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {listLoading && (
            <div className="panel-empty">Loading order queue...</div>
          )}
          {!listLoading && list && list.items.length === 0 && (
            <div className="panel-empty healthy-empty">
              {search
                ? 'No orders match this search and filter.'
                : 'No records for this filter.'}
            </div>
          )}
        </div>

        {list && list.count > 0 && (
          <div className="fulfillment-pagination">
            <span>
              Showing {(list.page - 1) * list.page_size + 1}-
              {Math.min(list.page * list.page_size, list.count)} of{' '}
              {fmt(list.count)}
            </span>

            <div>
              <button
                className="panel-action"
                disabled={list.page <= 1}
                onClick={() => changePage(Math.max(1, list.page - 1))}
              >
                <ChevronLeft size={15} /> Previous
              </button>

              <span>
                Page {list.page} of {list.total_pages}
              </span>

              <button
                className="panel-action"
                disabled={list.page >= list.total_pages}
                onClick={() =>
                  changePage(Math.min(list.total_pages, list.page + 1))
                }
              >
                Next <ChevronRight size={15} />
              </button>
            </div>
          </div>
        )}
      </section>

      {(selected || detailLoading) && (
        <RecordDetailDrawer
          kicker="Fulfillment order"
          title={selected ? 'Order #' + selected.order_id : 'Loading...'}
          loading={detailLoading && !selected}
          onClose={() => {
            setDetail(null)
            setWorkbench(null)
          }}
          status={
            selected ? (
              <span
                className={
                  'status-chip ' +
                  (selected.risk_state === 'overdue'
                    ? 'critical'
                    : selected.risk_state === 'due_today'
                      ? 'warning'
                      : selected.risk_state === 'completed'
                        ? 'success'
                        : 'monitoring')
                }
              >
                {riskLabel(selected.risk_state, selected.days_overdue)}
              </span>
            ) : undefined
          }
        >
          {selected && (
            <>
              <section className="fulfillment-drawer-summary" aria-label="Order summary">
                <div>
                  <span>Customer</span>
                  <strong>{selected.customer_name}</strong>
                  <small>Customer {selected.customer_id}</small>
                </div>
                <div>
                  <span>Customer promise</span>
                  <strong>{fmtDate(selected.expected_delivery_date)}</strong>
                  <small>Ordered {fmtDate(selected.order_date)}</small>
                </div>
                <div>
                  <span>Picking</span>
                  <strong>{fmt(selected.picked_lines)} / {fmt(selected.line_count)} lines</strong>
                  <small>
                    {selected.line_count > 0
                      ? Math.round((selected.picked_lines / selected.line_count) * 100) + '% complete'
                      : 'No order lines'}
                  </small>
                </div>
                <div>
                  <span>Order value</span>
                  <strong>{fmtValue(selected.order_value)}</strong>
                  <small>{fmt(selected.units_ordered)} units ordered</small>
                </div>
              </section>

              <ExceptionWorkbench
                data={workbench}
                loading={workbenchLoading}
                onNavigate={onNavigate}
              />
              <section className="fulfillment-source-facts">
                <div className="fulfillment-drawer-section-heading">
                  <span className="panel-kicker">Source record</span>
                  <h4>Order facts</h4>
                </div>
                <div className="record-detail-list">
                <div>
                  <span>Customer</span>
                  <strong>{selected.customer_name}</strong>
                </div>
                <div>
                  <span>Order date</span>
                  <strong>{fmtDate(selected.order_date)}</strong>
                </div>
                <div>
                  <span>Expected delivery</span>
                  <strong>{fmtDate(selected.expected_delivery_date)}</strong>
                </div>
                <div>
                  <span>Days overdue</span>
                  <strong>
                    {selected.risk_state === 'overdue'
                      ? selected.days_overdue + ' days'
                      : '-'}
                  </strong>
                </div>
                <div>
                  <span>Picking completed</span>
                  <strong>{fmtTimestamp(selected.picking_completed_when)}</strong>
                </div>
                <div>
                  <span>Order lines</span>
                  <strong>{fmt(selected.line_count)}</strong>
                </div>
                <div>
                  <span>Picking progress</span>
                  <strong>
                    {fmt(selected.picked_lines)} / {fmt(selected.line_count)} lines
                    {selected.line_count > 0
                      ? ' (' + Math.round((selected.picked_lines / selected.line_count) * 100) + '%)'
                      : ''}
                  </strong>
                </div>
                <div>
                  <span>Units ordered</span>
                  <strong>{fmt(selected.units_ordered)}</strong>
                </div>
                <div>
                  <span>Order value</span>
                  <strong>{fmtValue(selected.order_value)}</strong>
                </div>
                <div>
                  <span>Backorder</span>
                  <strong>
                    {selected.active_backorder && selected.backorder_order_id
                      ? 'Backorder of #' + selected.backorder_order_id
                      : 'No active backorder reference'}
                  </strong>
                </div>
                <div>
                  <span>Last source update</span>
                  <strong>{fmtTimestamp(selected.last_edited_when)}</strong>
                </div>
                </div>
              </section>

              <section className="record-lines-section">
                <div className="record-lines-header">
                  <div>
                    <span className="panel-kicker">Order lines</span>
                    <h4>Order contents</h4>
                  </div>
                  <strong>{fmt(selectedLines.length)} lines</strong>
                </div>

                <div className="record-line-list">
                  {selectedLines.map((line) => (
                    <div className="record-line-row" key={line.order_line_key}>
                      <div>
                        <strong>{line.description}</strong>
                        <span>Stock item #{line.stock_item_id}</span>
                      </div>
                      <div>
                        <span>{line.picking_completed_when ? 'Picked' : 'Open'} / {fmt(line.quantity)} units</span>
                        <strong>{fmtValue(line.total_including_tax)}</strong>
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
