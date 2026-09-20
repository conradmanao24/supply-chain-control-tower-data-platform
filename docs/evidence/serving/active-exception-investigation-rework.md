# Active Exception Investigation Rework

Date: 2026-09-18

## Scope

Control Tower Active Exceptions was reworked from a debug-style alert table into a business-record investigation workflow.

## Problems corrected

- raw alert count was presented like a count of unique business problems;
- UI fetched only 200 active alerts even when more existed;
- the alert table was appended below the Control Tower;
- selected alert detail was rendered below the long table;
- raw JSON was the primary investigation content;
- duplicate alerts for the same invoice/order/item appeared as independent cases.

## Implemented behavior

### Summary semantics

Control Tower now distinguishes:

- affected records — distinct business records with active alerts;
- alert signals — individual active rule matches.

Current verified values:

- 261 affected records;
- 286 active alert signals;
- 0 critical;
- 285 warning;
- 1 info.

### Exception workspace

Investigate exceptions opens a dedicated Control Tower workspace rather than appending a table under the page.

The workspace provides:

- server-side pagination, 50 business records per page;
- complete access to all matching records;
- search;
- domain filter;
- severity filter;
- status filter;
- grouping by business record;
- active signal count/reasons per record.

Verified API example:

- total cases: 261;
- page size: 50;
- total pages: 6;
- delivery filter: 22 affected records;
- warning filter: 260 affected records;
- search 308184: 1 invoice case with 2 active signals.

### Business-readable case detail

Selecting a case opens a right-side investigation drawer.

The drawer prioritizes:

1. What happened
2. Why this needs attention
3. Active signals
4. Business evidence
5. Link to the owning business record

Raw JSON remains available only under expandable Technical evidence.

Example verified case:

- invoice 308184;
- 2 active signals;
- delivery.receiver_not_present;
- delivery.due_today;
- latest delivery attempt includes Receiver not present business evidence.

## Backend

New endpoints:

- GET /api/control-tower/exception-cases
- GET /api/control-tower/exception-cases/{entity_type}/{entity_id}

Control Tower overview alert summary now includes affected_records.

## Frontend

New component:

- frontend/src/ExceptionInvestigationPage.tsx

Control Tower now routes to that workspace when exception investigation is opened.

The old appended 200-row exception table was removed from the Control Tower component.

## Validation

- backend case count: PASS;
- grouping by entity: PASS;
- server-side pagination: PASS;
- search/filter checks: PASS;
- frontend production build: PASS;
- existing Control Tower summary preserved.

This checkpoint preceded the final application validation.
