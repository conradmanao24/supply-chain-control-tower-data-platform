import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Boxes,
  ChevronLeft,
  ChevronRight,
  PackageX,
  Search,
  ShieldAlert,
} from 'lucide-react'
import {
  fetchInventoryDetail,
  fetchInventoryList,
  fetchInventoryOverview,
  fetchInventoryWorkbench,
  type InventoryDetailResponse,
  type InventoryFilter,
  type InventoryListResponse,
  type InventoryOverview,
  type ExceptionWorkbench as WorkbenchData,
  type SseConnectionState,
} from './api'
import RecordDetailDrawer from './RecordDetailDrawer'
import ExceptionWorkbench from './ExceptionWorkbench'

const nf = new Intl.NumberFormat('en-US')
const fmt = (value: number | undefined) => (value === undefined ? '-' : nf.format(value))

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

const labelForState = (state: string) =>
  state === 'negative'
    ? 'Negative'
    : state === 'out_of_stock'
      ? 'Out of stock'
      : state === 'reorder'
        ? 'Reorder required'
        : 'Above reorder'

const coverageLabel = (state: string) =>
  state === 'negative_stock'
    ? 'Negative stock'
    : state === 'projected_shortfall'
      ? 'Projected shortfall'
      : state === 'stockout_before_inbound'
        ? 'Stockout before inbound'
        : state === 'coverage_gap'
          ? 'Coverage gap'
          : state === 'reorder'
            ? 'Reorder'
            : 'Covered'

const coverageTone = (severity: string) =>
  severity === 'critical'
    ? 'critical'
    : severity === 'warning'
      ? 'warning'
      : 'success'


const healthFilter = (state: string): InventoryFilter =>
  state === 'negative'
    ? 'negative'
    : state === 'out_of_stock'
      ? 'out_of_stock'
      : state === 'reorder'
        ? 'reorder'
        : 'healthy'

const fmtCover = (value: number | null | undefined) => {
  if (value == null) return '-'
  if (value > 0 && value < 0.1) return '<0.1'
  return value.toFixed(1)
}

const inventoryPageCache: {
  overview: InventoryOverview | null
  lists: Map<string, InventoryListResponse>
} = {
  overview: null,
  lists: new Map(),
}

const inventoryListKey = (
  filter: InventoryFilter,
  page: number,
  search: string,
) => `${filter}|${page}|${search.trim().toLowerCase()}`


type Props = {
  sseState: SseConnectionState
  refreshSignal: number
  initialFilter?: InventoryFilter
  initialRecordId?: number | null
  onNavigate?: (
    domain: 'Fulfillment' | 'Delivery' | 'Inventory' | 'Procurement',
    recordId: number,
  ) => void
}

const filters: Array<{ value: InventoryFilter; label: string }> = [
  { value: 'risk', label: 'Supply risk' },
  { value: 'reorder', label: 'Reorder required' },
  { value: 'out_of_stock', label: 'Out of stock' },
  { value: 'negative', label: 'Negative' },
  { value: 'healthy', label: 'Above reorder' },
  { value: 'all', label: 'All items' },
]

