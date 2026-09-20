import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Clock3,
  Minus,
  Radio,
  ShieldCheck,
  Snowflake,
  Thermometer,
  Truck,
  X,
} from 'lucide-react'
import {
  fetchColdChainOverview,
  type ColdChainHistoryPoint,
  type ColdChainOverview,
  type SseConnectionState,
} from './api'

const nf = new Intl.NumberFormat('en-US')
const fmt = (value: number | undefined) =>
  value === undefined ? '-' : nf.format(value)

const fmtTemp = (value: number | null | undefined) =>
  value === null || value === undefined ? '-' : `${value.toFixed(2)} °C`

function fmtTimestamp(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function liveAgeSeconds(recordedWhen: string | null | undefined, nowMs: number) {
  if (!recordedWhen) return null
  const ts = new Date(recordedWhen).getTime()
  if (Number.isNaN(ts)) return null
  return Math.max(0, (nowMs - ts) / 1000)
}

function fmtDuration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return '-'
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} sec`
  const minutes = seconds / 60
  if (minutes < 60) return `${minutes < 10 ? minutes.toFixed(1) : Math.round(minutes)} min`
  const hours = minutes / 60
  if (hours < 24) return `${hours < 10 ? hours.toFixed(1) : Math.round(hours)} hr`
  const days = hours / 24
  return `${days < 10 ? days.toFixed(1) : Math.round(days)} d`
}

function fmtDelta(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)} °C`
}

function sensorLabel(sensor: ColdChainOverview['sensors'][number]) {
  if (sensor.sensor_type === 'vehicle') {
    return `${sensor.vehicle_registration ?? 'Vehicle'} · Sensor ${sensor.sensor_number}`
  }
  return `Cold room · Sensor ${sensor.sensor_number}`
}

function sensorTypeLabel(value: string) {
  return value === 'coldroom' ? 'Cold room' : 'Vehicle'
}

function stateTone(state: ColdChainOverview['sensors'][number]['operational_state']) {
  if (state === 'offline' || state === 'temperature_critical') return 'critical'
  if (state === 'stale' || state === 'temperature_warning') return 'warning'
  if (state === 'healthy') return 'success'
  return 'monitoring'
}

function stateLabel(state: ColdChainOverview['sensors'][number]['operational_state']) {
  if (state === 'temperature_critical') return 'Temp critical'
  if (state === 'temperature_warning') return 'Temp warning'
  if (state === 'offline') return 'Offline'
  if (state === 'stale') return 'Stale'
  if (state === 'healthy') return 'Fresh'
  return 'Unknown'
}

function temperatureLabel(sensor: ColdChainOverview['sensors'][number]) {
  if (!sensor.temperature_thresholds_configured) return 'Not evaluated'
  if (sensor.temperature_state === 'critical') return 'Critical'
  if (sensor.temperature_state === 'warning') return 'Warning'
  if (sensor.temperature_state === 'normal') return 'Within band'
  return 'Not evaluated'
}

function MovementIcon({
  movement,
  size = 15,
}: {
  movement: ColdChainOverview['sensors'][number]['movement']
  size?: number
}) {
  if (movement === 'rising') return <ArrowUpRight size={size} />
  if (movement === 'falling') return <ArrowDownRight size={size} />
  return <Minus size={size} />
}

