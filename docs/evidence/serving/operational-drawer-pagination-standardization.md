# Operational Drill-down Drawer and Pagination Standardization

Date: 2026-09-18

## Scope

The same structural defect found in Fulfillment was audited across the operational domain pages.

Old behavior:
- clicking a table row appended record detail below the full list;
- users had to scroll to the bottom to find the selected record;
- Delivery, Inventory, and Procurement still used hard list limits instead of complete pagination;
- Delivery and Procurement still interpreted the exclusive source frontier as the business date.

## Implemented standard

The following pages now use the same right-side record drawer:
- Fulfillment
- Delivery
- Inventory
- Procurement

Clicking a record:
- keeps the filtered list and pagination in place;
- opens record detail immediately on the right;
- does not increase document height;
- can be closed without losing investigation context.

Shared component:
- frontend/src/RecordDetailDrawer.tsx

## Pagination

Server-side pagination is now standardized at 50 records/page for:
- Fulfillment
- Delivery
- Inventory
- Procurement

No operational list is silently truncated by a UI hard limit.

Current verified examples:
- Fulfillment overdue: 154 records / 4 pages
- Delivery all 30d: 2,000 records / 40 pages
- Inventory: 227 records / 5 pages
- Procurement: 50 records / 1 page

## Frontier semantics

Delivery and Procurement now use the same exclusive-cutoff rule as Control Tower and Fulfillment:

business_date = safe_through_cutoff - 1 day

Current verified business date: 2026-09-18

Control Tower and domain counts now agree:
- Delivery pending: 84
- Delivery overdue: 5
- Delivery due today: 1
- Procurement under-received: 2
- Procurement overdue: 0
- Procurement due today: 0

## Browser validation

1920x1080 and 2560x1440:
- Control Tower -> Fulfillment overdue preserves Overdue filter and 154 count;
- Fulfillment row -> right-side Order drawer;
- Delivery row -> right-side Invoice drawer;
- Inventory row -> right-side Stock-item drawer;
- Procurement row -> right-side PO drawer;
- opening drawers does not change page document height;
- horizontal overflow: none;
- browser runtime errors: 0.

Operational tables use an internal scroll region with sticky table headers so record investigation no longer extends the page by dozens of rows.

This checkpoint preceded the final application validation.
