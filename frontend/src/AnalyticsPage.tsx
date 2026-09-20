import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CircleDollarSign,
  Minus,
  PackageCheck,
  TrendingUp,
  X,
} from 'lucide-react'
import {
  fetchAnalyticsDrilldown,
  fetchAnalyticsOverview,
  type AnalyticsDrilldown,
  type AnalyticsDrilldownRow,
  type AnalyticsOverview,
} from './api'

const nf = new Intl.NumberFormat('en-US')
const money = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const compactMoney = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 1,
})
const fmt = (value: number | undefined) => (value === undefined ? '—' : nf.format(value))
const fmtMoney = (value: number | undefined) => (value === undefined ? '—' : money.format(value))

type AnalyticsPeriod = 30 | 90 | 365
type DetailSelection =
  | { kind: 'revenue' | 'profit' | 'orders' | 'receipt' }
  | { kind: 'customer' | 'product'; entityId: number; rank?: number }

const periods: Array<{ value: AnalyticsPeriod; label: string }> = [
  { value: 30, label: '30D' },
  { value: 90, label: '90D' },
  { value: 365, label: '365D' },
]

const analyticsOverviewCache = new Map<AnalyticsPeriod, AnalyticsOverview>()

const analyticsDrilldownCache = new Map<string, AnalyticsDrilldown>()

const analyticsDrilldownKey = (
  kind: AnalyticsDrilldown['kind'],
  period: AnalyticsPeriod,
  entityId?: number,
) => `${kind}|${period}|${entityId ?? 'all'}`

function fmtDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtTimestamp(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function periodLabel(days: AnalyticsPeriod) {
  return `${days}D`
}

function periodRange(period: { start_date: string | null; end_date: string | null }) {
  return `${fmtDate(period.start_date)} – ${fmtDate(period.end_date)}`
}

function trendBucketLabel(
  value: string,
  granularity: AnalyticsOverview['trend_granularity'],
) {
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return granularity === 'month'
    ? date.toLocaleDateString([], { month: 'short' })
    : date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function Delta({
  value,
  suffix = '%',
}: {
  value: number | null | undefined
  suffix?: string
}) {
  if (value === null || value === undefined) {
    return <span className="analytics-delta neutral"><Minus size={12} />No prior comparison</span>
  }
  const tone = value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral'
  return (
    <span className={'analytics-delta ' + tone}>
      {value > 0 ? <ArrowUpRight size={12} /> : value < 0 ? <ArrowDownRight size={12} /> : <Minus size={12} />}
      {value > 0 ? '+' : ''}{value.toFixed(2)}{suffix}
    </span>
  )
}

function TrendChart({
  rows,
  granularity,
}: {
  rows: AnalyticsOverview['trend']
  granularity: AnalyticsOverview['trend_granularity']
}) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const width = 920
  const height = 226
  const left = 58
  const right = 12
  const top = 14
  const bottom = 34
  const plotWidth = width - left - right
  const plotHeight = height - top - bottom
  const maxValue = Math.max(1, ...rows.flatMap((row) => [row.revenue, row.profit]))

  const points = (key: 'revenue' | 'profit') =>
    rows.map((row, index) => {
      const x = left + (index / Math.max(1, rows.length - 1)) * plotWidth
      const y = top + (1 - row[key] / maxValue) * plotHeight
      return { x, y, row }
    })

  const pathFrom = (items: ReturnType<typeof points>) =>
    items.map((point, index) =>
      `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`
    ).join(' ')

  const revenuePoints = points('revenue')
  const profitPoints = points('profit')
  const hasLeadingPartial = Boolean(rows.length > 1 && rows[0]?.is_partial)
  const hasTrailingPartial = Boolean(rows.length > 1 && rows.at(-1)?.is_partial)
  const completeStart = hasLeadingPartial ? 1 : 0
  const completeEnd = hasTrailingPartial ? rows.length - 1 : rows.length
  const revenueComplete = revenuePoints.slice(completeStart, completeEnd)
  const profitComplete = profitPoints.slice(completeStart, completeEnd)
  const revenueLeadingPartial = hasLeadingPartial ? revenuePoints.slice(0, 2) : []
  const profitLeadingPartial = hasLeadingPartial ? profitPoints.slice(0, 2) : []
  const revenueTrailingPartial = hasTrailingPartial ? revenuePoints.slice(-2) : []
  const profitTrailingPartial = hasTrailingPartial ? profitPoints.slice(-2) : []
  const labelEvery = rows.length > 20 ? 5 : rows.length > 14 ? 2 : 1
  const hoveredRow = hoverIndex === null ? null : rows[hoverIndex] ?? null
  const hoveredPoint = hoverIndex === null ? null : revenuePoints[hoverIndex] ?? null
  const hoveredMargin =
    hoveredRow && hoveredRow.revenue > 0
      ? (100 * hoveredRow.profit) / hoveredRow.revenue
      : null
  const hoverLeftPct = hoveredPoint ? (hoveredPoint.x / width) * 100 : 50
  const hoverAlign =
    hoverLeftPct < 20 ? 'left'
      : hoverLeftPct > 80 ? 'right'
        : 'center'

  return (
    <div className="analytics-trend-chart" onMouseLeave={() => setHoverIndex(null)}>
      <div className="analytics-chart-legend">
        <span><i className="analytics-legend-line revenue" />Revenue</span>
        <span><i className="analytics-legend-line profit" />Profit</span>
        {(hasLeadingPartial || hasTrailingPartial) && (
          <span className="analytics-partial-legend">Edge bucket partial</span>
        )}
      </div>

      <svg
        className="analytics-trend-svg"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Revenue and profit trend"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = top + (1 - ratio) * plotHeight
          return (
            <g key={ratio}>
              <line className="analytics-grid-line" x1={left} y1={y} x2={width - right} y2={y} />
              <text className="analytics-y-axis-label" x={left - 8} y={y + 3} textAnchor="end">
                {ratio === 0 ? '0' : compactMoney.format(maxValue * ratio)}
              </text>
            </g>
          )
        })}

        {hasLeadingPartial && revenuePoints[0] && (
          <rect
            className="analytics-partial-zone"
            x={left}
            y={top}
            width={plotWidth / Math.max(1, rows.length - 1) / 2}
            height={plotHeight}
          />
        )}
        {hasTrailingPartial && revenuePoints.at(-1) && (
          <rect
            className="analytics-partial-zone"
            x={Math.max(
              left,
              revenuePoints.at(-1)!.x -
                plotWidth / Math.max(1, rows.length - 1) / 2,
            )}
            y={top}
            width={plotWidth / Math.max(1, rows.length - 1) / 2}
            height={plotHeight}
          />
        )}

        {revenueComplete.length > 1 && (
          <path className="analytics-trend-line revenue" d={pathFrom(revenueComplete)} />
        )}
        {profitComplete.length > 1 && (
          <path className="analytics-trend-line profit" d={pathFrom(profitComplete)} />
        )}
        {hasLeadingPartial && (
          <>
            <path className="analytics-trend-line revenue partial-segment" d={pathFrom(revenueLeadingPartial)} />
            <path className="analytics-trend-line profit partial-segment" d={pathFrom(profitLeadingPartial)} />
          </>
        )}
        {hasTrailingPartial && (
          <>
            <path className="analytics-trend-line revenue partial-segment" d={pathFrom(revenueTrailingPartial)} />
            <path className="analytics-trend-line profit partial-segment" d={pathFrom(profitTrailingPartial)} />
          </>
        )}

        {revenuePoints.map((point, index) => (
          <circle
            key={'r' + index}
            className={'analytics-trend-dot revenue ' + (point.row.is_partial ? 'partial' : '')}
            cx={point.x}
            cy={point.y}
            r={point.row.is_partial ? 4.5 : 3}
          />
        ))}
        {profitPoints.map((point, index) => (
          <circle
            key={'p' + index}
            className={'analytics-trend-dot profit ' + (point.row.is_partial ? 'partial' : '')}
            cx={point.x}
            cy={point.y}
            r={point.row.is_partial ? 4 : 2.5}
          />
        ))}

        {hoveredPoint && (
          <line
            className="analytics-hover-guide"
            x1={hoveredPoint.x}
            y1={top}
            x2={hoveredPoint.x}
            y2={top + plotHeight}
          />
        )}

        {rows.map((row, index) => {
          const x = left + (index / Math.max(1, rows.length - 1)) * plotWidth
          const step = plotWidth / Math.max(1, rows.length - 1)
          const hitX = index === 0 ? left : x - step / 2
          const hitWidth =
            index === 0 || index === rows.length - 1 ? step / 2 : step
          return (
            <rect
              key={'hit-' + row.bucket_start}
              className="analytics-trend-hit"
              x={hitX}
              y={top}
              width={Math.max(8, hitWidth)}
              height={plotHeight}
              onMouseEnter={() => setHoverIndex(index)}
            />
          )
        })}

        {rows.map((row, index) => {
          if (index !== 0 && index !== rows.length - 1 && index % labelEvery !== 0) return null
          const x = left + (index / Math.max(1, rows.length - 1)) * plotWidth
          return (
            <text key={row.bucket_start} className="analytics-axis-label" x={x} y={height - 8} textAnchor="middle">
              {trendBucketLabel(row.bucket_start, granularity)}
            </text>
          )
        })}
      </svg>

      {hoveredRow && hoveredPoint && (
        <div
          className={'analytics-trend-tooltip ' + hoverAlign}
          style={{ left: `${hoverLeftPct}%` }}
          role="status"
        >
          <div className="analytics-trend-tooltip-head">
            <strong>{trendBucketLabel(hoveredRow.bucket_start, granularity)}</strong>
            {hoveredRow.is_partial && <span>Partial</span>}
          </div>
          <dl>
            <div><dt>Revenue</dt><dd>{fmtMoney(hoveredRow.revenue)}</dd></div>
            <div><dt>Profit</dt><dd>{fmtMoney(hoveredRow.profit)}</dd></div>
            <div><dt>Margin</dt><dd>{hoveredMargin === null ? '—' : `${hoveredMargin.toFixed(2)}%`}</dd></div>
            <div><dt>Invoices</dt><dd>{fmt(hoveredRow.invoices)}</dd></div>
          </dl>
        </div>
      )}
    </div>
  )
}

