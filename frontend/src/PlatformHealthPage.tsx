import { useEffect, useMemo, useState } from 'react'
import {
  Database,
  HeartPulse,
  RefreshCw,
  ShieldCheck,
  Waves,
} from 'lucide-react'
import {
  fetchApiHealth,
  fetchPlatformHealthOverview,
  type ApiHealth,
  type PlatformHealthOverview,
  type SseConnectionState,
} from './api'

const nf = new Intl.NumberFormat('en-US')
const fmt = (value: number | undefined) => (value === undefined ? '—' : nf.format(value))

function fmtTimestamp(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function fmtLag(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  if (value < 1) return `${Math.round(value * 1000)} ms`
  if (value < 60) return `${value.toFixed(value < 10 ? 2 : 1)} sec`
  return `${(value / 60).toFixed(1)} min`
}

type CheckTone = 'success' | 'warning' | 'critical'

type HealthCheck = {
  label:string
  status:string
  tone:CheckTone
  evidence:string
  observed:string
}

type PlatformHealthPageProps = {
  sseState: SseConnectionState
  refreshSignal: number
}

export default function PlatformHealthPage({ sseState, refreshSignal }: PlatformHealthPageProps) {
  const [data, setData] = useState<PlatformHealthOverview | null>(null)
  const [health, setHealth] = useState<ApiHealth | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = async (showBusy = false) => {
    if (showBusy) setRefreshing(true)
    try {
      const [next, apiHealth] = await Promise.all([
        fetchPlatformHealthOverview(),
        fetchApiHealth(),
      ])
      setData(next)
      setHealth(apiHealth)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load platform health')
    } finally {
      if (showBusy) setRefreshing(false)
    }
  }

  useEffect(() => {
    void load(false)
  }, [refreshSignal])

  const qualityStatus = data?.latest_quality.status ?? 'unknown'
  const servingHealthy =
    health?.status === 'ok' &&
    health?.database === 'ok' &&
    health?.sse_listener === 'connected'
  const platformHealthy =
    servingHealthy &&
    data?.watermark_aligned === true &&
    data?.freshness.all_fresh === true &&
    qualityStatus === 'pass' &&
    (data?.realtime.unprocessed ?? 0) === 0 &&
    (data?.alerts.platform_active ?? 0) === 0

  const checks = useMemo<HealthCheck[]>(() => {
    if (!data || !health) return []

    return [
      {
        label:'Serving API',
        status:health.status === 'ok' ? 'Healthy' : 'Check',
        tone:health.status === 'ok' ? 'success' : 'critical',
        evidence:`REST health: ${health.status}`,
        observed:fmtTimestamp(data.generated_at),
      },
      {
        label:'Warehouse connection',
        status:health.database === 'ok' ? 'Connected' : 'Check',
        tone:health.database === 'ok' ? 'success' : 'critical',
        evidence:`Database: ${health.database}`,
        observed:fmtTimestamp(data.generated_at),
      },
      {
        label:'Realtime listener',
        status:health.sse_listener === 'connected' ? 'Connected' : 'Check',
        tone:health.sse_listener === 'connected' ? 'success' : 'critical',
        evidence:`Backend listener ${health.sse_listener} · ${fmt(health.subscribers)} subscriber(s)`,
        observed:fmtTimestamp(data.realtime.latest_event_at),
      },
      {
        label:'Dashboard session',
        status:sseState === 'connected' ? 'Connected' : sseState === 'reconnecting' ? 'Reconnecting' : 'Disconnected',
        tone:sseState === 'connected' ? 'success' : 'warning',
        evidence:'Browser session connectivity only; excluded from platform health state',
        observed:fmtTimestamp(data.generated_at),
      },
      {
        label:'Warehouse watermark',
        status:data.watermark_aligned ? 'Aligned' : 'Mismatch',
        tone:data.watermark_aligned ? 'success' : 'critical',
        evidence:`Pipeline ${fmtTimestamp(data.pipeline_cutoff)} · Source ${fmtTimestamp(data.source_frontier)}`,
        observed:fmtTimestamp(data.pipelines[0]?.updated_at),
      },
      {
        label:'Metadata freshness',
        status:data.freshness.all_fresh ? 'Fresh' : 'Stale',
        tone:data.freshness.all_fresh ? 'success' : 'critical',
        evidence:`Pipeline ${fmtLag((data.freshness.pipeline_age_hours ?? 0) * 3600)} old · frontier ${fmtLag((data.freshness.frontier_age_hours ?? 0) * 3600)} old · quality ${fmtLag((data.freshness.quality_age_hours ?? 0) * 3600)} old · max ${data.freshness.max_age_hours}h`,
        observed:fmtTimestamp(data.generated_at),
      },
      {
        label:'Data quality',
        status:qualityStatus === 'pass' ? 'Pass' : 'Check',
        tone:qualityStatus === 'pass' ? 'success' : 'critical',
        evidence:`${fmt(data.latest_quality.passed_checks)} passed · ${fmt(data.latest_quality.failed_checks)} failed · ${fmt(data.latest_quality.warning_checks)} warning`,
        observed:fmtTimestamp(data.latest_quality.finished_at),
      },
      {
        label:'Realtime event queue',
        status:data.realtime.unprocessed === 0 ? 'Clear' : 'Backlog',
        tone:data.realtime.unprocessed === 0 ? 'success' : 'warning',
        evidence:`${fmt(data.realtime.unprocessed)} pending · avg lag ${fmtLag(data.realtime.avg_processing_lag_seconds)}`,
        observed:fmtTimestamp(data.realtime.latest_processed_at),
      },
      {
        label:'Platform alerts',
        status:data.alerts.platform_active === 0 ? 'Clear' : 'Active',
        tone:data.alerts.platform_critical > 0 ? 'critical' : data.alerts.platform_active > 0 ? 'warning' : 'success',
        evidence:`${fmt(data.alerts.platform_active)} active platform alert(s) · ${fmt(data.alerts.active)} active operational alert(s) overall`,
        observed:fmtTimestamp(data.generated_at),
      },
    ]
  }, [data, health, sseState, qualityStatus])

  return (
    <div className="fulfillment-page platform-health-v2">
      <section className="overview-heading">
        <div>
          <div className="overview-title-row">
            <h2>Platform Health</h2>
            <span className="preview-pill">Live platform telemetry</span>
          </div>
          <p>
            Verify serving health, warehouse alignment, data quality, and realtime processing
            before trusting operational dashboards.
          </p>
        </div>

        <div className="overview-meta">
          <span>
            <span className={`live-dot sse-${sseState}`} />
            {error ? 'Health unavailable' : platformHealthy ? 'Platform healthy' : 'Platform needs attention'}
          </span>
          <span>Refreshed {fmtTimestamp(data?.generated_at)}</span>
        </div>
      </section>

      {error && <div className="overview-error">Platform health serving error: {error}</div>}

      <section className="kpi-grid fulfillment-kpi-grid">
        <article className="kpi-card">
          <div className="kpi-icon tone-accent"><HeartPulse size={20} /></div>
          <div className="kpi-copy">
            <span>Platform state</span>
            <strong>{platformHealthy ? 'Healthy' : 'Watch'}</strong>
            <small>{platformHealthy ? 'All platform checks passing' : 'One or more platform checks need review'}</small>
          </div>
        </article>

        <article className="kpi-card">
          <div className="kpi-icon tone-cool"><Database size={20} /></div>
          <div className="kpi-copy">
            <span>Warehouse sync</span>
            <strong>{data?.watermark_aligned ? 'Aligned' : 'Mismatch'}</strong>
            <small>{data?.freshness.all_fresh ? 'Aligned and fresh' : 'Alignment and freshness check'}</small>
          </div>
        </article>

        <article className="kpi-card">
          <div className="kpi-icon tone-cool"><ShieldCheck size={20} /></div>
          <div className="kpi-copy">
            <span>Quality gate</span>
            <strong>{qualityStatus.toUpperCase()}</strong>
            <small>{fmt(data?.latest_quality.passed_checks)} passed · {fmt(data?.latest_quality.failed_checks)} failed</small>
          </div>
        </article>

        <article className="kpi-card">
          <div className="kpi-icon tone-warning"><Waves size={20} /></div>
          <div className="kpi-copy">
            <span>Realtime queue</span>
            <strong>{fmt(data?.realtime.unprocessed)}</strong>
            <small>pending · avg lag {fmtLag(data?.realtime.avg_processing_lag_seconds)}</small>
          </div>
        </article>
      </section>

      <section className="fulfillment-mid-grid platform-health-mid-grid">
        <article className="panel-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Serving runtime</span>
              <h3>Serving components</h3>
            </div>
            <span className={`status-chip ${servingHealthy ? 'success' : 'warning'}`}>
              {servingHealthy ? 'Operational' : 'Check'}
            </span>
          </div>

          <div className="platform-service-grid">
            <div>
              <span>Realtime API</span>
              <strong>{health?.status === 'ok' ? 'Healthy' : health?.status ?? '—'}</strong>
              <small>REST serving layer</small>
            </div>
            <div>
              <span>Warehouse DB</span>
              <strong>{health?.database === 'ok' ? 'Connected' : health?.database ?? '—'}</strong>
              <small>Serving query connection</small>
            </div>
            <div>
              <span>Backend SSE</span>
              <strong>{health?.sse_listener ?? '—'}</strong>
              <small>Database event listener</small>
            </div>
            <div>
              <span>Dashboard session</span>
              <strong>{sseState}</strong>
              <small>Browser connectivity · excluded from platform health</small>
            </div>
          </div>

          {health?.listener_error && <div className="overview-error">{health.listener_error}</div>}
        </article>

        <article className="panel-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Processing telemetry</span>
              <h3>Realtime processing</h3>
            </div>
            <span className={`status-chip ${(data?.realtime.unprocessed ?? 0) === 0 ? 'success' : 'warning'}`}>
              {(data?.realtime.unprocessed ?? 0) === 0 ? 'Queue clear' : 'Backlog'}
            </span>
          </div>

          <div className="platform-metric-grid">
            <div>
              <span>Events · 24h</span>
              <strong>{fmt(data?.realtime.events_24h)}</strong>
            </div>
            <div>
              <span>Processed · 24h</span>
              <strong>{fmt(data?.realtime.processed_24h)}</strong>
            </div>
            <div>
              <span>Average lag</span>
              <strong>{fmtLag(data?.realtime.avg_processing_lag_seconds)}</strong>
            </div>
            <div>
              <span>Max lag · 24h</span>
              <strong>{fmtLag(data?.realtime.max_processing_lag_seconds)}</strong>
            </div>
          </div>

          <div className="platform-timeline">
            <div>
              <span>Latest event</span>
              <strong>{fmtTimestamp(data?.realtime.latest_event_at)}</strong>
            </div>
            <div>
              <span>Latest processed</span>
              <strong>{fmtTimestamp(data?.realtime.latest_processed_at)}</strong>
            </div>
          </div>
        </article>
      </section>

      <section className="panel-card fulfillment-table-card platform-check-card">
        <div className="panel-header fulfillment-queue-header">
          <div>
            <span className="panel-kicker">Platform checks</span>
            <h3>Platform checks</h3>
          </div>
          <button className="panel-action" onClick={() => void load(true)} disabled={refreshing}>
            <RefreshCw size={13} />
            {refreshing ? 'Refreshing…' : 'Refresh health'}
          </button>
        </div>

        <div className="fulfillment-table-wrap">
          <table className="fulfillment-table platform-check-table">
            <thead>
              <tr>
                <th>Check</th>
                <th>Status</th>
                <th>Evidence</th>
                <th>Last observed</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => (
                <tr key={check.label}>
                  <td>
                    <strong>{check.label}</strong>
                  </td>
                  <td>
                    <span className={`status-chip ${check.tone}`}>
                      {check.status}
                    </span>
                  </td>
                  <td>{check.evidence}</td>
                  <td>{check.observed}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data && !error && <div className="panel-empty">Loading platform health…</div>}
        </div>
      </section>
    </div>
  )
}
