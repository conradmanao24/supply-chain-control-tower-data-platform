export type OverviewAlert = {
  alert_id: number
  rule_id: string
  domain: string
  entity_type: string
  entity_id: string
  severity: 'info' | 'warning' | 'critical'
  status: 'open' | 'acknowledged'
  opened_at: string
  last_observed_at: string
}

export type ControlTowerOverview = {
  generated_at: string
  as_of_date: string
  kpis: {
    active_exceptions: number
    fulfillment_overdue: number
    delivery_pending: number
    delivery_overdue: number
    inventory_watch: number
  }
  workload: {
    fulfillment_open_window: number
    fulfillment_all_time_open: number
    fulfillment_due_today: number
    fulfillment_backorders: number
    delivery_pending: number
    delivery_due_today: number
    procurement_open: number
    procurement_overdue: number
    procurement_supply_risk_pos: number
    coldroom_sensors: number
    vehicle_sensors: number
  }
  alert_summary: {
    active: number
    affected_records: number
    critical: number
    warning: number
    info: number
  }
  domains: Array<{
    name: 'Fulfillment' | 'Delivery' | 'Inventory' | 'Procurement' | 'Cold Chain'
    status: 'healthy' | 'monitoring' | 'attention' | 'exception'
    headline: string
    detail: string
    target: 'Fulfillment' | 'Delivery' | 'Inventory' | 'Procurement' | 'Cold Chain'
  }>
  recent_alerts: OverviewAlert[]
  latest_activity: Array<{
    event_type: string
    entity_type: string
    operation: string
    occurred_at_utc: string
    source_table: string
    processing_result: string
    entity_id: string | null
  }>
  platform: {
    pipeline_cutoff: string | null
    source_frontier: string | null
    watermark_aligned: boolean
    freshness: {
      max_age_hours:number
      pipeline_age_hours:number|null
      frontier_age_hours:number|null
      quality_age_hours:number|null
      all_fresh:boolean
    }
    quality: null | {
      airflow_run_id: string
      status: 'running' | 'pass' | 'fail'
      passed_checks: number
      failed_checks: number
      warning_checks: number
      finished_at: string | null
    }
  }
}
export type ApiHealth = {
  status: string
  database: string
  sse_listener: string
  subscribers: number
  listener_error: string | null
}

const API_BASE = import.meta.env.VITE_REALTIME_API_BASE ?? 'http://127.0.0.1:18000'

const inFlightGetJson = new Map<string, Promise<unknown>>()