function DrawerMetric({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub?: ReactNode
}) {
  return (
    <div className="analytics-detail-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {sub && <small>{sub}</small>}
    </div>
  )
}

function drilldownMetric(detail: AnalyticsDrilldown) {
  if (detail.kind === 'profit') return { key: 'profit', label: 'Profit' }
  if (detail.kind === 'orders') return { key: 'orders', label: 'Orders' }
  if (detail.kind === 'receipt') return { key: 'receipt_rate_pct', label: 'Receipt completion' }
  return { key: 'revenue', label: 'Revenue' }
}

function DrilldownTrend({ detail }: { detail: AnalyticsDrilldown }) {
  const metric = drilldownMetric(detail)
  const values = detail.trend.map((row) => Number(row[metric.key as keyof typeof row] ?? 0))
  if (values.length < 2) return <div className="panel-empty">Not enough trend history for this selection.</div>

  const width = 380
  const height = 112
  const padX = 8
  const padY = 8
  const max = Math.max(1, ...values)
  const min = Math.min(...values)
  const span = Math.max(1, max - min)
  const points = values.map((value, index) => {
    const x = padX + (index / Math.max(1, values.length - 1)) * (width - padX * 2)
    const y = padY + ((max - value) / span) * (height - padY * 2)
    return { x, y, value }
  })
  const path = points.map((point, index) =>
    `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`
  ).join(' ')

  const formatValue = (value: number) =>
    metric.key === 'revenue' || metric.key === 'profit'
      ? compactMoney.format(value)
      : metric.key === 'receipt_rate_pct'
        ? `${value.toFixed(1)}%`
        : nf.format(Math.round(value))

  return (
    <div className="analytics-drilldown-trend">
      <div className="analytics-drilldown-trend-head">
        <span>{metric.label} trend</span>
        <strong>{formatValue(values.at(-1) ?? 0)}</strong>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <path d={path} className="analytics-drilldown-line" />
        {points.map((point, index) => (
          <circle key={index} cx={point.x} cy={point.y} r="2.5" className="analytics-drilldown-dot" />
        ))}
      </svg>
      <div className="analytics-drilldown-trend-foot">
        <span>{trendBucketLabel(detail.trend[0].bucket_start, detail.trend_granularity)}</span>
        <span>{trendBucketLabel(detail.trend.at(-1)?.bucket_start ?? '', detail.trend_granularity)}</span>
      </div>
    </div>
  )
}