export default function InventoryPage({
  sseState,
  refreshSignal,
  initialFilter = 'risk',
  initialRecordId = null,
  onNavigate,
}: Props) {
  const initialListKey = inventoryListKey(initialFilter, 1, '')
  const [data, setData] = useState<InventoryOverview | null>(
    () => inventoryPageCache.overview,
  )
  const [list, setList] = useState<InventoryListResponse | null>(
    () => inventoryPageCache.lists.get(initialListKey) ?? null,
  )
  const [filter, setFilter] = useState<InventoryFilter>(initialFilter)
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [detail, setDetail] = useState<InventoryDetailResponse | null>(null)
  const [workbench, setWorkbench] = useState<WorkbenchData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [listLoading, setListLoading] = useState(
    () => !inventoryPageCache.lists.has(initialListKey),
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
    const key = inventoryListKey(nextFilter, nextPage, nextSearch)
    const cachedRows = inventoryPageCache.lists.get(key) ?? null

    if (inventoryPageCache.overview) {
      setData(inventoryPageCache.overview)
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
        fetchInventoryOverview(),
        fetchInventoryList(nextFilter, nextPage, 50, nextSearch),
      ])
      inventoryPageCache.overview = overview
      inventoryPageCache.lists.set(key, rows)
      if (requestId !== requestSeq.current) return
      setData(overview)
      setList(rows)
      setError(null)
    } catch (err) {
      if (requestId !== requestSeq.current) return
      setError(err instanceof Error ? err.message : 'Unable to load inventory data')
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
        fetchInventoryDetail(id),
        fetchInventoryWorkbench(id),
      ])
      setDetail(record)
      setWorkbench(diagnostic)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load inventory detail')
    } finally {
      setDetailLoading(false)
      setWorkbenchLoading(false)
    }
  }

  const changeFilter = (nextFilter: InventoryFilter) => {
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

  const totalHealth = useMemo(
    () => Math.max(1, (data?.stock_health ?? []).reduce((sum, item) => sum + item.value, 0)),
    [data],
  )

  const selected = detail?.item

  const listTitle =
    filter === 'risk'
      ? 'Supply-risk queue'
      : filter === 'reorder'
      ? 'Reorder-required queue'
      : filter === 'out_of_stock'
        ? 'Out-of-stock items'
        : filter === 'negative'
          ? 'Negative-stock exceptions'
          : filter === 'healthy'
            ? 'Items above reorder level'
            : 'All inventory items'

  return (
    <div className="fulfillment-page fulfillment-v2 inventory-v2">
      <section className="overview-heading">
        <div>
          <div className="overview-title-row">
            <h2>Inventory control</h2>
            <span className={'preview-pill sse-pill ' + sseState}>Realtime channel</span>
          </div>
          <p>
            Prioritize stockout and coverage risk by combining on-hand inventory,
            open demand, inbound purchase orders, and actual outbound demand velocity.
          </p>
        </div>

        <div className="overview-meta">
          <span>
            <span className={'live-dot sse-' + sseState} />
            Realtime {sseState}
          </span>
          <span>Latest source state {fmtTs(data?.latest_state_edit)}</span>
        </div>
      </section>

      {error && <div className="overview-error">Inventory serving error: {error}</div>}

      <section className="kpi-grid fulfillment-kpi-grid">
        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('all')}>
          <div className="kpi-icon tone-cool"><Boxes size={20} /></div>
          <div className="kpi-copy">
            <span>Stock items</span>
            <strong>{fmt(data?.kpis.total_items)}</strong>
            <small>All current stock-item states</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('risk')}>
          <div className="kpi-icon tone-critical"><AlertTriangle size={20} /></div>
          <div className="kpi-copy">
            <span>Supply risk</span>
            <strong>{fmt(data?.kpis.supply_risk_items)}</strong>
            <small>{fmt(data?.kpis.critical_supply_risk_items)} critical coverage gaps</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('out_of_stock')}>
          <div className="kpi-icon tone-accent"><PackageX size={20} /></div>
          <div className="kpi-copy">
            <span>Out of stock</span>
            <strong>{fmt(data?.kpis.out_of_stock)}</strong>
            <small>Quantity on hand equals zero</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('negative')}>
          <div className="kpi-icon tone-critical"><ShieldAlert size={20} /></div>
          <div className="kpi-copy">
            <span>Negative stock</span>
            <strong>{fmt(data?.kpis.negative_stock)}</strong>
            <small>Invalid on-hand state requiring correction</small>
          </div>
        </article>
      </section>

      <section className="fulfillment-mid-grid">
        <article className="panel-card aging-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Inventory state</span>
              <h3>Current stock-state distribution</h3>
            </div>
            <span className="panel-muted">{fmt(data?.kpis.total_items)} items</span>
          </div>

          <div className="aging-list">
            {(data?.stock_health ?? []).map((item) => (
              <button
                type="button"
                className="aging-row aging-row-action inventory-health-row"
                key={item.state}
                onClick={() => changeFilter(healthFilter(item.state))}
                aria-label={'Open ' + labelForState(item.state).toLowerCase() + ' inventory items'}
              >
                <div className="aging-label">
                  <span>{labelForState(item.state)}</span>
                  <strong>{fmt(item.value)}</strong>
                </div>
                <div className={'aging-track inventory-health-track ' + item.state}>
                  <i
                    style={{
                      width:
                        item.value === 0
                          ? '0%'
                          : Math.max(
                              2,
                              Math.round((item.value / totalHealth) * 100),
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
              <span className="panel-kicker">Supply / demand context</span>
              <h3>Coverage projection</h3>
            </div>
            <span className={'status-chip ' + ((data?.kpis.supply_risk_items ?? 0) > 0 ? 'critical' : 'success')}>
              {(data?.kpis.supply_risk_items ?? 0) > 0
                ? fmt(data?.kpis.supply_risk_items) + ' supply-risk items'
                : 'Covered'}
            </span>
          </div>

          <div className="fulfillment-context-grid">
            <div>
              <span>Open demand</span>
              <strong>{fmt(data?.operational_context.open_demand_units)} units</strong>
            </div>
            <div>
              <span>Incoming supply</span>
              <strong>{fmt(data?.operational_context.incoming_units)} units</strong>
            </div>
            <div>
              <span>Timing shortfall before inbound</span>
              <strong>{fmt(data?.operational_context.pre_inbound_shortfall_units)} units</strong>
            </div>
            <div>
              <span>Final projected shortfall</span>
              <strong>{fmt(data?.operational_context.projected_shortfall_units)} units</strong>
            </div>
          </div>

          <p className="fulfillment-context-note">
            Timing risk can exist even when final projected stock is positive: customer demand may be due before the next inbound receipt.
            {' '}WWI TargetStockLevel is treated as typical order quantity, not an on-hand stock threshold.
          </p>
        </article>
      </section>

      <section className="panel-card fulfillment-table-card">
        <div className="panel-header fulfillment-queue-header">
          <div>
            <span className="panel-kicker">Operational inventory queue</span>
            <h3>{listTitle} / {fmt(list?.count)}</h3>
            <p className="inventory-queue-description">
              One row represents one stock item. Coverage risk combines timing of demand,
              current on-hand stock, and inbound purchase orders.
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
              placeholder="Search stock item ID or name"
              aria-label="Search inventory items"
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

        <div className={'fulfillment-table-wrap ' + (!listLoading && list && list.items.length === 0 ? 'inventory-empty-wrap' : '')}>
          <table className="fulfillment-table inventory-work-table">
            <thead>
              <tr>
                <th>Stock item</th>
                <th>On hand</th>
                <th>Open demand</th>
                <th>Incoming</th>
                <th>Projected balance</th>
                <th>Days cover</th>
                <th>Coverage</th>
              </tr>
            </thead>
            <tbody>
              {(list?.items ?? []).map((item) => (
                <tr
                  key={item.stock_item_id}
                  onClick={() => void openDetail(item.stock_item_id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>
                    <strong>{item.stock_item_name}</strong>
                    <small>Stock item #{item.stock_item_id}</small>
                  </td>
                  <td>
                    <strong>{fmt(item.quantity_on_hand)}</strong>
                    <small>reorder {fmt(item.reorder_level)}</small>
                  </td>
                  <td>
                    <strong>{fmt(item.open_demand_units)}</strong>
                    <small>{fmt(item.affected_orders)} affected orders</small>
                  </td>
                  <td>
                    <strong>{fmt(item.incoming_units)}</strong>
                    <small>{item.next_inbound_date ? 'next ' + item.next_inbound_date : 'no scoped inbound'}</small>
                  </td>
                  <td>
                    <strong>{fmt(item.projected_available)}</strong>
                    <small>on hand + inbound - demand</small>
                  </td>
                  <td>
                    <strong>{fmtCover(item.days_of_cover)}</strong>
                    <small>
                      {item.days_to_next_inbound == null
                        ? 'no inbound ETA'
                        : item.days_to_next_inbound + 'd to inbound'}
                    </small>
                  </td>
                  <td>
                    <span className={'status-chip ' + coverageTone(item.coverage_severity)}>
                      {coverageLabel(item.coverage_state)}
                    </span>
                    <small>
                      {item.pre_inbound_shortfall_units > 0
                        ? fmt(item.pre_inbound_shortfall_units) + ' units short before inbound'
                        : item.projected_shortfall_units > 0
                          ? fmt(item.projected_shortfall_units) + ' units final shortfall'
                          : 'No projected shortfall'}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {listLoading && <div className="panel-empty">Loading inventory queue...</div>}
          {!listLoading && list && list.items.length === 0 && (
            <div className="panel-empty healthy-empty">
              {search
                ? 'No stock items match this search and filter.'
                : filter === 'out_of_stock'
                  ? 'No out-of-stock items in the current inventory state.'
                  : filter === 'negative'
                    ? 'No negative-stock exceptions in the current inventory state.'
                    : filter === 'reorder'
                      ? 'No items are currently at or below the source reorder level.'
                      : filter === 'risk'
                        ? 'No supply-risk items in the current coverage projection.'
                        : 'No inventory records for this filter.'}
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
          className="inventory-record-drawer"
          kicker="Stock-item record"
          title={selected ? selected.stock_item_name : 'Loading...'}
          loading={detailLoading && !selected}
          onClose={() => {
            setDetail(null)
            setWorkbench(null)
          }}
          status={selected ? (
            <span className={'status-chip ' + coverageTone(selected.coverage_severity)}>
              {coverageLabel(selected.coverage_state)}
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
                <div><span>Stock item ID</span><strong>#{selected.stock_item_id}</strong></div>
                <div><span>Quantity on hand</span><strong>{fmt(selected.quantity_on_hand)}</strong></div>
                <div><span>Source stock state</span><strong>{labelForState(selected.stock_state)}</strong></div>
                <div><span>Source reorder level</span><strong>{fmt(selected.reorder_level)}</strong></div>
                <div>
                  <span>Below trigger by</span>
                  <strong>{selected.below_reorder_by > 0 ? fmt(selected.below_reorder_by) + ' units' : '-'}</strong>
                </div>
                <div><span>Typical order quantity</span><strong>{fmt(selected.typical_order_quantity)}</strong></div>
                <div><span>Last stocktake quantity</span><strong>{fmt(selected.last_stocktake_quantity)}</strong></div>
                <div>
                  <span>Change since stocktake</span>
                  <strong>
                    {(selected.stocktake_delta > 0 ? '+' : '') + fmt(selected.stocktake_delta)}
                  </strong>
                </div>
                <div><span>Last source update</span><strong>{fmtTs(selected.last_edited_when)}</strong></div>
              </div>

              <div className="record-detail-note">
                {selected.stock_state === 'negative'
                  ? 'Quantity on hand is below zero. This is an invalid inventory state that requires correction or investigation.'
                  : selected.stock_state === 'out_of_stock'
                    ? 'Quantity on hand is zero and the item has reached its configured replenishment trigger.'
                    : selected.stock_state === 'reorder'
                      ? 'Quantity on hand is at or below the source-configured reorder level.'
                      : 'Quantity on hand is above the source-configured reorder level.'}
              </div>
            </>
          )}
        </RecordDetailDrawer>
      )}
    </div>
  )
}
