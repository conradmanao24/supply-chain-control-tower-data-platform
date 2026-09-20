# Fulfillment Overdue Cutoff and Pagination Fix

Date: 2026-09-18

## Problem

Control Tower correctly showed 154 fulfillment overdue orders using business data through 2026-09-18, but the Fulfillment API interpreted the exclusive source frontier (2026-09-19 00:00) as the business date. That produced:

- Control Tower overdue: 154
- Fulfillment overdue: 150
- Fulfillment due today: 0

The Fulfillment list also used a hard limit instead of server-side pagination.

## Fix

Fulfillment now derives business date as:

safe_through_cutoff - 1 day

The 30-day operational scope includes the business-through date.

The Control Tower fulfillment scope was aligned to the same date semantics.

The Fulfillment list endpoint now uses server-side pagination:

- page
- page_size
- count
- total_pages

Default page size is 50.

## Verified current state

Business date: 2026-09-18

Control Tower:
- open: 164
- overdue: 154
- due today: 3
- backorders: 164

Fulfillment overview:
- open: 164
- overdue: 154
- due today: 3
- backorders: 164

Fulfillment overdue list:
- total: 154
- page 1: 50 rows
- page 2: 50 rows
- page 4: 4 rows
- total pages: 4

Browser drill-down from Control Tower:
- card: Fulfillment overdue 154
- opens Fulfillment with Overdue filter
- list header: Overdue orders / 154
- pagination: Showing 1-50 of 154
- next page: Showing 51-100 of 154
- browser errors: 0

Order detail also uses the same 2026-09-18 business date.

This checkpoint preceded the final application validation.