function summaryCards(detail: AnalyticsDrilldown) {
  const s = detail.summary

  if (detail.kind === 'receipt') {
    return (
      <>
        <DrawerMetric label="Completion" value={`${(s.receipt_rate_pct ?? 0).toFixed(2)}%`} sub={<Delta value={s.receipt_rate_change_pp} suffix=" pp" />} />
        <DrawerMetric label="Outstanding" value={fmt(s.outstanding_outers)} sub="outers not yet received" />
        <DrawerMetric label="Purchase orders" value={fmt(s.purchase_orders)} />
      </>
    )
  }

  if (detail.kind === 'profit') {
    return (
      <>
        <DrawerMetric label="Profit" value={fmtMoney(s.profit)} sub={<Delta value={s.profit_change_pct} />} />
        <DrawerMetric label="Margin" value={`${(s.margin_pct ?? 0).toFixed(2)}%`} sub={`${(s.margin_change_pp ?? 0) >= 0 ? '+' : ''}${(s.margin_change_pp ?? 0).toFixed(2)} pp vs prior`} />
        <DrawerMetric label="Profit / order" value={fmtMoney(s.orders ? s.profit / s.orders : 0)} />
      </>
    )
  }

  if (detail.kind === 'orders') {
    return (
      <>
        <DrawerMetric label="Orders" value={fmt(s.orders)} sub={<Delta value={s.orders_change_pct} />} />
        <DrawerMetric label="Units / order" value={(s.avg_units_per_order ?? 0).toFixed(2)} />
        <DrawerMetric label="Revenue / order" value={fmtMoney(s.avg_revenue_per_order)} />
      </>
    )
  }

  if (detail.kind === 'customer') {
    return (
      <>
        <DrawerMetric label="Revenue" value={fmtMoney(s.revenue)} sub={<Delta value={s.revenue_change_pct} />} />
        <DrawerMetric label="Profit" value={fmtMoney(s.profit)} sub={<Delta value={s.profit_change_pct} />} />
        <DrawerMetric label="Orders" value={fmt(s.orders)} sub={<Delta value={s.orders_change_pct} />} />
      </>
    )
  }

  if (detail.kind === 'product') {
    return (
      <>
        <DrawerMetric label="Revenue" value={fmtMoney(s.revenue)} sub={<Delta value={s.revenue_change_pct} />} />
        <DrawerMetric label="Profit" value={fmtMoney(s.profit)} sub={<Delta value={s.profit_change_pct} />} />
        <DrawerMetric label="Units" value={fmt(s.units)} sub={<Delta value={s.units_change_pct} />} />
        <DrawerMetric label="Customers" value={fmt(s.customers)} />
      </>
    )
  }

  return (
    <>
      <DrawerMetric label="Revenue" value={fmtMoney(s.revenue)} sub={<Delta value={s.revenue_change_pct} />} />
      <DrawerMetric label="Revenue / order" value={fmtMoney(s.avg_revenue_per_order)} />
      <DrawerMetric label="Orders" value={fmt(s.orders)} />
    </>
  )
}

function CurrentContext({ detail }: { detail: AnalyticsDrilldown }) {
  const s = detail.summary
  if (detail.kind === 'receipt') return null

  const rows: Array<[string, string]> =
    detail.kind === 'revenue'
      ? [
          ['Profit', fmtMoney(s.profit)],
          ['Margin', `${(s.margin_pct ?? 0).toFixed(2)}%`],
          ['Invoices', fmt(s.invoices)],
          ['Units', fmt(s.units)],
          ['Customers', fmt(s.customers)],
        ]
      : detail.kind === 'profit'
        ? [
            ['Revenue', fmtMoney(s.revenue)],
            ['Orders', fmt(s.orders)],
            ['Invoices', fmt(s.invoices)],
            ['Units', fmt(s.units)],
            ['Customers', fmt(s.customers)],
          ]
        : detail.kind === 'orders'
          ? [
              ['Revenue', fmtMoney(s.revenue)],
              ['Profit', fmtMoney(s.profit)],
              ['Margin', `${(s.margin_pct ?? 0).toFixed(2)}%`],
              ['Invoices', fmt(s.invoices)],
              ['Customers', fmt(s.customers)],
            ]
          : detail.kind === 'customer'
            ? [
                ['Margin', `${(s.margin_pct ?? 0).toFixed(2)}%`],
                ['Invoices', fmt(s.invoices)],
                ['Units', fmt(s.units)],
                ['Revenue / order', fmtMoney(s.avg_revenue_per_order)],
                ['Units / order', (s.avg_units_per_order ?? 0).toFixed(2)],
              ]
            : [
                ['Margin', `${(s.margin_pct ?? 0).toFixed(2)}%`],
                ['Orders', fmt(s.orders)],
                ['Invoices', fmt(s.invoices)],
                ['Revenue / order', fmtMoney(s.avg_revenue_per_order)],
                ['Units / order', (s.avg_units_per_order ?? 0).toFixed(2)],
              ]

  return (
    <dl className="coldchain-detail-list analytics-detail-list">
      {rows.map(([label, value]) => (
        <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
      ))}
    </dl>
  )
}


