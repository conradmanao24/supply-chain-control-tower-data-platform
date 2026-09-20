# Functional Drill-Down Standard

Purpose: ensure every dashboard summary can be traced to the records that create it.

## Global rules

1. Every operational KPI or domain status that represents a count/exposure must be actionable.
2. Clicking a KPI must open the owning domain page with the relevant filter already applied.
3. Domain pages must provide a full filtered list, not only a priority shortlist.
4. Clicking a list row must open record-level detail.
5. Record detail must show the factual reason/evidence behind the current state.
6. If the source does not contain a specific business reason, the dashboard must say exactly what is known instead of inventing a reason.
7. Priority tables are allowed as shortcuts, but never replace the full list.
8. Navigation must preserve investigation context where practical.
9. Operational data freshness must remain visible while investigating.
10. Platform/admin details must not interrupt the operational investigation flow.

## First pilot flow

Control Tower:
`Delivery pending`
→ Delivery page with `pending` filter
→ full pending-delivery list
→ click invoice
→ delivery detail with event/reason evidence.

This pilot becomes the reusable pattern for Fulfillment, Inventory, Procurement, Cold Chain, and Exceptions.
