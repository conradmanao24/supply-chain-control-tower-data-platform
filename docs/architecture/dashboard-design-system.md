# Dashboard Design System

Date: 2026-09-17

## Purpose

The application uses one shared visual system across Control Tower, Fulfillment, Delivery, Inventory, Procurement, Cold Chain, Analytics, Platform Health, and Admin.

The design system is implemented directly in the project frontend. No third-party dashboard template files or design-source packages are redistributed in this repository.

## Typography

Primary family: **Plus Jakarta Sans**.

Recommended hierarchy:

- page title: 24-28 px, 700
- section title: 16-18 px, 700
- card KPI: 24-32 px, 700
- body: 13-14 px, 500
- secondary/meta: 11-12 px, 500
- table body: 12-13 px, 500

## Color tokens

Primary accent:

- `accent`: `#FF4C4B`
- `accent_soft`: `#FFD2D2`
- `accent_pale`: `#FFE2E2`

Neutral system:

- `surface`: `#FFFFFF`
- `surface_subtle`: `#F7F7F8`
- `surface_muted`: `#F5F6F8`
- `border`: `#D9D9D9`
- `text_primary`: `#2D2E33`
- `text_muted`: `#969699`
- `sidebar_dark`: `#2D2E33`

Alert colors remain semantic and separate from the product accent.

## Shape and spacing

- card radius: 12 px
- compact control radius: 8 px
- primary page gap: 16 px
- compact internal gap: 8-12 px
- card padding: 16 px
- border: 1 px neutral where separation is needed
- shadows: subtle only

## Navigation

One navigation model is shared by all serving areas:

1. Control Tower
2. Fulfillment
3. Delivery
4. Inventory
5. Procurement
6. Cold Chain
7. Analytics
8. Platform Health
9. Admin

Typography, active state, icon style, spacing, and shell dimensions remain consistent across pages.

## Charts

- shared typography and tooltip treatment
- consistent axis and grid density
- red accent reserved for priority/current focus
- neutral series for secondary comparison
- flat chart backgrounds
- no decorative 3D treatment
- direct labels preferred when they reduce legend overhead

## Tables

Operational tables use:

- sticky headers where needed
- compact row height
- clear severity/status chips
- right-aligned numeric values
- consistent action placement
- internal scrolling when record volume exceeds the viewport

## Responsive behavior

Desktop is the primary operating surface.

Pages use adaptive density so normal operational views fit within the available viewport where possible. Scrolling is reserved for content that genuinely exceeds the available space, such as long exception lists.

## Realtime behavior

The frontend uses:

- REST for initial/current state
- SSE for operational updates and alerts
- PostgreSQL/dbt serving data for historical analytics

Realtime updates must not reset user filters or force full-page reloads.

## Consistency rules

- one typography system across all domains
- one card/radius/border system
- one navigation shell
- semantic alert colors separate from brand accent
- shared chart/table interaction patterns
- no duplicate dashboard-specific data pipeline

## Implementation order

The serving layer was implemented incrementally to keep validation bounded:

1. shared application shell and tokens
2. Control Tower
3. Fulfillment
4. Delivery
5. Inventory
6. Procurement
7. Cold Chain
8. Analytics
9. Platform Health
10. Admin
11. cross-page consistency and responsive validation