function PriorPeriodReference({ detail }: { detail: AnalyticsDrilldown }) {
  const s = detail.summary
  if (detail.kind === 'receipt') return null

  return (
    <section className="analytics-prior-reference">
      <div className="analytics-prior-reference-head">
        <span className="panel-kicker">Prior period reference</span>
        <small>{periodRange(detail.prior_period)}</small>
      </div>
      <div className="analytics-prior-reference-grid">
        <div><span>Revenue</span><strong>{fmtMoney(s.prior_revenue)}</strong></div>
        <div><span>Profit</span><strong>{fmtMoney(s.prior_profit)}</strong></div>
        <div><span>Orders</span><strong>{fmt(s.prior_orders)}</strong></div>
        <div><span>Units</span><strong>{fmt(s.prior_units)}</strong></div>
      </div>
    </section>
  )
}

function breakdownValue(
  row: AnalyticsDrilldownRow,
  parentKind: AnalyticsDrilldown['kind'],
) {
  const share =
    row.contribution_pct !== undefined
      ? `${row.contribution_pct.toFixed(1)}% of ${row.contribution_basis ?? 'selected metric'}`
      : null

  if (row.supplier_name) {
    return {
      primary: `${fmt(row.outstanding_outers)} outstanding`,
      secondary: [
        `${(row.completion_pct ?? 0).toFixed(1)}% complete`,
        share,
      ].filter(Boolean).join(' · '),
    }
  }

  if (parentKind === 'profit' && row.profit !== undefined) {
    return {
      primary: `${fmtMoney(row.profit)} profit`,
      secondary: [
        `${fmtMoney(row.revenue)} revenue`,
        share,
      ].filter(Boolean).join(' · '),
    }
  }

  if (parentKind === 'orders' && row.orders !== undefined) {
    return {
      primary: `${fmt(row.orders)} orders`,
      secondary: [
        row.units !== undefined ? `${fmt(row.units)} units` : null,
        share,
      ].filter(Boolean).join(' · '),
    }
  }

  return {
    primary: row.revenue !== undefined
      ? `${fmtMoney(row.revenue)} revenue`
      : `${fmtMoney(row.metric_value)} value`,
    secondary: [
      row.orders !== undefined
        ? `${fmt(row.orders)} orders`
        : row.units !== undefined
          ? `${fmt(row.units)} units`
          : null,
      share,
    ].filter(Boolean).join(' · '),
  }
}

