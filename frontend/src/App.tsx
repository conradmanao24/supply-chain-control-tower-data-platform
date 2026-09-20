import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  BarChart3,
  Boxes,
  ClipboardList,
  Gauge,
  Menu,
  Moon,
  PackageCheck,
  Settings,
  Snowflake,
  Sun,
  Truck,
  X,
} from 'lucide-react'
import {
  fetchApiHealth,
  fetchControlTowerOverview,
  realtimeStreamUrl,
  type ApiHealth,
  type ControlTowerOverview,
  type SseConnectionState,
  type FulfillmentFilter,
  type InventoryFilter,
  type ProcurementFilter,
} from './api'
import ControlTowerPage from './ControlTowerPage'
import FulfillmentPage from './FulfillmentPage'
import DeliveryPage from './DeliveryPage'
import InventoryPage from './InventoryPage'
import ProcurementPage from './ProcurementPage'
import ColdChainPage from './ColdChainPage'
import AnalyticsPage from './AnalyticsPage'
import PlatformHealthPage from './PlatformHealthPage'
import AdminPage from './AdminPage'
import './App.css'

type NavItem = {
  label: string
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Control Tower', icon: Gauge },
  { label: 'Fulfillment', icon: PackageCheck },
  { label: 'Delivery', icon: Truck },
  { label: 'Inventory', icon: Boxes },
  { label: 'Procurement', icon: ClipboardList },
  { label: 'Cold Chain', icon: Snowflake },
  { label: 'Analytics', icon: BarChart3 },
  { label: 'Platform Health', icon: Activity },
  { label: 'Admin', icon: Settings },
]

