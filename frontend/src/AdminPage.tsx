import { useEffect, useMemo, useState } from 'react'
import {
  BellRing,
  Filter,
  LockKeyhole,
  RefreshCw,
  Save,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from 'lucide-react'
import {
  fetchAdminOverview,
  patchAlertRule,
  type AdminOverview,
} from './api'

const nf = new Intl.NumberFormat('en-US')
const fmt = (value: number | undefined) => (value === undefined ? '—' : nf.format(value))

type AdminRule = AdminOverview['rules'][number]
type RuleStatusFilter = 'all' | 'enabled' | 'disabled'
type RuleSourceFilter = 'all' | 'project' | 'source'

function fmtTimestamp(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString([], {
    month:'short',
    day:'numeric',
    hour:'2-digit',
    minute:'2-digit',
  })
}

function domainLabel(value:string) {
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function parameterSummary(parameters:Record<string,unknown>) {
  if ('seconds' in parameters && typeof parameters.seconds === 'number') {
    const seconds=parameters.seconds
    if (seconds >= 60 && seconds % 60 === 0) return `${seconds / 60} min`
    return `${seconds} sec`
  }

  const low=parameters.low
  const high=parameters.high
  if (typeof low === 'number' || typeof high === 'number') {
    return `${typeof low === 'number' ? low : '—'} to ${typeof high === 'number' ? high : '—'} °C`
  }

  return Object.keys(parameters).length ? 'Configured' : 'No parameters'
}

function policyLabel(value:string | null | undefined) {
  if (!value) return 'Unknown'
  if (value === 'event_touched_only') return 'Event-touched'
  return value.replaceAll('_', ' ')
}

function auditChangeSummary(
  before:AdminOverview['recent_changes'][number]['before_config'],
  after:AdminOverview['recent_changes'][number]['after_config'],
) {
  const changes:string[]=[]
  if (before.enabled !== after.enabled) {
    changes.push(after.enabled ? 'enabled' : 'disabled')
  }
  if (before.severity !== after.severity) {
    changes.push(`severity ${before.severity} → ${after.severity}`)
  }
  if (JSON.stringify(before.parameters) !== JSON.stringify(after.parameters)) {
    changes.push('parameters updated')
  }
  return changes.length ? changes.join(' · ') : 'configuration saved'
}

export default function AdminPage() {
  const [data, setData] = useState<AdminOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [search, setSearch] = useState('')
  const [domain, setDomain] = useState('all')
  const [status, setStatus] = useState<RuleStatusFilter>('all')
  const [source, setSource] = useState<RuleSourceFilter>('all')
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null)
  const [editEnabled, setEditEnabled] = useState(true)
  const [editSeverity, setEditSeverity] = useState('warning')
  const [editSeconds, setEditSeconds] = useState('')
  const [editLow, setEditLow] = useState('')
  const [editHigh, setEditHigh] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const load = async (showBusy = false) => {
    if (showBusy) setRefreshing(true)
    try {
      const next = await fetchAdminOverview()
      setData(next)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load admin data')
    } finally {
      if (showBusy) setRefreshing(false)
    }
  }

  useEffect(() => {
    void load(false)
  }, [])

  const selectedRule =
    data?.rules.find((rule) => rule.rule_id === selectedRuleId) ?? null

  useEffect(() => {
    if (!selectedRule) return
    setEditEnabled(selectedRule.enabled)
    setEditSeverity(selectedRule.severity)
    setEditSeconds(
      typeof selectedRule.parameters.seconds === 'number'
        ? String(selectedRule.parameters.seconds)
        : '',
    )
    setEditLow(
      typeof selectedRule.parameters.low === 'number'
        ? String(selectedRule.parameters.low)
        : '',
    )
    setEditHigh(
      typeof selectedRule.parameters.high === 'number'
        ? String(selectedRule.parameters.high)
        : '',
    )
    setSaveError(null)
  }, [selectedRuleId, selectedRule?.updated_at])

  const projectOwnedRules = useMemo(
    () => (data?.rules ?? []).filter((rule) => !rule.source_native),
    [data],
  )

  const visibleRules = useMemo(() => {
    const term=search.trim().toLowerCase()
    return (data?.rules ?? []).filter((rule) => {
      if (domain !== 'all' && rule.domain !== domain) return false
      if (status === 'enabled' && !rule.enabled) return false
      if (status === 'disabled' && rule.enabled) return false
      if (source === 'project' && rule.source_native) return false
      if (source === 'source' && !rule.source_native) return false
      if (
        term &&
        !rule.rule_id.toLowerCase().includes(term) &&
        !rule.description.toLowerCase().includes(term) &&
        !rule.domain.toLowerCase().includes(term)
      ) return false
      return true
    })
  }, [data, domain, status, source, search])

  const selectedRuleHistory = useMemo(
    () => (data?.recent_changes ?? [])
      .filter((change) => change.rule_id === selectedRuleId)
      .slice(0, 8),
    [data, selectedRuleId],
  )

  const setRuleSelection = (rule:AdminRule) => {
    setSelectedRuleId(rule.rule_id)
    setSaveError(null)
  }

  const saveRule = async () => {
    if (!selectedRule || selectedRule.source_native) return

    const parameters={...selectedRule.parameters}
    if ('seconds' in parameters) {
      const seconds=Number(editSeconds)
      if (!Number.isFinite(seconds) || seconds <= 0) {
        setSaveError('Freshness interval must be a positive number of seconds.')
        return
      }
      parameters.seconds=seconds
    }

    if ('low' in parameters || 'high' in parameters) {
      const low=editLow.trim() === '' ? null : Number(editLow)
      const high=editHigh.trim() === '' ? null : Number(editHigh)
      if (
        (low !== null && !Number.isFinite(low)) ||
        (high !== null && !Number.isFinite(high))
      ) {
        setSaveError('Temperature limits must be numeric.')
        return
      }
      if (low !== null && high !== null && low >= high) {
        setSaveError('Low temperature must be below high temperature.')
        return
      }
      parameters.low=low
      parameters.high=high
    }

    setSaving(true)
    setSaveError(null)
    try {
      await patchAlertRule(selectedRule.rule_id, {
        enabled:editEnabled,
        severity:editSeverity as 'info'|'warning'|'critical',
        parameters,
        actor:'admin-ui',
      })
      await load(false)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Unable to save rule')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fulfillment-page admin-v2">
      <section className="overview-heading">
        <div>
          <div className="overview-title-row">
            <h2>Admin</h2>
            <span className="preview-pill">Rule management</span>
          </div>
          <p>
            Alert coverage, project-owned rule configuration, and configuration change history.
          </p>
        </div>

        <div className="overview-meta">
          <span>
            <span className="live-dot" />
            {error ? 'Configuration unavailable' : data ? 'Configuration connected' : 'Connecting'}
          </span>
          <span>Refreshed {fmtTimestamp(data?.generated_at)}</span>
        </div>
      </section>

      {error && <div className="overview-error">Admin serving error: {error}</div>}

      <section className="kpi-grid fulfillment-kpi-grid">
        <button
          className="kpi-card analytics-clickable-kpi"
          onClick={() => { setDomain('all'); setStatus('all'); setSource('all') }}
        >
          <div className="kpi-icon tone-accent"><Settings2 size={20} /></div>
          <div className="kpi-copy">
            <span>Alert rules</span>
            <strong>{fmt(data?.summary.total_rules)}</strong>
            <small>{fmt(data?.summary.enabled_rules)} enabled</small>
          </div>
        </button>

        <button
          className="kpi-card analytics-clickable-kpi"
          onClick={() => { setSource('project'); setStatus('all'); setDomain('all') }}
        >
          <div className="kpi-icon tone-cool"><SlidersHorizontal size={20} /></div>
          <div className="kpi-copy">
            <span>Project-owned</span>
            <strong>{fmt(projectOwnedRules.length)}</strong>
            <small>Configurable rules</small>
          </div>
        </button>

        <button
          className="kpi-card analytics-clickable-kpi"
          onClick={() => { setStatus('disabled'); setSource('all'); setDomain('all') }}
        >
          <div className="kpi-icon tone-warning"><BellRing size={20} /></div>
          <div className="kpi-copy">
            <span>Disabled rules</span>
            <strong>{fmt(data?.summary.disabled_rules)}</strong>
            <small>Explicitly inactive</small>
          </div>
        </button>

        <article className="kpi-card">
          <div className="kpi-icon tone-cool"><LockKeyhole size={20} /></div>
          <div className="kpi-copy">
            <span>Evaluation policy</span>
            <strong>{policyLabel(data?.alert_engine.backlog_policy)}</strong>
            <small>
              Activated {fmtTimestamp(data?.alert_engine.activated_at)} · guard {data?.processing_guard.mode ? 'acquired' : 'free'}
            </small>
          </div>
        </article>
      </section>

      <section className="panel-card admin-domain-card">
        <div className="panel-header">
          <div>
            <span className="panel-kicker">Rule coverage</span>
            <h3>Domains</h3>
          </div>
          <span className="panel-muted">{fmt(data?.domains.length)} domains</span>
        </div>

        <div className="admin-domain-grid">
          {(data?.domains ?? []).map((item) => (
            <button
              key={item.domain}
              className={'admin-domain-tile ' + (domain === item.domain ? 'active' : '')}
              onClick={() => setDomain(domain === item.domain ? 'all' : item.domain)}
            >
              <span>{domainLabel(item.domain)}</span>
              <strong>{fmt(item.enabled_rules)}/{fmt(item.total_rules)}</strong>
              <small>enabled · {fmt(item.disabled_rules)} disabled</small>
            </button>
          ))}
        </div>
      </section>

      <section className="panel-card fulfillment-table-card admin-rule-card">
        <div className="panel-header fulfillment-queue-header">
          <div>
            <span className="panel-kicker">Rule registry</span>
            <h3>Alert configuration / {fmt(visibleRules.length)}</h3>
          </div>

          <button className="panel-action" onClick={() => void load(true)} disabled={refreshing}>
            <RefreshCw size={13} />
            {refreshing ? 'Refreshing…' : 'Refresh rules'}
          </button>
        </div>

        <div className="admin-rule-tools">
          <label className="admin-rule-search">
            <Search size={14} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search rule, domain, or description"
            />
          </label>

          <div className="admin-filter-group">
            <Filter size={13} />
            {(['all','enabled','disabled'] as RuleStatusFilter[]).map((item) => (
              <button
                key={item}
                className={status === item ? 'active' : ''}
                onClick={() => setStatus(item)}
              >
                {item === 'all' ? 'All status' : item}
              </button>
            ))}
          </div>

          <div className="admin-filter-group">
            {(['all','project','source'] as RuleSourceFilter[]).map((item) => (
              <button
                key={item}
                className={source === item ? 'active' : ''}
                onClick={() => setSource(item)}
              >
                {item === 'all' ? 'All source' : item === 'project' ? 'Project-owned' : 'Source-native'}
              </button>
            ))}
          </div>
        </div>

        <div className="fulfillment-table-wrap">
          <table className="fulfillment-table admin-rule-table">
            <thead>
              <tr>
                <th>Rule</th>
                <th>Domain</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Configuration</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {visibleRules.map((rule) => (
                <tr
                  key={rule.rule_id}
                  className="admin-rule-row"
                  tabIndex={0}
                  role="button"
                  onClick={() => setRuleSelection(rule)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setRuleSelection(rule)
                    }
                  }}
                >
                  <td>
                    <strong>{rule.rule_id}</strong>
                    <small>{rule.description}</small>
                  </td>
                  <td>{domainLabel(rule.domain)}</td>
                  <td>
                    <span className={`status-chip ${rule.severity === 'critical' ? 'critical' : rule.severity === 'warning' ? 'warning' : 'monitoring'}`}>
                      {rule.severity}
                    </span>
                  </td>
                  <td>
                    <span className={`status-chip ${rule.enabled ? 'success' : 'warning'}`}>
                      {rule.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </td>
                  <td>{parameterSummary(rule.parameters)}</td>
                  <td>{rule.source_native ? 'Source-native' : 'Project-owned'}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {data && visibleRules.length === 0 && (
            <div className="panel-empty">No rules match the current filters.</div>
          )}
          {!data && !error && <div className="panel-empty">Loading rule registry…</div>}
        </div>
      </section>

      {selectedRule && (
        <>
          <button
            className="coldchain-drawer-backdrop"
            aria-label="Close rule detail"
            onClick={() => setSelectedRuleId(null)}
          />

          <aside className="coldchain-drawer admin-rule-drawer" aria-label="Rule configuration">
            <div className="coldchain-drawer-header">
              <div>
                <span className="panel-kicker">Rule configuration</span>
                <h3>{selectedRule.rule_id}</h3>
                <small>{domainLabel(selectedRule.domain)} · {selectedRule.source_native ? 'Source-native' : 'Project-owned'}</small>
              </div>
              <button className="icon-button" onClick={() => setSelectedRuleId(null)}>
                <X size={17} />
              </button>
            </div>

            <div className="coldchain-drawer-body">
              <div className="admin-rule-description">
                {selectedRule.description}
              </div>

              <section className="admin-rule-form">
                <label>
                  <span>Status</span>
                  <select
                    value={editEnabled ? 'enabled' : 'disabled'}
                    disabled={selectedRule.source_native}
                    onChange={(event) => setEditEnabled(event.target.value === 'enabled')}
                  >
                    <option value="enabled">Enabled</option>
                    <option value="disabled">Disabled</option>
                  </select>
                </label>

                <label>
                  <span>Severity</span>
                  <select
                    value={editSeverity}
                    disabled={selectedRule.source_native}
                    onChange={(event) => setEditSeverity(event.target.value)}
                  >
                    <option value="info">Info</option>
                    <option value="warning">Warning</option>
                    <option value="critical">Critical</option>
                  </select>
                </label>

                {'seconds' in selectedRule.parameters && (
                  <label className="admin-form-wide">
                    <span>Freshness interval · seconds</span>
                    <input
                      type="number"
                      min="1"
                      value={editSeconds}
                      disabled={selectedRule.source_native}
                      onChange={(event) => setEditSeconds(event.target.value)}
                    />
                  </label>
                )}

                {('low' in selectedRule.parameters || 'high' in selectedRule.parameters) && (
                  <>
                    <label>
                      <span>Low threshold · °C</span>
                      <input
                        type="number"
                        step="0.1"
                        value={editLow}
                        disabled={selectedRule.source_native}
                        onChange={(event) => setEditLow(event.target.value)}
                      />
                    </label>
                    <label>
                      <span>High threshold · °C</span>
                      <input
                        type="number"
                        step="0.1"
                        value={editHigh}
                        disabled={selectedRule.source_native}
                        onChange={(event) => setEditHigh(event.target.value)}
                      />
                    </label>
                  </>
                )}
              </section>

              <section className="coldchain-detail-section">
                <dl className="coldchain-detail-list">
                  <div><dt>Source basis</dt><dd>{selectedRule.source_native ? 'Source-native' : 'Project-owned'}</dd></div>
                  <div><dt>Last updated</dt><dd>{fmtTimestamp(selectedRule.updated_at)}</dd></div>
                  <div><dt>Evaluation policy</dt><dd>{policyLabel(data?.alert_engine.backlog_policy)}</dd></div>
                </dl>
              </section>

              {selectedRule.source_native ? (
                <div className="admin-readonly-note">
                  <ShieldCheck size={15} />
                  Source-native rules are protected by the API and cannot be changed from Admin.
                </div>
              ) : (
                <button
                  className="exception-open-record admin-save-rule"
                  onClick={() => void saveRule()}
                  disabled={saving}
                >
                  <Save size={15} />
                  {saving ? 'Saving…' : 'Save rule'}
                </button>
              )}

              {saveError && <div className="overview-error">{saveError}</div>}

              <section className="coldchain-detail-section admin-audit-section">
                <div className="coldchain-detail-section-head">
                  <div>
                    <span className="panel-kicker">Configuration history</span>
                    <h4>Recent changes</h4>
                  </div>
                </div>

                <div className="admin-audit-list">
                  {selectedRuleHistory.map((change) => (
                    <div className="admin-audit-row" key={change.audit_id}>
                      <div>
                        <strong>{auditChangeSummary(change.before_config, change.after_config)}</strong>
                        <small>{change.actor} · {fmtTimestamp(change.changed_at)}</small>
                      </div>
                      <span>
                        {typeof change.reevaluation_result.entities === 'number'
                          ? `${change.reevaluation_result.entities} entities`
                          : 'Applied'}
                      </span>
                    </div>
                  ))}
                  {selectedRuleHistory.length === 0 && (
                    <div className="panel-empty">No configuration changes recorded yet.</div>
                  )}
                </div>
              </section>
            </div>
          </aside>
        </>
      )}
    </div>
  )
}