function Sparkline({
  points,
  width = 136,
  height = 34,
}: {
  points: ColdChainHistoryPoint[]
  width?: number
  height?: number
}) {
  if (points.length < 2) {
    return <div className="coldchain-sparkline-empty">Waiting for movement</div>
  }

  const values = points.map((point) => point.temperature)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(0.1, max - min)
  const pad = 3
  const coordinates = values
    .map((value, index) => {
      const x =
        pad + (index / Math.max(1, values.length - 1)) * (width - pad * 2)
      const y =
        pad + ((max - value) / span) * (height - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg
      className="coldchain-sparkline"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Recent temperature movement"
      preserveAspectRatio="none"
    >
      <polyline points={coordinates} fill="none" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

type ColdChainPageProps = {
  sseState: SseConnectionState
  refreshSignal: number
  initialSensorKey?: string | null
}

type SensorFilter = 'all' | 'attention' | 'fresh' | 'coldroom' | 'vehicle'

const filters: Array<{ value: SensorFilter; label: string }> = [
  { value: 'all', label: 'All sensors' },
  { value: 'attention', label: 'Needs attention' },
  { value: 'fresh', label: 'Fresh' },
  { value: 'coldroom', label: 'Cold room' },
  { value: 'vehicle', label: 'Vehicle' },
]

export default function ColdChainPage({
  sseState,
  refreshSignal,
  initialSensorKey = null,
}: ColdChainPageProps) {
  const [data, setData] = useState<ColdChainOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [filter, setFilter] = useState<SensorFilter>('all')
  const [selectedSensorKey, setSelectedSensorKey] = useState<string | null>(initialSensorKey)
  const [detailSensorKey, setDetailSensorKey] = useState<string | null>(initialSensorKey)
  const [policyOpen, setPolicyOpen] = useState(false)
  const [nowMs, setNowMs] = useState(() => Date.now())

  const changeFilter = (next: SensorFilter) => {
    setSelectedSensorKey(null)
    setDetailSensorKey(null)
    setFilter(next)
  }

  const load = async (showBusy = false) => {
    if (showBusy) setRefreshing(true)
    try {
      const next = await fetchColdChainOverview()
      setData(next)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load cold-chain data')
    } finally {
      if (showBusy) setRefreshing(false)
    }
  }

  useEffect(() => {
    void load(false)
  }, [refreshSignal])

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    setSelectedSensorKey(initialSensorKey)
    setDetailSensorKey(initialSensorKey)
  }, [initialSensorKey])

  const liveSensors = useMemo(
    () =>
      (data?.sensors ?? []).map((sensor) => {
        const age = liveAgeSeconds(sensor.recorded_when, nowMs)
        let freshness = sensor.freshness_state
        if (age !== null) {
          if (age > sensor.offline_after_seconds) freshness = 'offline'
          else if (age > sensor.stale_after_seconds) freshness = 'stale'
          else freshness = 'fresh'
        }

        let operational = sensor.operational_state
        if (freshness === 'offline') operational = 'offline'
        else if (freshness === 'stale') operational = 'stale'
        else if (sensor.temperature_state === 'critical') operational = 'temperature_critical'
        else if (sensor.temperature_state === 'warning') operational = 'temperature_warning'
        else operational = 'healthy'

        return {
          ...sensor,
          age_seconds: age,
          freshness_state: freshness,
          operational_state: operational,
        }
      }),
    [data, nowMs],
  )

  const visibleSensors = useMemo(() => {
    if (selectedSensorKey) {
      return liveSensors.filter((sensor) => sensor.sensor_key === selectedSensorKey)
    }
    if (filter === 'attention') {
      return liveSensors.filter((sensor) => sensor.operational_state !== 'healthy')
    }
    if (filter === 'fresh') {
      return liveSensors.filter((sensor) => sensor.freshness_state === 'fresh')
    }
    if (filter === 'coldroom' || filter === 'vehicle') {
      return liveSensors.filter((sensor) => sensor.sensor_type === filter)
    }
    return liveSensors
  }, [liveSensors, filter, selectedSensorKey])

  const detailSensor =
    liveSensors.find((sensor) => sensor.sensor_key === detailSensorKey) ?? null
  const temperatureConfigured =
    data?.monitoring.temperature_thresholds_configured ?? false
  const totalSensors = liveSensors.length
  const freshSensors = liveSensors.filter((sensor) => sensor.freshness_state === 'fresh').length
  const staleSensors = liveSensors.filter((sensor) => sensor.freshness_state === 'stale').length
  const offlineSensors = liveSensors.filter((sensor) => sensor.freshness_state === 'offline').length
  const attentionSensors = liveSensors.filter((sensor) => sensor.operational_state !== 'healthy').length
  const latestAge = liveAgeSeconds(data?.latest_recorded_when, nowMs)

  const rule = (id: string) => data?.rules.find((item) => item.rule_id === id)
  const ruleBand = (id: string) => {
    const params = rule(id)?.parameters ?? {}
    const low = typeof params.low === 'number' ? params.low : null
    const high = typeof params.high === 'number' ? params.high : null
    return { low, high }
  }
  const warningBand = ruleBand('coldroom.temperature_warning')
  const criticalBand = ruleBand('coldroom.temperature_critical')

  const groupStats = (sensorType: string) => {
    const items = liveSensors.filter((sensor) => sensor.sensor_type === sensorType)
    const ages = items
      .map((sensor) => sensor.age_seconds)
      .filter((value): value is number => value !== null)
    return {
      total: items.length,
      fresh: items.filter((sensor) => sensor.freshness_state === 'fresh').length,
      stale: items.filter((sensor) => sensor.freshness_state === 'stale').length,
      offline: items.filter((sensor) => sensor.freshness_state === 'offline').length,
      latestAge: ages.length ? Math.min(...ages) : null,
    }
  }

  return (
    <div className="fulfillment-page fulfillment-v2 cold-chain-v2">
      <section className="overview-heading">
        <div>
          <div className="overview-title-row">
            <h2>Cold Chain control</h2>
            <span className={'preview-pill sse-pill ' + sseState}>Realtime channel</span>
          </div>
          <p>
            Verify that sensor feeds are alive, watch actual temperature movement,
            and work exceptions before trusting the cold-chain condition.
          </p>
        </div>

        <div className="overview-meta">
          <span>
            <span className={'live-dot sse-' + sseState} />
            Realtime {sseState}
          </span>
          <span>Latest telemetry {fmtDuration(latestAge)} ago</span>
        </div>
      </section>

      {error && <div className="overview-error">Cold-chain serving error: {error}</div>}

      <section className="kpi-grid fulfillment-kpi-grid">
        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('fresh')}>
          <div className="kpi-icon tone-cool"><Radio size={20} /></div>
          <div className="kpi-copy">
            <span>Feed status</span>
            <strong>{freshSensors}/{totalSensors}</strong>
            <small>Reporting inside freshness policy</small>
          </div>
        </article>

        <article className="kpi-card clickable-kpi" onClick={() => changeFilter('attention')}>
          <div className="kpi-icon tone-critical"><AlertTriangle size={20} /></div>
          <div className="kpi-copy">
            <span>Needs attention</span>
            <strong>{fmt(attentionSensors)}</strong>
            <small>
              {fmt(offlineSensors)} offline · {fmt(staleSensors)} stale
            </small>
          </div>
        </article>

        <article className="kpi-card">
          <div className="kpi-icon tone-accent"><Clock3 size={20} /></div>
          <div className="kpi-copy">
            <span>Latest telemetry</span>
            <strong>{fmtDuration(latestAge)}</strong>
            <small>{fmtTimestamp(data?.latest_recorded_when)} · informational</small>
          </div>
        </article>

        <article
          className="kpi-card clickable-kpi"
          onClick={() => {
            setDetailSensorKey(null)
            setPolicyOpen(true)
          }}
        >
          <div className="kpi-icon tone-warning"><Thermometer size={20} /></div>
          <div className="kpi-copy">
            <span>Temperature policy</span>
            <strong>
              {temperatureConfigured ? 'Active' : 'Not set'}
            </strong>
            <small>
              {temperatureConfigured
                ? `Warning ${warningBand.low?.toFixed(1)}–${warningBand.high?.toFixed(1)} °C · View policy`
                : 'No warning / critical bands configured · View policy'}
            </small>
          </div>
        </article>
      </section>

      <section className="fulfillment-mid-grid coldchain-mid-grid">
        <article className="panel-card aging-card coldchain-freshness-card">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Feed health</span>
              <h3>Sensor feed reliability</h3>
            </div>
            <span
              className={
                'status-chip ' +
                (attentionSensors > 0 ? 'critical' : 'success')
              }
            >
              {attentionSensors > 0 ? 'Action required' : 'All reporting'}
            </span>
          </div>

          <div className="coldchain-group-list">
            {(data?.sensor_groups ?? []).map((group) => (
              <button
                key={group.sensor_type}
                className="coldchain-group-row"
                onClick={() =>
                  changeFilter(group.sensor_type === 'coldroom' ? 'coldroom' : 'vehicle')
                }
              >
                <div className="coldchain-group-icon">
                  {group.sensor_type === 'coldroom'
                    ? <Snowflake size={17} />
                    : <Truck size={17} />}
                </div>

                <div className="coldchain-group-copy">
                  <strong>{sensorTypeLabel(group.sensor_type)}</strong>
                  <span>
                    Latest {fmtDuration(groupStats(group.sensor_type).latestAge)} ago
                  </span>
                  <small>
                    stale after {fmtDuration(group.stale_after_seconds)} ·
                    offline after {fmtDuration(group.offline_after_seconds)}
                  </small>
                </div>

                <div className="coldchain-group-state">
                  <strong>
                    {fmt(groupStats(group.sensor_type).fresh)}/{fmt(groupStats(group.sensor_type).total)} fresh
                  </strong>
                  <span>
                    {fmt(groupStats(group.sensor_type).stale)} stale ·
                    {fmt(groupStats(group.sensor_type).offline)} offline
                  </span>
                </div>
              </button>
            ))}
          </div>

          <div className="coldchain-feed-note">
            Fresh means the reading arrived within the configured reporting cadence.
            It does not mean the temperature itself is within an acceptable band.
          </div>
        </article>

        <article className="panel-card coldchain-movement-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Live sensor movement</span>
              <h3>Current sensor movement</h3>
            </div>
            <span className="status-chip monitoring">
              Last {data?.monitoring.history_points ?? 0} readings
            </span>
          </div>

          <div className="coldchain-movement-grid">
            {liveSensors.map((sensor) => (
              <button
                key={sensor.sensor_key}
                className="coldchain-movement-card"
                onClick={() => setDetailSensorKey(sensor.sensor_key)}
              >
                <div className="coldchain-movement-head">
                  <div>
                    <strong>{sensorLabel(sensor)}</strong>
                    <span>{fmtDuration(sensor.age_seconds)} ago</span>
                  </div>
                  <span className={'status-chip ' + stateTone(sensor.operational_state)}>
                    {stateLabel(sensor.operational_state)}
                  </span>
                </div>

                <div className="coldchain-movement-body">
                  <div className="coldchain-current-temp">
                    <strong>{fmtTemp(sensor.temperature)}</strong>
                    <span className={'movement-' + sensor.movement}>
                      <MovementIcon movement={sensor.movement} />
                      {fmtDelta(sensor.temperature_delta)}
                    </span>
                  </div>
                  <Sparkline points={sensor.history} />
                </div>
              </button>
            ))}
          </div>
        </article>
      </section>

      <section className="panel-card fulfillment-table-card">
        <div className="panel-header fulfillment-queue-header">
          <div>
            <span className="panel-kicker">Operational sensor queue</span>
            <h3>
              {selectedSensorKey
                ? 'Selected sensor'
                : filter === 'attention'
                  ? 'Sensors needing attention'
                  : filter === 'fresh'
                    ? 'Fresh sensors'
                    : filter === 'coldroom'
                      ? 'Cold-room sensors'
                      : filter === 'vehicle'
                        ? 'Vehicle sensors'
                        : 'All monitored sensors'}{' '}
              / {fmt(visibleSensors.length)}
            </h3>
          </div>

          <button
            className="panel-action"
            onClick={() => void load(true)}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        <div className="fulfillment-queue-tools coldchain-queue-tools">
          <div className="coldchain-queue-explainer">
            <AlertTriangle size={15} />
            <span>
              Exceptions sort first; healthy sensors are ordered by the largest latest movement.
            </span>
          </div>

          <div className="fulfillment-filter-row">
            {filters.map((item) => (
              <button
                key={item.value}
                className={'panel-action ' + (!selectedSensorKey && filter === item.value ? 'active' : '')}
                onClick={() => changeFilter(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="fulfillment-table-wrap">
          <table className="fulfillment-table coldchain-work-table">
            <thead>
              <tr>
                <th>Sensor</th>
                <th>Current temperature</th>
                <th>Δ previous</th>
                <th>Last reading</th>
                <th>Reading age / policy</th>
                <th>Feed</th>
                <th>Temperature status</th>
              </tr>
            </thead>
            <tbody>
              {visibleSensors.map((sensor) => (
                <tr
                  key={sensor.sensor_key}
                  className={
                    (selectedSensorKey === sensor.sensor_key ? 'coldchain-selected-row ' : '') +
                    'coldchain-clickable-row'
                  }
                  onClick={() => setDetailSensorKey(sensor.sensor_key)}
                >
                  <td>
                    <strong>{sensorLabel(sensor)}</strong>
                    <small>{sensor.sensor_key}</small>
                  </td>
                  <td>
                    <strong>{fmtTemp(sensor.temperature)}</strong>
                  </td>
                  <td>
                    <span className={'coldchain-delta movement-' + sensor.movement}>
                      <MovementIcon movement={sensor.movement} />
                      {fmtDelta(sensor.temperature_delta)}
                    </span>
                  </td>
                  <td>{fmtTimestamp(sensor.recorded_when)}</td>
                  <td>
                    <strong>{fmtDuration(sensor.age_seconds)}</strong>
                    <small>
                      stale at {fmtDuration(sensor.stale_after_seconds)} ·
                      offline at {fmtDuration(sensor.offline_after_seconds)}
                    </small>
                  </td>
                  <td>
                    <span className={'status-chip ' + stateTone(sensor.operational_state)}>
                      {stateLabel(sensor.operational_state)}
                    </span>
                  </td>
                  <td>
                    <span
                      className={
                        'status-chip ' +
                        (sensor.temperature_state === 'critical'
                          ? 'critical'
                          : sensor.temperature_state === 'warning'
                            ? 'warning'
                            : sensor.temperature_state === 'normal'
                              ? 'success'
                              : 'monitoring')
                      }
                    >
                      {temperatureLabel(sensor)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {data && visibleSensors.length === 0 && (
            <div className="panel-empty healthy-empty">
              No sensors match this filter.
            </div>
          )}
          {!data && !error && (
            <div className="panel-empty">Loading cold-chain sensor state...</div>
          )}
        </div>
      </section>

      {policyOpen && (
        <>
          <button
            className="coldchain-drawer-backdrop"
            aria-label="Close temperature policy"
            onClick={() => setPolicyOpen(false)}
          />

          <aside className="coldchain-drawer" aria-label="Temperature policy">
            <div className="coldchain-drawer-header">
              <div>
                <span className="panel-kicker">Temperature policy</span>
                <h3>Cold Chain thresholds</h3>
                <small>Current project configuration</small>
              </div>
              <button className="icon-button" onClick={() => setPolicyOpen(false)}>
                <X size={17} />
              </button>
            </div>

            <div className="coldchain-drawer-body">
              <div className="coldchain-drawer-badges">
                <span className={'status-chip ' + (temperatureConfigured ? 'success' : 'warning')}>
                  {temperatureConfigured ? 'Active' : 'Not configured'}
                </span>
              </div>

              <section className="coldchain-policy-band-grid">
                <article>
                  <span>Warning</span>
                  <strong>
                    {warningBand.low !== null && warningBand.high !== null
                      ? `${warningBand.low.toFixed(1)}–${warningBand.high.toFixed(1)} °C`
                      : 'Not configured'}
                  </strong>
                </article>
                <article>
                  <span>Critical</span>
                  <strong>
                    {criticalBand.low !== null && criticalBand.high !== null
                      ? `${criticalBand.low.toFixed(1)}–${criticalBand.high.toFixed(1)} °C`
                      : 'Not configured'}
                  </strong>
                </article>
              </section>

              <section className="coldchain-detail-section">
                <dl className="coldchain-detail-list">
                  <div><dt>Cold room</dt><dd>4 sensors</dd></div>
                  <div><dt>Vehicle</dt><dd>2 sensors</dd></div>
                </dl>
              </section>
            </div>
          </aside>
        </>
      )}

      {detailSensor && (
        <>
          <button
            className="coldchain-drawer-backdrop"
            aria-label="Close sensor detail"
            onClick={() => setDetailSensorKey(null)}
          />

          <aside className="coldchain-drawer" aria-label="Cold-chain sensor detail">
            <div className="coldchain-drawer-header">
              <div>
                <span className="panel-kicker">Sensor detail</span>
                <h3>{sensorLabel(detailSensor)}</h3>
                <small>{detailSensor.sensor_key}</small>
              </div>
              <button className="icon-button" onClick={() => setDetailSensorKey(null)}>
                <X size={17} />
              </button>
            </div>

            <div className="coldchain-drawer-body">
              <div className="coldchain-drawer-badges">
                <span className={'status-chip ' + stateTone(detailSensor.operational_state)}>
                  {stateLabel(detailSensor.operational_state)}
                </span>
                <span
                  className={
                    'status-chip ' +
                    (detailSensor.temperature_thresholds_configured ? 'success' : 'monitoring')
                  }
                >
                  {temperatureLabel(detailSensor)}
                </span>
              </div>

              <section className="coldchain-detail-metrics">
                <div>
                  <span>Current</span>
                  <strong>{fmtTemp(detailSensor.temperature)}</strong>
                </div>
                <div>
                  <span>Δ previous</span>
                  <strong>{fmtDelta(detailSensor.temperature_delta)}</strong>
                </div>
                <div>
                  <span>Reading age</span>
                  <strong>{fmtDuration(detailSensor.age_seconds)}</strong>
                </div>
              </section>

              <section className="coldchain-detail-section">
                <div className="coldchain-detail-section-head">
                  <div>
                    <span className="panel-kicker">Recent movement</span>
                    <h4>Short-term sensor history</h4>
                  </div>
                  <span>{detailSensor.history.length} readings</span>
                </div>
                <div className="coldchain-detail-chart">
                  <Sparkline points={detailSensor.history} width={320} height={90} />
                </div>
              </section>

              <section className="coldchain-detail-section">
                <div className="coldchain-detail-section-head">
                  <div>
                    <span className="panel-kicker">Feed policy</span>
                    <h4>Feed reliability thresholds</h4>
                  </div>
                </div>
                <dl className="coldchain-detail-list">
                  <div><dt>Last reading</dt><dd>{fmtTimestamp(detailSensor.recorded_when)}</dd></div>
                  <div><dt>Current age</dt><dd>{fmtDuration(detailSensor.age_seconds)}</dd></div>
                  <div><dt>Stale after</dt><dd>{fmtDuration(detailSensor.stale_after_seconds)}</dd></div>
                  <div><dt>Offline after</dt><dd>{fmtDuration(detailSensor.offline_after_seconds)}</dd></div>
                </dl>
              </section>

              <section className="coldchain-detail-section">
                <div className="coldchain-detail-section-head">
                  <div>
                    <span className="panel-kicker">Recent readings</span>
                    <h4>Evidence behind the current movement</h4>
                  </div>
                </div>
                <div className="coldchain-reading-list">
                  {[...detailSensor.history].reverse().slice(0, 8).map((point, index) => (
                    <div key={(point.recorded_when ?? 'reading') + index}>
                      <span>{fmtTimestamp(point.recorded_when)}</span>
                      <strong>{fmtTemp(point.temperature)}</strong>
                    </div>
                  ))}
                </div>
              </section>

              <button
                className="exception-open-record"
                onClick={() => {
                  setDetailSensorKey(null)
                  setPolicyOpen(true)
                }}
              >
                View temperature policy <Thermometer size={16} />
              </button>
            </div>
          </aside>
        </>
      )}
    </div>
  )
}