function formatTimestamp(value: string | null | undefined) {
  if (!value) return 'â€”'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'â€”'
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function App() {
  const [active, setActive] = useState('Control Tower')
  const [fulfillmentEntryFilter, setFulfillmentEntryFilter] = useState<FulfillmentFilter>('open')
  const [fulfillmentEntryRecordId, setFulfillmentEntryRecordId] = useState<number | null>(null)
  const [deliveryEntryFilter, setDeliveryEntryFilter] = useState<'all' | 'pending' | 'confirmed' | 'receiver_not_present' | 'overdue' | 'due_today'>('pending')
  const [deliveryEntryRecordId, setDeliveryEntryRecordId] = useState<number | null>(null)
  const [inventoryEntryFilter, setInventoryEntryFilter] = useState<InventoryFilter>('risk')
  const [inventoryEntryRecordId, setInventoryEntryRecordId] = useState<number | null>(null)
  const [procurementEntryFilter, setProcurementEntryFilter] = useState<ProcurementFilter>('open')
  const [procurementEntryRecordId, setProcurementEntryRecordId] = useState<number | null>(null)
  const [coldChainEntrySensorKey, setColdChainEntrySensorKey] = useState<string | null>(null)
  const [darkMode, setDarkMode] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [overview, setOverview] = useState<ControlTowerOverview | null>(null)
  const [apiHealth, setApiHealth] = useState<ApiHealth | null>(null)
  const [overviewError, setOverviewError] = useState<string | null>(null)
  const [sseState, setSseState] = useState<SseConnectionState>('connecting')
  const [fulfillmentRefreshSignal, setFulfillmentRefreshSignal] = useState(0)
  const [deliveryRefreshSignal, setDeliveryRefreshSignal] = useState(0)
  const [inventoryRefreshSignal, setInventoryRefreshSignal] = useState(0)
  const [procurementRefreshSignal, setProcurementRefreshSignal] = useState(0)
  const [coldChainRefreshSignal, setColdChainRefreshSignal] = useState(0)
  const [platformHealthRefreshSignal, setPlatformHealthRefreshSignal] = useState(0)

  const activeRef = useRef(active)

  useEffect(() => {
    activeRef.current = active
  }, [active])

  useEffect(() => {
    let cancelled = false

    Promise.all([fetchControlTowerOverview(), fetchApiHealth()])
      .then(([overviewData, healthData]) => {
        if (cancelled) return
        setOverview(overviewData)
        setApiHealth(healthData)
        setOverviewError(null)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setOverviewError(error instanceof Error ? error.message : 'Unable to load serving data')
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let closed = false
    let servingRefreshTimer: number | undefined
    const domainTimers: Partial<Record<string, number>> = {}
    const stream = new EventSource(realtimeStreamUrl())
    setSseState('connecting')

    const scheduleSignal = (
      key: string,
      updater: (fn: (value: number) => number) => void,
      delay = 900,
    ) => {
      if (domainTimers[key] !== undefined) return
      domainTimers[key] = window.setTimeout(() => {
        delete domainTimers[key]
        if (!closed) updater((value) => value + 1)
      }, delay)
    }

    const refreshServingData = () => {
      if (servingRefreshTimer !== undefined) return
      servingRefreshTimer = window.setTimeout(() => {
        servingRefreshTimer = undefined
        Promise.all([fetchControlTowerOverview(), fetchApiHealth()])
          .then(([overviewData, healthData]) => {
            if (closed) return
            setOverview(overviewData)
            setApiHealth(healthData)
            setOverviewError(null)
          })
          .catch((error: unknown) => {
            if (closed) return
            setOverviewError(error instanceof Error ? error.message : 'Unable to refresh serving data')
          })
      }, 1800)
    }

    const handleServingEvent = (event: Event) => {
      refreshServingData()

      if (activeRef.current === 'Platform Health') {
        scheduleSignal('platform-health', setPlatformHealthRefreshSignal, 1200)
      }

      if (!(event instanceof MessageEvent)) return
      try {
        const payload = JSON.parse(event.data) as {
          event_type?: string
          rule_id?: string
          domain?: string
        }

        const fulfillmentRelevant =
          payload.event_type === 'order.changed' ||
          payload.event_type?.startsWith('deadline.fulfillment.') ||
          payload.rule_id?.startsWith('fulfillment.') ||
          payload.domain === 'fulfillment'
        if (fulfillmentRelevant && activeRef.current === 'Fulfillment') {
          scheduleSignal('fulfillment', setFulfillmentRefreshSignal)
        }

        const deliveryRelevant =
          payload.event_type === 'delivery.changed' ||
          payload.event_type?.startsWith('deadline.delivery.') ||
          payload.rule_id?.startsWith('delivery.') ||
          payload.domain === 'delivery'
        if (deliveryRelevant && activeRef.current === 'Delivery') {
          scheduleSignal('delivery', setDeliveryRefreshSignal)
        }

        const inventoryRelevant =
          payload.event_type === 'inventory.changed' ||
          payload.rule_id?.startsWith('inventory.') ||
          payload.domain === 'inventory'
        if (inventoryRelevant && activeRef.current === 'Inventory') {
          scheduleSignal('inventory', setInventoryRefreshSignal)
        }

        const procurementRelevant =
          payload.event_type === 'procurement.changed' ||
          payload.rule_id?.startsWith('procurement.') ||
          payload.domain === 'procurement'
        if (procurementRelevant && activeRef.current === 'Procurement') {
          scheduleSignal('procurement', setProcurementRefreshSignal)
        }

        const coldChainRelevant =
          payload.event_type?.startsWith('telemetry.coldroom.') ||
          payload.event_type?.startsWith('telemetry.vehicle.') ||
          payload.rule_id?.startsWith('coldroom.') ||
          payload.domain === 'cold_chain'
        if (coldChainRelevant && activeRef.current === 'Cold Chain') {
          scheduleSignal('cold-chain', setColdChainRefreshSignal, 700)
        }
      } catch {
        // Ignore malformed SSE payloads; shared serving refresh remains coalesced.
      }
    }

    stream.addEventListener('ready', () => setSseState('connected'))
    stream.addEventListener('alert', handleServingEvent)
    stream.addEventListener('update', handleServingEvent)
    stream.onopen = () => setSseState('connected')
    stream.onerror = () => {
      if (!closed) setSseState('reconnecting')
    }

    return () => {
      closed = true
      if (servingRefreshTimer !== undefined) {
        window.clearTimeout(servingRefreshTimer)
      }
      Object.values(domainTimers).forEach((timer) => {
        if (timer !== undefined) window.clearTimeout(timer)
      })
      stream.close()
      setSseState('disconnected')
    }
  }, [])

  const subtitle = useMemo(() => {
    if (active === 'Control Tower') return 'Operational command center'
    return `${active} workspace`
  }, [active])

  const navigateOperationalRecord = (
    target: 'Fulfillment' | 'Delivery' | 'Inventory' | 'Procurement',
    recordId: number,
  ) => {
    if (target === 'Fulfillment') {
      setFulfillmentEntryFilter('all')
      setFulfillmentEntryRecordId(recordId)
    } else if (target === 'Delivery') {
      setDeliveryEntryFilter('all')
      setDeliveryEntryRecordId(recordId)
    } else if (target === 'Inventory') {
      setInventoryEntryFilter('all')
      setInventoryEntryRecordId(recordId)
    } else if (target === 'Procurement') {
      setProcurementEntryFilter('all')
      setProcurementEntryRecordId(recordId)
    }
    setActive(target)
  }

  const sseLabel =
    sseState === 'connected'
      ? 'SSE connected'
      : sseState === 'reconnecting'
        ? 'SSE reconnecting'
        : sseState === 'disconnected'
          ? 'SSE disconnected'
          : 'SSE connecting'

  return (
    <div className={`app-shell ${darkMode ? 'theme-dark' : 'theme-light'}`}>
      <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="brand-block">
          <div className="brand-mark">CT</div>
          <div className="brand-copy">
            <strong>Control Tower</strong>
            <span>Supply Chain</span>
          </div>
          <button className="icon-button mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation">
            <X size={18} />
          </button>
        </div>

        <nav className="primary-nav" aria-label="Primary navigation">
          {NAV_ITEMS.map(({ label, icon: Icon }) => (
            <button
              key={label}
              className={`nav-item ${active === label ? 'active' : ''}`}
              onClick={() => {
                if (label === 'Fulfillment') { setFulfillmentEntryFilter('open'); setFulfillmentEntryRecordId(null) }
                if (label === 'Delivery') { setDeliveryEntryFilter('pending'); setDeliveryEntryRecordId(null) }
                if (label === 'Inventory') { setInventoryEntryFilter('risk'); setInventoryEntryRecordId(null) }
                if (label === 'Procurement') { setProcurementEntryFilter('open'); setProcurementEntryRecordId(null) }
                if (label === 'Cold Chain') { setColdChainEntrySensorKey(null) }
                setActive(label)
                setSidebarOpen(false)
              }}
            >
              <Icon size={18} strokeWidth={1.9} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="system-chip">
            <span className={`status-dot ${sseState === 'reconnecting' ? 'status-dot-warning' : ''}`} />
            {apiHealth?.status === 'ok' ? 'Platform online' : overviewError ? 'API unavailable' : 'Connecting'}
          </div>
          <p>{sseLabel}</p>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Open navigation">
              <Menu size={20} />
            </button>
            <div>
              <p className="eyebrow">Supply Chain Control Tower</p>
              <h1>{active}</h1>
              <span className="page-subtitle">{subtitle}</span>
            </div>
          </div>

          <div className="topbar-actions">
            <button
              className="icon-button"
              onClick={() => setDarkMode((value) => !value)}
              aria-label="Toggle theme"
            >
              {darkMode ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <div className="profile-button profile-identity" aria-label="Current operator">
              <span className="profile-avatar">O</span>
              <span className="profile-copy">
                <strong>Operator</strong>
                <small>Control Tower</small>
              </span>
            </div>
          </div>
        </header>

        <main className="page-container">
          {active === 'Control Tower' ? (
            <ControlTowerPage
              overview={overview}
              apiHealth={apiHealth}
              sseState={sseState}
              error={overviewError}
              onNavigate={(target, options) => {
                if (target === 'Fulfillment') {
                  setFulfillmentEntryFilter(options?.fulfillmentFilter ?? 'all')
                  setFulfillmentEntryRecordId(options?.recordId ?? null)
                }
                if (target === 'Delivery') {
                  setDeliveryEntryFilter(options?.deliveryFilter ?? 'all')
                  setDeliveryEntryRecordId(options?.recordId ?? null)
                }
                if (target === 'Inventory') {
                  setInventoryEntryFilter(options?.inventoryFilter ?? 'all')
                  setInventoryEntryRecordId(options?.recordId ?? null)
                }
                if (target === 'Procurement') {
                  setProcurementEntryFilter(options?.procurementFilter ?? 'all')
                  setProcurementEntryRecordId(options?.recordId ?? null)
                }
                if (target === 'Cold Chain') {
                  setColdChainEntrySensorKey(options?.coldChainSensorKey ?? null)
                }
                setActive(target)
              }}
            />
          ) : active === 'Fulfillment' ? (
            <FulfillmentPage
              sseState={sseState}
              refreshSignal={fulfillmentRefreshSignal}
              initialFilter={fulfillmentEntryFilter}
              initialRecordId={fulfillmentEntryRecordId}
              onNavigate={navigateOperationalRecord}
            />
          ) : active === 'Delivery' ? (
            <DeliveryPage
              sseState={sseState}
              refreshSignal={deliveryRefreshSignal}
              initialFilter={deliveryEntryFilter}
              initialRecordId={deliveryEntryRecordId}
              onNavigate={navigateOperationalRecord}
            />
          ) : active === 'Inventory' ? (
            <InventoryPage
              sseState={sseState}
              refreshSignal={inventoryRefreshSignal}
              initialFilter={inventoryEntryFilter}
              initialRecordId={inventoryEntryRecordId}
              onNavigate={navigateOperationalRecord}
            />
          ) : active === 'Procurement' ? (
            <ProcurementPage
              sseState={sseState}
              refreshSignal={procurementRefreshSignal}
              initialFilter={procurementEntryFilter}
              initialRecordId={procurementEntryRecordId}
              onNavigate={navigateOperationalRecord}
            />
          ) : active === 'Cold Chain' ? (
            <ColdChainPage
              sseState={sseState}
              refreshSignal={coldChainRefreshSignal}
              initialSensorKey={coldChainEntrySensorKey}
            />
          ) : active === 'Analytics' ? (
            <AnalyticsPage />
          ) : active === 'Platform Health' ? (
            <PlatformHealthPage sseState={sseState} refreshSignal={platformHealthRefreshSignal} />
          ) : active === 'Admin' ? (
            <AdminPage />
          ) : (
            <section className="shell-preview-card">
              <div className="shell-preview-icon"><Activity size={22} /></div>
              <div>
                <p className="eyebrow">Workspace</p>
                <h2>{active}</h2>
                <p>This navigation state is not available.</p>
              </div>
            </section>
          )}
        </main>
      </div>

      {sidebarOpen && <button className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} aria-label="Close navigation backdrop" />}
    </div>
  )
}

export default App


