function getJson<T>(path: string): Promise<T> {
  const existing = inFlightGetJson.get(path)
  if (existing) return existing as Promise<T>

  const request = fetch(`${API_BASE}${path}`)
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`)
      }
      return response.json() as Promise<T>
    })
    .finally(() => {
      inFlightGetJson.delete(path)
    })

  inFlightGetJson.set(path, request)
  return request
}

export function fetchControlTowerOverview(): Promise<ControlTowerOverview> {
  return getJson('/api/control-tower/overview')
}

export type ExceptionSignal = {
  alert_id:number
  rule_id:string
  description:string
  severity:'info'|'warning'|'critical'
  status:'open'|'acknowledged'
  opened_at:string
  last_observed_at:string
}

export type ExceptionCaseItem = {
  entity_type:string
  entity_id:string
  domain:string
  severity:'info'|'warning'|'critical'
  status:'open'|'acknowledged'
  opened_at:string
  last_observed_at:string
  signal_count:number
  signals:ExceptionSignal[]
}

export type ExceptionEvidence = { label:string; value:string }

export type ExceptionAlertDetail = ExceptionSignal & {
  domain:string
  parameters:Record<string,unknown>
  entity_type:string
  entity_id:string
  acknowledged_at:string|null
  acknowledged_by:string|null
  resolved_at:string|null
  resolved_by:string|null
  observed_value:Record<string,unknown>|null
  threshold_value:Record<string,unknown>|null
  source_event_id:string|null
  resolution_reason:string|null
  evidence_verified:boolean
  what_happened:string|null
  why_it_matters:string|null
  business_evidence:ExceptionEvidence[]
}

export type ExceptionCaseDetail = {
  entity_type:string
  entity_id:string
  domain:string
  severity:'info'|'warning'|'critical'
  status:'open'|'acknowledged'
  opened_at:string
  last_observed_at:string
  signal_count:number
  alerts:ExceptionAlertDetail[]
}

export type ExceptionCaseListResponse = {
  generated_at:string
  page:number
  page_size:number
  total:number
  total_pages:number
  filters:{domain:string;severity:string;status:string;search:string}
  items:ExceptionCaseItem[]
}

export function fetchExceptionCases(options:{
  page:number
  pageSize:number
  domain:string
  severity:string
  status:string
  search:string
}):Promise<ExceptionCaseListResponse>{
  const q=new URLSearchParams({
    page:String(options.page),
    page_size:String(options.pageSize),
    domain:options.domain,
    severity:options.severity,
    status:options.status,
    search:options.search,
  })
  return getJson(`/api/control-tower/exception-cases?${q.toString()}`)
}

export function fetchExceptionCaseDetail(entityType:string, entityId:string):Promise<{generated_at:string;case:ExceptionCaseDetail}>{
  return getJson(`/api/control-tower/exception-cases/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`)
}

export function fetchApiHealth(): Promise<ApiHealth> {
  return getJson('/health')
}

export type SseConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected'

export function realtimeStreamUrl(): string {
  return `${API_BASE}/api/realtime/stream`
}

export type FulfillmentOverview = {
  generated_at:string
  as_of_date:string
  lookback_days:number
  kpis:{
    orders_in_window:number
    open_orders:number
    overdue_orders:number
    due_today:number
    upcoming_open:number
    backorders:number
    completed_orders:number
  }
  operational_context:{
    overdue_rate:number
    oldest_days_overdue:number
    median_days_overdue:number
    upcoming_open:number
    completed_orders:number
    supply_exposed_orders:number
    critical_supply_orders:number
  }
  aging:Array<{bucket:string;value:number}>
  alert_summary:{active:number;critical:number;warning:number;info:number}
}

export function fetchFulfillmentOverview():Promise<FulfillmentOverview>{
  return getJson('/api/fulfillment/overview')
}

export type DeliveryOverview = {
  generated_at:string
  as_of_date:string
  lookback_days:number
  kpis:{
    deliveries_30d:number
    pending:number
    overdue:number
    due_today:number
    upcoming_pending:number
    confirmed:number
    receiver_not_present_events:number
    receiver_not_present_pending:number
  }
  operational_context:{
    confirmation_rate:number
    overdue_rate_pending:number
    median_days_overdue:number
    oldest_days_overdue:number
    median_order_to_pick_days:number|null
    p90_order_to_pick_days:number|null
    median_invoice_to_confirm_days:number|null
    lifecycle_anomalies:number
    lifecycle_max_days:number
  }
  aging:Array<{bucket:string;value:number}>
  alert_summary:{active:number;critical:number;warning:number;info:number}
}
export function fetchDeliveryOverview():Promise<DeliveryOverview>{ return getJson('/api/delivery/overview') }

export type InventoryOverview = {
  generated_at:string
  kpis:{
    total_items:number
    reorder_required:number
    out_of_stock:number
    negative_stock:number
    supply_risk_items:number
    critical_supply_risk_items:number
  }
  stock_health:Array<{
    state:'negative'|'out_of_stock'|'reorder'|'healthy'
    value:number
  }>
  operational_context:{
    units_on_hand:number
    above_reorder:number
    total_below_reorder_by:number
    typical_order_qty_flagged:number
    open_demand_units:number
    incoming_units:number
    pre_inbound_shortfall_units:number
    projected_shortfall_units:number
  }
  alert_summary:{active:number;critical:number;warning:number;info:number}
  latest_state_edit:string|null
}
export function fetchInventoryOverview():Promise<InventoryOverview>{ return getJson('/api/inventory/overview') }

export type ProcurementOverview = {
  generated_at:string
  as_of_date:string
  lookback_days:number
  kpis:{
    po_30d:number
    open_po:number
    due_today:number
    overdue:number
  }
  operational_context:{
    finalized_po:number
    upcoming_open:number
    ordered_outers:number
    received_outers:number
    receipt_rate_pct:number
    outstanding_open_outers:number
    outstanding_open_lines:number
    nearest_open_due:string|null
    days_to_nearest_due:number|null
    open_supplier_count:number
  }
  open_suppliers:Array<{
    supplier_id:number
    supplier_name:string|null
    open_po_count:number
    ordered_outers:number
    received_outers:number
    outstanding_outers:number
    nearest_due:string|null
    otif_pct:number|null
    avg_delay_days:number|null
    historical_finalized_po_count:number
    historical_late_po_count:number
    at_risk_sku_count:number
    at_risk_units:number
    affected_order_links:number
  }>
  alert_summary:{active:number;critical:number;warning:number;info:number}
  latest_state_edit:string|null
}
export function fetchProcurementOverview():Promise<ProcurementOverview>{ return getJson('/api/procurement/overview') }

export type FulfillmentFilter =
  | 'all'
  | 'open'
  | 'upcoming'
  | 'completed'
  | 'overdue'
  | 'overdue_1_2'
  | 'overdue_3_7'
  | 'overdue_8_14'
  | 'overdue_15_plus'
  | 'due_today'
  | 'backorder'
export type FulfillmentListItem = {
  order_id:number; customer_id:number; customer_name:string; order_date:string; expected_delivery_date:string;
  is_undersupply_backordered:boolean; backorder_order_id:number|null; picking_completed_when:string|null;
  last_edited_when:string|null; refreshed_at?:string|null; risk_state:'completed'|'overdue'|'due_today'|'upcoming'; days_overdue:number;
  active_backorder:boolean; line_count:number; units_ordered:number; order_value:number; picked_lines:number;
  supply_exposed_sku_count:number; critical_supply_sku_count:number;
  linked_pre_inbound_shortfall_units:number; minimum_days_of_cover:number|null;
  exception_priority:'high'|'medium'|'low';
}
export type FulfillmentOrderLine = {
  order_line_key:string; stock_item_id:number; description:string; package_name:string|null; quantity:number; unit_price:number;
  total_excluding_tax:number; tax_amount:number; total_including_tax:number; picking_completed_when:string|null;
}
export type FulfillmentListResponse = { generated_at:string; as_of_date:string; status:FulfillmentFilter; search:string; count:number; page:number; page_size:number; total_pages:number; items:FulfillmentListItem[] }
export type FulfillmentDetailResponse = { generated_at:string; as_of_date:string; order:FulfillmentListItem; lines:FulfillmentOrderLine[] }
export function fetchFulfillmentList(status:FulfillmentFilter='open', page=1, pageSize=50, search=''):Promise<FulfillmentListResponse>{
  const q=new URLSearchParams({status,page:String(page),page_size:String(pageSize)})
  if(search.trim()) q.set('search',search.trim())
  return getJson(`/api/fulfillment/list?${q.toString()}`)
}
export function fetchFulfillmentDetail(orderId:number):Promise<FulfillmentDetailResponse>{ return getJson(`/api/fulfillment/${orderId}`) }

export type InventoryFilter = 'all' | 'risk' | 'negative' | 'out_of_stock' | 'reorder' | 'healthy'
export type InventoryListItem = {
  stock_item_id:number
  stock_item_name:string
  quantity_on_hand:number
  last_stocktake_quantity:number
  reorder_level:number
  typical_order_quantity:number
  last_edited_when:string|null
  refreshed_at:string|null
  stock_state:'negative'|'out_of_stock'|'reorder'|'healthy'
  below_reorder_by:number
  stocktake_delta:number
  open_demand_units:number
  demand_before_inbound_units:number
  incoming_units:number
  affected_orders:number
  earliest_demand_due:string|null
  next_inbound_date:string|null
  inbound_po_count:number
  outbound_units_30d:number
  days_of_cover:number|null
  days_to_next_inbound:number|null
  pre_inbound_balance:number
  projected_available:number
  pre_inbound_shortfall_units:number
  projected_shortfall_units:number
  coverage_state:string
  coverage_severity:'healthy'|'warning'|'critical'|string
}
export type InventoryListResponse = {
  generated_at:string
  status:InventoryFilter
  search:string
  count:number
  page:number
  page_size:number
  total_pages:number
  items:InventoryListItem[]
}
export type InventoryDetailResponse = { generated_at:string; item:InventoryListItem }
export function fetchInventoryList(status:InventoryFilter='reorder', page=1, pageSize=50, search=''):Promise<InventoryListResponse>{
  const q=new URLSearchParams({status,page:String(page),page_size:String(pageSize)})
  if(search.trim()) q.set('search',search.trim())
  return getJson(`/api/inventory/list?${q.toString()}`)
}
export function fetchInventoryDetail(stockItemId:number):Promise<InventoryDetailResponse>{ return getJson(`/api/inventory/${stockItemId}`) }

export type ProcurementFilter = 'all' | 'open' | 'upcoming' | 'finalized' | 'overdue' | 'due_today'
export type ProcurementListItem = {
  purchase_order_id:number
  supplier_id:number
  supplier_name:string|null
  order_date:string
  expected_delivery_date:string
  is_order_finalized:boolean
  ordered_outers:number
  received_outers:number
  outstanding_line_count:number
  last_edited_when:string|null
  refreshed_at:string|null
  outstanding_outers:number
  procurement_state:'overdue'|'due_today'|'awaiting_receipt'|'finalized'
  days_overdue:number
  days_until_due:number
  at_risk_sku_count:number
  at_risk_units:number
  affected_order_links:number
  supplier_otif_pct:number|null
  supplier_avg_delay_days:number|null
}
export type ProcurementLineItem = {
  purchase_order_line_key:string
  stock_item_id:number
  stock_item_name:string
  package_name:string|null
  ordered_outers:number
  ordered_quantity:number
  received_outers:number
  outstanding_outers:number
  is_order_finalized:boolean
  last_modified_when:string|null
}
export type ProcurementListResponse = {
  generated_at:string
  as_of_date:string
  status:ProcurementFilter
  search:string
  count:number
  page:number
  page_size:number
  total_pages:number
  items:ProcurementListItem[]
}
export type ProcurementDetailResponse = {
  generated_at:string
  as_of_date:string
  purchase_order:ProcurementListItem
  lines:ProcurementLineItem[]
}
export function fetchProcurementList(status:ProcurementFilter='open', page=1, pageSize=50, search=''):Promise<ProcurementListResponse>{
  const q=new URLSearchParams({status,page:String(page),page_size:String(pageSize)})
  if(search.trim()) q.set('search',search.trim())
  return getJson(`/api/procurement/list?${q.toString()}`)
}
export function fetchProcurementDetail(poId:number):Promise<ProcurementDetailResponse>{ return getJson(`/api/procurement/${poId}`) }

export type DeliveryListItem = {
  invoice_id:number
  order_id:number
  customer_id:number
  customer_name:string
  invoice_date:string
  expected_delivery_date:string|null
  confirmed_delivery_time:string|null
  confirmed_received_by:string|null
  delivery_run:string|null
  run_position:string|null
  last_edited_when:string|null
  refreshed_at:string|null
  returned_delivery_data:{Events?:Array<Record<string,unknown>>}|null
  latest_event:string|null
  latest_event_comment:string|null
  had_receiver_not_present:boolean
  delivery_state:'confirmed'|'overdue'|'due_today'|'pending'
  days_overdue:number
  days_until_due:number
  days_since_invoice:number
  order_date:string|null
  picking_completed_when:string|null
  lifecycle_gap_days:number|null
  lifecycle_coherent:boolean
}
export type DeliveryListResponse = {
  generated_at:string
  as_of_date:string
  status:
    | 'all'
    | 'pending'
    | 'upcoming'
    | 'confirmed'
    | 'receiver_not_present'
    | 'overdue'
    | 'overdue_1_2'
    | 'overdue_3_5'
    | 'overdue_6_10'
    | 'overdue_10_plus'
    | 'due_today'
  search:string
  count:number
  page:number
  page_size:number
  total_pages:number
  items:DeliveryListItem[]
}
export type DeliveryDetailResponse = {
  generated_at:string
  as_of_date:string
  delivery:DeliveryListItem
}
export function fetchDeliveryList(
  status:DeliveryListResponse['status']='pending',
  page=1,
  pageSize=50,
  search='',
):Promise<DeliveryListResponse>{
  const q=new URLSearchParams({status,page:String(page),page_size:String(pageSize)})
  if(search.trim()) q.set('search',search.trim())
  return getJson(`/api/delivery/list?${q.toString()}`)
}
export function fetchDeliveryDetail(invoiceId:number):Promise<DeliveryDetailResponse>{
  return getJson(`/api/delivery/${invoiceId}`)
}

export type ColdChainHistoryPoint = {
  recorded_when:string|null
  temperature:number
}

export type ColdChainOverview = {
  generated_at:string
  source_timezone:string
  latest_recorded_when:string|null
  kpis:{
    total_sensors:number
    coldroom_sensors:number
    vehicle_sensors:number
    fresh_sensors:number
    stale_sensors:number
    offline_sensors:number
    attention_sensors:number
    temperature_evaluated_sensors:number
    latest_age_seconds:number|null
  }
  sensor_groups:Array<{
    sensor_type:'coldroom'|'vehicle'|string
    sensor_count:number
    fresh_count:number
    stale_count:number
    offline_count:number
    attention_count:number
    latest_recorded_when:string|null
    stale_after_seconds:number
    offline_after_seconds:number
    temperature_thresholds_configured:boolean
  }>
  sensors:Array<{
    sensor_key:string
    sensor_type:'coldroom'|'vehicle'|string
    vehicle_registration:string|null
    sensor_number:number
    recorded_when:string|null
    temperature:number
    reading_count:number
    value_basis:string
    refreshed_at:string|null
    age_seconds:number|null
    freshness_state:'fresh'|'stale'|'offline'|'unknown'
    operational_state:'healthy'|'stale'|'offline'|'temperature_warning'|'temperature_critical'|'unknown'
    stale_after_seconds:number
    offline_after_seconds:number
    temperature_state:'normal'|'warning'|'critical'|'not_configured'
    temperature_thresholds_configured:boolean
    previous_temperature:number|null
    temperature_delta:number|null
    movement:'rising'|'falling'|'steady'
    history:ColdChainHistoryPoint[]
  }>
  alert_summary:{active:number;critical:number;warning:number;info:number}
  rules:Array<{
    rule_id:string
    description:string
    severity:string
    enabled:boolean
    source_native:boolean
    parameters:Record<string,unknown>
  }>
  monitoring:{
    freshness_status_source:string
    persisted_alerts_are_separate:boolean
    temperature_thresholds_configured:boolean
    history_window_hours:number
    history_points:number
  }
}

export function fetchColdChainOverview():Promise<ColdChainOverview>{
  return getJson('/api/cold-chain/overview')
}

export type AlertRulePatch = {
  enabled?:boolean
  severity?:'info'|'warning'|'critical'
  parameters?:Record<string,unknown>
  actor?:string
}

export async function patchAlertRule(
  ruleId:string,
  patch:AlertRulePatch,
):Promise<ColdChainOverview['rules'][number] & {updated_at:string|null}>{
  const response=await fetch(`${API_BASE}/api/alerts/rules/${encodeURIComponent(ruleId)}`,{
    method:'PATCH',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(patch),
  })
  if(!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json()
}

export type AnalyticsOverview = {
  generated_at:string
  frontier_cutoff:string|null
  as_of_date:string|null
  lookback_days:number
  current_period:{start_date:string|null;end_date:string|null}
  prior_period:{start_date:string|null;end_date:string|null}
  kpis:{
    invoices:number
    orders:number
    units:number
    revenue:number
    profit:number
    margin_pct:number
    prior_invoices:number
    prior_orders:number
    prior_units:number
    prior_revenue:number
    prior_profit:number
    prior_margin_pct:number
    revenue_change_pct:number|null
    profit_change_pct:number|null
    orders_change_pct:number|null
    units_change_pct:number|null
    margin_change_pp:number
  }
  trend_granularity:'day'|'week'|'month'
  trend:Array<{
    bucket_start:string
    revenue:number
    profit:number
    invoices:number
    is_partial:boolean
  }>
  customer_concentration:{
    top5_revenue_share_pct:number
    customers:Array<{
      customer_id:number
      customer_name:string
      revenue:number
      profit:number
      invoices:number
      revenue_share_pct:number
    }>
  }
  top_product_revenue_share_pct:number
  top_products:Array<{
    stock_item_id:number
    stock_item_name:string
    revenue:number
    profit:number
    units:number
    revenue_share_pct:number
  }>
  procurement:{
    ordered_outers:number
    received_outers:number
    po_count:number
    receipt_rate_pct:number
    receipt_rate_change_pp:number
    prior_receipt_rate_pct:number
    prior_ordered_outers:number
    prior_received_outers:number
    prior_po_count:number
  }
}
export function fetchAnalyticsOverview(lookbackDays=30):Promise<AnalyticsOverview>{
  const q=new URLSearchParams({lookback_days:String(lookbackDays)})
  return getJson(`/api/analytics/overview?${q.toString()}`)
}

export type AnalyticsDrilldownRow = {
  id?:number
  supplier_id?:number
  label?:string
  supplier_name?:string
  metric_value?:number
  revenue?:number
  profit?:number
  orders?:number
  units?:number
  ordered_outers?:number
  received_outers?:number
  outstanding_outers?:number
  purchase_orders?:number
  completion_pct?:number
  contribution_pct?:number
  contribution_basis?:string
}

export type AnalyticsDrilldown = {
  kind:'revenue'|'profit'|'orders'|'receipt'|'customer'|'product'
  title:string
  entity_id:number|null
  current_period:{start_date:string;end_date:string}
  prior_period:{start_date:string;end_date:string}
  trend_granularity:'day'|'week'|'month'
  trend:Array<{
    bucket_start:string
    revenue?:number
    profit?:number
    orders?:number
    units?:number
    ordered_outers?:number
    received_outers?:number
    purchase_orders?:number
    receipt_rate_pct?:number
    is_partial:boolean
  }>
  summary:Record<string,number>
  breakdowns:Array<{
    title:string
    entity_kind:'customer'|'product'|'supplier'
    rows:AnalyticsDrilldownRow[]
  }>
}

export function fetchAnalyticsDrilldown(
  kind:AnalyticsDrilldown['kind'],
  lookbackDays:number,
  entityId?:number,
):Promise<AnalyticsDrilldown>{
  const q=new URLSearchParams({
    kind,
    lookback_days:String(lookbackDays),
  })
  if(entityId!==undefined) q.set('entity_id',String(entityId))
  return getJson(`/api/analytics/drilldown?${q.toString()}`)
}

export type PlatformHealthOverview = {
  generated_at:string
  pipeline_cutoff:string|null
  source_frontier:string|null
  watermark_aligned:boolean
  pipelines:Array<{pipeline_name:string;last_successful_cutoff:string|null;last_successful_run_id:string|null;updated_at:string|null}>
  frontiers:Array<{source_name:string;safe_through_cutoff:string|null;basis:string|null;updated_at:string|null}>
  processing_guard:{singleton:boolean;mode:string|null;owner_run_id:string|null;acquired_at:string|null}
  alert_engine:{singleton:boolean;activated_at:string|null;backlog_policy:string|null;notes:string|null}
  freshness:{
    max_age_hours:number
    pipeline_age_hours:number|null
    frontier_age_hours:number|null
    quality_age_hours:number|null
    pipeline_fresh:boolean
    frontier_fresh:boolean
    quality_fresh:boolean
    all_fresh:boolean
  }
  latest_quality:{
    quality_run_id:string
    airflow_run_id:string
    mode:string
    status:string
    started_at:string|null
    finished_at:string|null
    passed_checks:number
    failed_checks:number
    warning_checks:number
    error_message:string|null
  }
  alerts:{
    active:number
    critical:number
    warning:number
    info:number
    platform_active:number
    platform_critical:number
  }
  realtime:{
    total_events:number
    events_24h:number
    processed_24h:number
    unprocessed:number
    avg_processing_lag_seconds:number
    max_processing_lag_seconds:number
    latest_event_at:string|null
    latest_processed_at:string|null
  }
  event_results:Array<{processing_result:string;event_count:number}>
}
export function fetchPlatformHealthOverview():Promise<PlatformHealthOverview>{
  return getJson('/api/platform-health/overview')
}

export type AdminOverview = {
  generated_at:string
  mode:string
  summary:{
    total_rules:number
    enabled_rules:number
    disabled_rules:number
    critical_rules:number
    warning_rules:number
    info_rules:number
    source_native_rules:number
  }
  domains:Array<{
    domain:string
    total_rules:number
    enabled_rules:number
    disabled_rules:number
    critical_rules:number
    warning_rules:number
    info_rules:number
  }>
  rules:Array<{
    rule_id:string
    domain:string
    description:string
    enabled:boolean
    severity:string
    source_native:boolean
    parameters:Record<string,unknown>
    updated_at:string|null
  }>
  alert_engine:{singleton:boolean;activated_at:string|null;backlog_policy:string|null;notes:string|null}
  processing_guard:{singleton:boolean;mode:string|null;owner_run_id:string|null;acquired_at:string|null}
  recent_changes:Array<{
    audit_id:number
    rule_id:string
    actor:string
    changed_at:string
    before_config:{enabled:boolean;severity:string;parameters:Record<string,unknown>}
    after_config:{enabled:boolean;severity:string;parameters:Record<string,unknown>}
    reevaluation_result:Record<string,unknown>
  }>
}
export function fetchAdminOverview():Promise<AdminOverview>{
  return getJson('/api/admin/overview')
}



export type WorkbenchMetric = {
  label:string
  value:string|number|boolean|null
  detail?:string|null
}

export type WorkbenchRelation = {
  domain:'Fulfillment'|'Delivery'|'Inventory'|'Procurement'|string
  entity_type:string
  entity_id:string
  label:string
  relationship:string
  status?:string|null
  detail?:string|null
}

export type WorkbenchTimelineEvent = {
  label:string
  timestamp:string|null
  detail?:string|null
  state:'observed'|'planned'|'current'|string
}

export type ExceptionWorkbench = {
  generated_at:string
  entity:{
    domain:string
    entity_type:string
    entity_id:string
    label:string
  }
  issue:{
    code:string
    title:string
    severity:'healthy'|'warning'|'critical'|string
    summary:string
  }
  impact:WorkbenchMetric[]
  evidence:WorkbenchMetric[]
  cause:{
    classification:string
    title:string
    explanation:string
    basis:string
  }
  related_records:WorkbenchRelation[]
  timeline:WorkbenchTimelineEvent[]
  projection?:Record<string,unknown>
  supply_evidence?:Array<Record<string,unknown>>
  supplier_performance?:Record<string,unknown>|null
  line_risk?:Array<Record<string,unknown>>
  cycle_time?:Record<string,unknown>
}

export function fetchFulfillmentWorkbench(orderId:number):Promise<ExceptionWorkbench>{
  return getJson(`/api/workbench/fulfillment/${orderId}`)
}

export function fetchDeliveryWorkbench(invoiceId:number):Promise<ExceptionWorkbench>{
  return getJson(`/api/workbench/delivery/${invoiceId}`)
}

export function fetchInventoryWorkbench(stockItemId:number):Promise<ExceptionWorkbench>{
  return getJson(`/api/workbench/inventory/${stockItemId}`)
}

export function fetchProcurementWorkbench(poId:number):Promise<ExceptionWorkbench>{
  return getJson(`/api/workbench/procurement/${poId}`)
}