function AnalyticsDetailDrawer({
  detail,
  loading,
  error,
  selection,
  onClose,
  onSelectEntity,
  onRetry,
}: {
  detail: AnalyticsDrilldown | null
  loading: boolean
  error: string | null
  selection: DetailSelection
  onClose: () => void
  onSelectEntity: (kind: 'customer' | 'product', entityId: number, rank?: number) => void
  onRetry: () => void
}) {
  const fallbackTitle =
    selection.kind === 'customer' ? 'Customer analysis'
      : selection.kind === 'product' ? 'Product analysis'
        : selection.kind === 'receipt' ? 'Receipt completion'
          : selection.kind.charAt(0).toUpperCase() + selection.kind.slice(1)

  return (
    <>
      <button className="coldchain-drawer-backdrop" aria-label="Close analytics detail" onClick={onClose} />
      <aside className="coldchain-drawer analytics-detail-drawer" aria-label="Analytics drill-down">
        <div className="coldchain-drawer-header">
          <div>
            <span className="panel-kicker">
              Analytics drill-down{selection.rank ? ' · rank ' + selection.rank : ''}
            </span>
            <h3>{detail?.title ?? fallbackTitle}</h3>
            <small>
              {detail
                ? `${periodRange(detail.current_period)} · compared with ${periodRange(detail.prior_period)}`
                : 'Loading warehouse detail…'}
            </small>
          </div>
          <button className="icon-button" onClick={onClose}><X size={17} /></button>
        </div>

        <div className="coldchain-drawer-body analytics-drilldown-body">
          {loading && !detail && (
            <div className="panel-empty">Loading analytical detail...</div>
          )}
          {error && (
            <div className="analytics-drilldown-error">
              <div>
                <strong>Analytical detail unavailable</strong>
                <span>{error}</span>
              </div>
              <button type="button" className="panel-action" onClick={onRetry}>
                Retry
              </button>
            </div>
          )}

          {detail && (
            <>
              <section className={'analytics-detail-metrics ' + (detail.kind === 'product' ? 'four-up' : '')}>
                {summaryCards(detail)}
              </section>

              <div className={'analytics-detail-context-grid ' + (detail.kind === 'receipt' ? 'single' : '')}>
                <section className="coldchain-detail-section">
                  <div className="coldchain-detail-section-head">
                    <div>
                      <span className="panel-kicker">Movement</span>
                      <h4>Period movement</h4>
                    </div>
                  </div>
                  <DrilldownTrend detail={detail} />
                </section>

                {detail.kind !== 'receipt' && (
                  <section className="coldchain-detail-section">
                    <div className="coldchain-detail-section-head">
                      <div>
                        <span className="panel-kicker">Current period</span>
                        <h4>Commercial context</h4>
                      </div>
                    </div>
                    <CurrentContext detail={detail} />
                  </section>
                )}
              </div>

              <PriorPeriodReference detail={detail} />

              {detail.breakdowns.map((section) => (
                <section className="coldchain-detail-section" key={section.title}>
                  <div className="coldchain-detail-section-head">
                    <div>
                      <span className="panel-kicker">
                        {section.entity_kind === 'customer' || section.entity_kind === 'product'
                          ? 'Linked contribution'
                          : 'Drivers'}
                      </span>
                      <h4>{section.title}</h4>
                    </div>
                  </div>

                  <div className="analytics-driver-list">
                    {section.rows.map((row, index) => {
                      const label = row.label ?? row.supplier_name ?? `Record ${row.id ?? row.supplier_id ?? index + 1}`
                      const values = breakdownValue(row, detail.kind)
                      const canOpen = section.entity_kind === 'customer' || section.entity_kind === 'product'
                      const id = row.id

                      return (
                        <button
                          key={`${section.entity_kind}-${id ?? row.supplier_id ?? index}`}
                          type="button"
                          className={'analytics-driver-row ' + (canOpen ? 'clickable' : '')}
                          disabled={!canOpen || id === undefined}
                          onClick={() => {
                            if (canOpen && id !== undefined) {
                              onSelectEntity(section.entity_kind, id, index + 1)
                            }
                          }}
                        >
                          <span className="analytics-rank">{index + 1}</span>
                          <div>
                            <strong>{label}</strong>
                            {values.secondary && <small>{values.secondary}</small>}
                          </div>
                          <span className="analytics-driver-value">{values.primary}</span>
                        </button>
                      )
                    })}
                  </div>
                </section>
              ))}

              <div className="analytics-detail-source">
                This view is calculated from the analytical warehouse, complete through {fmtDate(detail.current_period.end_date)}.
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  )
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsOverview | null>(
    () => analyticsOverviewCache.get(30) ?? null,
  )
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [period, setPeriod] = useState<AnalyticsPeriod>(30)
  const [selection, setSelection] = useState<DetailSelection | null>(null)
  const [drilldown, setDrilldown] = useState<AnalyticsDrilldown | null>(null)
  const [drilldownLoading, setDrilldownLoading] = useState(false)
  const [drilldownError, setDrilldownError] = useState<string | null>(null)
  const drilldownRequestSeq = useRef(0)

  const load = async (showBusy = false) => {
    const cached = analyticsOverviewCache.get(period) ?? null
    if (cached) setData(cached)
    else setData(null)
    if (showBusy) setRefreshing(true)
    try {
      const next = await fetchAnalyticsOverview(period)
      analyticsOverviewCache.set(period, next)
      setData(next)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load analytics data')
    } finally {
      if (showBusy) setRefreshing(false)
    }
  }

  useEffect(() => {
    setSelection(null)
    setDrilldown(null)
    void load(false)
  }, [period])

  const loadDrilldown = async (
    currentSelection: DetailSelection,
    currentPeriod: AnalyticsPeriod,
  ) => {
    const requestId = ++drilldownRequestSeq.current
    const entityId =
      currentSelection.kind === 'customer' || currentSelection.kind === 'product'
        ? currentSelection.entityId
        : undefined
    const key = analyticsDrilldownKey(currentSelection.kind, currentPeriod, entityId)
    const cached = analyticsDrilldownCache.get(key) ?? null

    setDrilldown(cached)
    setDrilldownLoading(true)
    setDrilldownError(null)
    try {
      const next = await fetchAnalyticsDrilldown(
        currentSelection.kind,
        currentPeriod,
        entityId,
      )
      analyticsDrilldownCache.set(key, next)
      if (requestId !== drilldownRequestSeq.current) return
      setDrilldown(next)
    } catch (err) {
      if (requestId !== drilldownRequestSeq.current) return
      setDrilldownError(
        err instanceof Error ? err.message : 'Unable to load analytics drill-down',
      )
    } finally {
      if (requestId === drilldownRequestSeq.current) {
        setDrilldownLoading(false)
      }
    }
  }

  useEffect(() => {
    if (!selection) {
      setDrilldown(null)
      setDrilldownError(null)
      return
    }
    void loadDrilldown(selection, period)
  }, [selection, period])

  const customers = data?.customer_concentration.customers ?? []
  const edgePartial = Boolean(
    data?.trend[0]?.is_partial || data?.trend.at(-1)?.is_partial,
  )
  const granularityLabel =
    data?.trend_granularity === 'day'
      ? 'Daily'
      : data?.trend_granularity === 'week'
        ? 'Weekly'
        : 'Monthly'

  return (
    <div className="fulfillment-page analytics-v2">
      <section className="overview-heading">
        <div>
          <div className="overview-title-row">
            <h2>Analytics</h2>
            <span className="preview-pill">Warehouse analytics</span>
          </div>
          <p>
            Compare commercial performance, customer concentration, product contribution,
            and procurement completion from the analytical warehouse.
          </p>
        </div>

        <div className="analytics-heading-actions">
          <div className="analytics-period-switch" aria-label="Analytics period">
            {periods.map((item) => (
              <button
                key={item.value}
                className={period === item.value ? 'active' : ''}
                onClick={() => setPeriod(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="overview-meta">
            <span><span className="live-dot" />{error ? 'Analytics unavailable' : data ? 'Warehouse connected' : 'Connecting'}</span>
            <span>Complete through {fmtDate(data?.as_of_date)} · refreshed {fmtTimestamp(data?.generated_at)}</span>
          </div>
        </div>
      </section>

      {error && <div className="overview-error">Analytics serving error: {error}</div>}

      <section className="kpi-grid fulfillment-kpi-grid analytics-kpi-grid">
        <button className="kpi-card analytics-clickable-kpi" onClick={() => setSelection({ kind: 'revenue' })}>
          <div className="kpi-icon tone-accent"><CircleDollarSign size={20} /></div>
          <div className="kpi-copy">
            <span>Revenue</span>
            <strong>{fmtMoney(data?.kpis.revenue)}</strong>
            <small><Delta value={data?.kpis.revenue_change_pct} /> vs prior {periodLabel(period)}</small>
          </div>
        </button>

        <button className="kpi-card analytics-clickable-kpi" onClick={() => setSelection({ kind: 'profit' })}>
          <div className="kpi-icon tone-cool"><TrendingUp size={20} /></div>
          <div className="kpi-copy">
            <span>Profit</span>
            <strong>{fmtMoney(data?.kpis.profit)}</strong>
            <small><Delta value={data?.kpis.profit_change_pct} /> · {data ? `${data.kpis.margin_pct.toFixed(2)}% margin` : 'margin'}</small>
          </div>
        </button>

        <button className="kpi-card analytics-clickable-kpi" onClick={() => setSelection({ kind: 'orders' })}>
          <div className="kpi-icon tone-cool"><BarChart3 size={20} /></div>
          <div className="kpi-copy">
            <span>Orders</span>
            <strong>{fmt(data?.kpis.orders)}</strong>
            <small><Delta value={data?.kpis.orders_change_pct} /> · {fmt(data?.kpis.units)} units</small>
          </div>
        </button>

        <button className="kpi-card analytics-clickable-kpi" onClick={() => setSelection({ kind: 'receipt' })}>
          <div className="kpi-icon tone-warning"><PackageCheck size={20} /></div>
          <div className="kpi-copy">
            <span>Receipt completion</span>
            <strong>{data ? `${data.procurement.receipt_rate_pct.toFixed(2)}%` : '—'}</strong>
            <small><Delta value={data?.procurement.receipt_rate_change_pp} suffix=" pp" /> · {fmt(data?.procurement.po_count)} POs</small>
          </div>
        </button>
      </section>

      <section className="fulfillment-mid-grid analytics-mid-grid">
        <article className="panel-card analytics-trend-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">{periodLabel(period)} performance trend</span>
              <h3>Revenue and profit movement</h3>
            </div>
            <span className="panel-muted">
              {granularityLabel}
              {edgePartial ? ' · edge buckets may be partial' : ''}
            </span>
          </div>

          <TrendChart rows={data?.trend ?? []} granularity={data?.trend_granularity ?? 'day'} />
          {!data && !error && <div className="panel-empty">Loading commercial trend…</div>}
        </article>

        <article className="panel-card analytics-customer-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Customer concentration · {periodLabel(period)}</span>
              <h3>Top 5 customers by revenue</h3>
            </div>
            <div className="analytics-concentration-stat">
              <span>Top 5 share</span>
              <strong>{data ? `${data.customer_concentration.top5_revenue_share_pct.toFixed(2)}%` : '—'}</strong>
            </div>
          </div>

          {data && (
            <div className="analytics-concentration-split">
              <div
                className="analytics-concentration-top5"
                style={{ width: `${Math.max(3, data.customer_concentration.top5_revenue_share_pct)}%` }}
                title={`Top 5 customers: ${data.customer_concentration.top5_revenue_share_pct.toFixed(2)}% of revenue`}
              />
              <div
                className="analytics-concentration-others"
                style={{ width: `${Math.max(0, 100 - data.customer_concentration.top5_revenue_share_pct)}%` }}
                title={`Other customers: ${(100 - data.customer_concentration.top5_revenue_share_pct).toFixed(2)}% of revenue`}
              />
            </div>
          )}

          {data && (
            <div className="analytics-concentration-legend">
              <span><i className="top5" />Top 5 {data.customer_concentration.top5_revenue_share_pct.toFixed(2)}%</span>
              <span><i className="others" />Others {(100 - data.customer_concentration.top5_revenue_share_pct).toFixed(2)}%</span>
            </div>
          )}

          <div className="analytics-customer-list">
            {customers.slice(0, 5).map((customer, index) => (
              <button
                type="button"
                className="analytics-customer-row analytics-clickable-row"
                key={customer.customer_id}
                onClick={() => setSelection({ kind: 'customer', entityId: customer.customer_id, rank: index + 1 })}
              >
                <span className="analytics-rank">{index + 1}</span>
                <div className="analytics-customer-main">
                  <div className="analytics-customer-label">
                    <span>{customer.customer_name}</span>
                    <strong>{customer.revenue_share_pct.toFixed(2)}%</strong>
                  </div>
                  <small>{fmtMoney(customer.revenue)} revenue · {customer.invoices} invoices</small>
                </div>
              </button>
            ))}
          </div>

          {data && <div className="analytics-concentration-note">Click a customer to see its own trend and product mix.</div>}
        </article>
      </section>

      <section className="panel-card fulfillment-table-card analytics-product-card">
        <div className="panel-header fulfillment-queue-header">
          <div>
            <span className="panel-kicker">Product contribution · {periodLabel(period)}</span>
            <h3>Top products by revenue contribution</h3>
            <p className="analytics-product-hint">
              Select a product row to inspect its trend, commercial contribution, and customer mix.
            </p>
          </div>

          <div className="analytics-product-header-actions">
            <div className="analytics-concentration-stat">
              <span>Top 8 share</span>
              <strong>{data ? `${data.top_product_revenue_share_pct.toFixed(2)}%` : '—'}</strong>
            </div>
            <button className="panel-action" onClick={() => void load(true)} disabled={refreshing}>
              {refreshing ? 'Refreshing…' : 'Refresh warehouse view'}
            </button>
          </div>
        </div>

        <div className="fulfillment-table-wrap">
          <table className="fulfillment-table analytics-product-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Revenue</th>
                <th>Revenue share</th>
                <th>Profit</th>
                <th>Units</th>
                <th>Margin</th>
              </tr>
            </thead>
            <tbody>
              {(data?.top_products ?? []).map((product, index) => {
                const margin = product.revenue > 0 ? (100 * product.profit) / product.revenue : 0
                return (
                  <tr
                    key={product.stock_item_id}
                    className="analytics-clickable-product-row"
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelection({ kind: 'product', entityId: product.stock_item_id, rank: index + 1 })}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        setSelection({ kind: 'product', entityId: product.stock_item_id, rank: index + 1 })
                      }
                    }}
                  >
                    <td><strong>{product.stock_item_name}</strong><small>Stock item {product.stock_item_id}</small></td>
                    <td>{fmtMoney(product.revenue)}</td>
                    <td><strong>{product.revenue_share_pct.toFixed(2)}%</strong></td>
                    <td>{fmtMoney(product.profit)}</td>
                    <td>{fmt(product.units)}</td>
                    <td>{margin.toFixed(1)}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {!data && !error && <div className="panel-empty">Loading product analytics…</div>}
        </div>
      </section>

      {selection && (
        <AnalyticsDetailDrawer
          detail={drilldown}
          loading={drilldownLoading}
          error={drilldownError}
          selection={selection}
          onClose={() => setSelection(null)}
          onSelectEntity={(kind, entityId, rank) => setSelection({ kind, entityId, rank })}
          onRetry={() => void loadDrilldown(selection, period)}
        />
      )}
    </div>
  )
}
