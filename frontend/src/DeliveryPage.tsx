import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Search,
  Truck,
  UserX,
} from 'lucide-react'
import {
  fetchDeliveryDetail,
  fetchDeliveryList,
  fetchDeliveryOverview,
  fetchDeliveryWorkbench,
  type DeliveryDetailResponse,
  type DeliveryListResponse,
  type DeliveryOverview,
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

const fmtTimestamp = (value: string | null | undefined) => {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
}

type DeliveryFilter = DeliveryListResponse['status']

type Props = {
  sseState: SseConnectionState
  refreshSignal: number
  initialFilter?: DeliveryFilter
  initialRecordId?: number | null
  onNavigate?: (
    domain: 'Fulfillment' | 'Delivery' | 'Inventory' | 'Procurement',
    recordId: number,
  ) => void
}

const filters: Array<{ value: DeliveryFilter; label: string }> = [
  { value: 'pending', label: 'Pending' },
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'due_today', label: 'Due today' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'receiver_not_present', label: 'Receiver absent history' },
  { value: 'all', label: 'All 30d' },
]

const agingFilter = (bucket: string): DeliveryFilter => {
  if (bucket === '1-2 days') return 'overdue_1_2'
  if (bucket === '3-5 days') return 'overdue_3_5'
  if (bucket === '6-10 days') return 'overdue_6_10'
  return 'overdue_10_plus'
}

function stateLabel(item: {
  delivery_state: string
  days_overdue: number
  days_until_due: number
}) {
  if (item.delivery_state === 'overdue') return item.days_overdue + 'd overdue'
  if (item.delivery_state === 'due_today') return 'Due today'
  if (item.delivery_state === 'confirmed') return 'Confirmed'
  return item.days_until_due > 0 ? item.days_until_due + 'd to due' : 'Pending'
}

function stateTone(state: string) {
  if (state === 'overdue') return 'critical'
  if (state === 'due_today') return 'warning'
  if (state === 'confirmed') return 'success'
  return 'monitoring'
}

function diffDays(start: string | null | undefined, end: string | null | undefined) {
  if (!start || !end) return null
  const a = new Date(start.length === 10 ? start + 'T00:00:00' : start)
  const b = new Date(end.length === 10 ? end + 'T00:00:00' : end)
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return null
  return Math.round(((b.getTime() - a.getTime()) / 86_400_000) * 100) / 100
}

const deliveryPageCache: {
  overview: DeliveryOverview | null
  lists: Map<string, DeliveryListResponse>
} = {
  overview: null,
  lists: new Map(),
}

const deliveryListKey = (
  filter: DeliveryFilter,
  page: number,
  search: string,
) => `${filter}|${page}|${search.trim().toLowerCase()}`

export default function DeliveryPage({
  sseState,
  refreshSignal,
  initialFilter = 'pending',
  initialRecordId = null,
  onNavigate,
}: Props) {
  const initialListKey = deliveryListKey(initialFilter, 1, '')
  const [data, setData] = useState<DeliveryOverview | null>(
    () => deliveryPageCache.overview,
  )
  const [list, setList] = useState<DeliveryListResponse | null>(
    () => deliveryPageCache.lists.get(initialListKey) ?? null,
  )
  const [filter, setFilter] = useState<DeliveryFilter>(initialFilter)
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [detail, setDetail] = useState<DeliveryDetailResponse | null>(null)
  const [workbench, setWorkbench] = useState<WorkbenchData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [listLoading, setListLoading] = useState(
    () => !deliveryPageCache.lists.has(initialListKey),
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
    const key = deliveryListKey(nextFilter, nextPage, nextSearch)
    const cachedRows = deliveryPageCache.lists.get(key) ?? null

    if (deliveryPageCache.overview) {
      setData(deliveryPageCache.overview)
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
      const [overview, deliveryList] = await Promise.all([
        fetchDeliveryOverview(),
        fetchDeliveryList(nextFilter, nextPage, 50, nextSearch),
      ])
      deliveryPageCache.overview = overview
      deliveryPageCache.lists.set(key, deliveryList)
      if (requestId !== requestSeq.current) return
      setData(overview)
      setList(deliveryList)
      setError(null)
    } catch (err) {
      if (requestId !== requestSeq.current) return
      setError(err instanceof Error ? err.message : 'Unable to load delivery data')
    } finally {
      if (requestId === requestSeq.current) {
        setListLoading(false)
        if (showBusy) setRefreshing(false)
      }
    }
  }

  const openDetail = async (invoiceId: number) => {
    setDetailLoading(true)
    setWorkbenchLoading(true)
    try {
      const [record, diagnostic] = await Promise.all([
        fetchDeliveryDetail(invoiceId),
        fetchDeliveryWorkbench(invoiceId),
      ])
      setDetail(record)
      setWorkbench(diagnostic)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load delivery detail')
    } finally {
      setDetailLoading(false)
      setWorkbenchLoading(false)
    }
  }

  const changeFilter = (nextFilter: DeliveryFilter) => {
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

  const selected = detail?.delivery
  const eventEvidence = useMemo(() => {
    const events = selected?.returned_delivery_data?.Events
    return Array.isArray(events) ? events : []
  }, [selected])

  const listTitle =
    filter === 'pending'
      ? 'Pending delivery queue'
      : filter === 'upcoming'
        ? 'Upcoming pending deliveries'
        : filter === 'overdue'
          ? 'Overdue delivery queue'
          : filter === 'overdue_1_2'
            ? 'Overdue deliveries / 1-2 days'
            : filter === 'overdue_3_5'
              ? 'Overdue deliveries / 3-5 days'
              : filter === 'overdue_6_10'
                ? 'Overdue deliveries / 6-10 days'
                : filter === 'overdue_10_plus'
                  ? 'Overdue deliveries / 10+ days'
                  : filter === 'due_today'
                    ? 'Due-today delivery queue'
                    : filter === 'receiver_not_present'
                      ? 'Receiver-absent event history'
                      : filter === 'confirmed'
                        ? 'Confirmed deliveries'
                        : 'All delivery records'

  return (
    <div className="fulfillment-page fulfillment-v2 delivery-v2">
      <section className="overview-heading">
        <div>
          <div className="overview-title-row">
            <h2>Delivery control</h2>
            <span className={'preview-pill sse-pill ' + sseState}>Realtime channel</span>
          </div>
          <p>
            Prioritize customer delivery risk, inspect delay aging and supported
            cycle-time stages, then trace the delivery back to its fulfillment record.
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

      {error && <div className="overview-error">Delivery serving error: {error}</div>}

      <section className="kpi-grid fulfillment-kpi-grid">
        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('all')}>
          <div className="kpi-icon tone-cool"><Truck size={20} /></div>
          <div className="kpi-copy">
            <span>Deliveries 30d</span>
            <strong>{fmt(data?.kpis.deliveries_30d)}</strong>
            <small>All delivery records in operational window</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('pending')}>
          <div className="kpi-icon tone-warning"><Clock3 size={20} /></div>
          <div className="kpi-copy">
            <span>Pending confirmation</span>
            <strong>{fmt(data?.kpis.pending)}</strong>
            <small>No confirmed delivery yet</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('overdue')}>
          <div className="kpi-icon tone-critical"><AlertTriangle size={20} /></div>
          <div className="kpi-copy">
            <span>Overdue</span>
            <strong>{fmt(data?.kpis.overdue)}</strong>
            <small>Expected delivery date has passed</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('due_today')}>
          <div className="kpi-icon tone-accent"><CalendarClock size={20} /></div>
          <div className="kpi-copy">
            <span>Due today</span>
            <strong>{fmt(data?.kpis.due_today)}</strong>
            <small>Due on {fmtDate(data?.as_of_date)}</small>
          </div>
        </article>
      </section>

      <section className="fulfillment-mid-grid">
        <article className="panel-card aging-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Overdue aging</span>
              <h3>Delivery exposure aging</h3>
            </div>
            <span className="panel-muted">{fmt(data?.kpis.overdue)} overdue deliveries</span>
          </div>

          <div className="aging-list">
            {(data?.aging ?? []).map((item) => (
              <button
                type="button"
                className="aging-row aging-row-action"
                key={item.bucket}
                onClick={() => changeFilter(agingFilter(item.bucket))}
                aria-label={'Open overdue deliveries aged ' + item.bucket}
              >
                <div className="aging-label">
                  <span>{item.bucket}</span>
                  <strong>{fmt(item.value)}</strong>
                </div>
                <div className="aging-track">
                  <i
                    style={{
                      width:
                        item.value === 0
                          ? '0%'
                          : Math.max(
                              6,
                              Math.round((item.value / maxAging) * 100),
                            ) + '%',
                    }}
                  />
                </div>
              </button>
            ))}
            {(data?.aging.length ?? 0) === 0 && (
              <div className="panel-empty healthy-empty">No overdue deliveries.</div>
            )}
          </div>
        </article>

        <article className="panel-card fulfillment-context-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Delivery outcome context</span>
              <h3>Queue context</h3>
            </div>
            <span className="status-chip success">
              {data?.operational_context.confirmation_rate ?? 0}% confirmed
            </span>
          </div>

          <div className="fulfillment-context-grid">
            <button className="context-stat-action" onClick={() => changeFilter('confirmed')}>
              <span>Confirmed in 30d</span>
              <strong>{fmt(data?.kpis.confirmed)}</strong>
            </button>
            <button className="context-stat-action" onClick={() => changeFilter('upcoming')}>
              <span>Upcoming pending</span>
              <strong>{fmt(data?.kpis.upcoming_pending)}</strong>
            </button>
            <div>
              <span>Median order → pick</span>
              <strong>
                {data?.operational_context.median_order_to_pick_days == null
                  ? '-'
                  : data.operational_context.median_order_to_pick_days + ' days'}
              </strong>
            </div>
            <div>
              <span>Median invoice → confirm</span>
              <strong>
                {data?.operational_context.median_invoice_to_confirm_days == null
                  ? '-'
                  : data.operational_context.median_invoice_to_confirm_days + ' days'}
              </strong>
            </div>
          </div>

          <p className="fulfillment-context-note delivery-history-note">
            Cycle time uses source-supported stages only; no dispatch/GPS stage is inferred.
            {' '}Order-to-pick p90: {data?.operational_context.p90_order_to_pick_days ?? '-'} days.
            {' '}Source lifecycle quality flag: {fmt(data?.operational_context.lifecycle_anomalies)} records exceed the reference gap, but remain included in KPIs and queues.
            {' '}Receiver-absent history: {fmt(data?.kpis.receiver_not_present_events)}.
            <button onClick={() => changeFilter('receiver_not_present')}>View event history</button>
          </p>
        </article>
      </section>

      <section className="panel-card fulfillment-table-card">
        <div className="panel-header fulfillment-queue-header">
          <div>
            <span className="panel-kicker">Operational delivery queue</span>
            <h3>{listTitle} / {fmt(list?.count)}</h3>
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
              placeholder="Search invoice, order, or customer"
              aria-label="Search delivery records"
            />
            {search && (
              <button type="button" onClick={clearSearch}>Clear</button>
            )}
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

        <div className="fulfillment-table-wrap">
          <table className="fulfillment-table delivery-work-table">
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Customer</th>
                <th>Order</th>
                <th>Expected</th>
                <th>Operational state</th>
                <th>Latest source event</th>
                <th>Cycle</th>
              </tr>
            </thead>
            <tbody>
              {(list?.items ?? []).map((delivery) => (
                <tr
                  key={delivery.invoice_id}
                  onClick={() => void openDetail(delivery.invoice_id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td className="mono-cell">#{delivery.invoice_id}</td>
                  <td>
                    <strong>{delivery.customer_name}</strong>
                    <small>Customer {delivery.customer_id}</small>
                  </td>
                  <td>#{delivery.order_id}</td>
                  <td>
                    {fmtDate(delivery.expected_delivery_date)}
                    <small>Invoice {fmtDate(delivery.invoice_date)}</small>
                  </td>
                  <td>
                    <span className={'status-chip ' + stateTone(delivery.delivery_state)}>
                      {stateLabel(delivery)}
                    </span>
                  </td>
                  <td>
                    <strong>
                      {delivery.confirmed_delivery_time
                        ? 'Confirmed delivery'
                        : delivery.latest_event || 'No source event'}
                    </strong>
                    <small>
                      {delivery.confirmed_delivery_time
                        ? fmtTimestamp(delivery.confirmed_delivery_time)
                        : delivery.latest_event_comment ||
                          (delivery.had_receiver_not_present
                            ? 'Receiver not present recorded previously'
                            : '')}
                    </small>
                  </td>
                  <td>
                    <strong>
                      {diffDays(delivery.order_date, delivery.picking_completed_when) == null
                        ? 'Pick pending'
                        : 'Order→Pick ' + diffDays(delivery.order_date, delivery.picking_completed_when) + 'd'}
                    </strong>
                    <small>
                      {delivery.confirmed_delivery_time
                        ? 'Invoice→Confirm ' +
                          (diffDays(delivery.invoice_date, delivery.confirmed_delivery_time) ?? '-') +
                          'd'
                        : 'Confirmation pending'}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {listLoading && <div className="panel-empty">Loading delivery queue...</div>}
          {!listLoading && list && list.items.length === 0 && (
            <div className="panel-empty healthy-empty">
              {search ? 'No deliveries match this search and filter.' : 'No records for this filter.'}
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
          className="delivery-record-drawer"
          kicker="Delivery record"
          title={selected ? 'Invoice #' + selected.invoice_id : 'Loading...'}
          loading={detailLoading && !selected}
          onClose={() => {
            setDetail(null)
            setWorkbench(null)
          }}
          status={selected ? (
            <span className={'status-chip ' + stateTone(selected.delivery_state)}>
              {stateLabel(selected)}
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
                <div><span>Customer</span><strong>{selected.customer_name}</strong></div>
                <div><span>Order</span><strong>#{selected.order_id}</strong></div>
                <div><span>Invoice date</span><strong>{fmtDate(selected.invoice_date)}</strong></div>
                <div><span>Expected delivery</span><strong>{fmtDate(selected.expected_delivery_date)}</strong></div>
                <div>
                  <span>Operational state</span>
                  <strong>{stateLabel(selected)}</strong>
                </div>
                <div>
                  <span>Days overdue</span>
                  <strong>{selected.delivery_state === 'overdue' ? selected.days_overdue + ' days' : '-'}</strong>
                </div>
                <div>
                  <span>Latest source event</span>
                  <strong>{selected.latest_event || '-'}</strong>
                </div>
                <div>
                  <span>Latest event comment</span>
                  <strong>{selected.latest_event_comment || '-'}</strong>
                </div>
                <div><span>Confirmed delivery</span><strong>{fmtTimestamp(selected.confirmed_delivery_time)}</strong></div>
                <div><span>Received by</span><strong>{selected.confirmed_received_by || '-'}</strong></div>
                <div><span>Last source update</span><strong>{fmtTimestamp(selected.last_edited_when)}</strong></div>
              </div>

              <section className="record-lines-section">
                <div className="record-lines-header">
                  <div>
                    <span className="panel-kicker">Source-event timeline</span>
                    <h4>Delivery event summary</h4>
                  </div>
                  <strong>{fmt(eventEvidence.length)} events</strong>
                </div>

                <div className="delivery-event-list">
                  {eventEvidence.length > 0 ? eventEvidence.map((event, index) => (
                    <div className="delivery-event-row" key={String(event.EventTime ?? index)}>
                      <div>
                        <strong>{String(event.Event ?? 'Event')}</strong>
                        <span>{fmtTimestamp(typeof event.EventTime === 'string' ? event.EventTime : null)}</span>
                      </div>
                      <div>
                        {event.Comment && <span>{String(event.Comment)}</span>}
                        {event.ConNote && <small>ConNote {String(event.ConNote)}</small>}
                      </div>
                    </div>
                  )) : (
                    <div className="panel-empty">No source-event timeline is available for this invoice.</div>
                  )}
                </div>
              </section>
            </>
          )}
        </RecordDetailDrawer>
      )}
    </div>
  )
}
