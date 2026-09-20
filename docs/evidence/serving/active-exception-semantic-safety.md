# Active Exception Semantic Safety Audit

Date: 2026-09-18

## Scope

The business-facing `What happened` content in Active Exceptions was moved out of frontend rule-name heuristics and into a deterministic backend explanation contract.

## Safety model

`src/realtime/alert_explanations.py` now:

- reads the stored `observed_value` and `threshold_value` for each alert;
- re-checks the same factual condition used by the alert evaluator;
- only emits a business-facing sentence when the stored evidence independently satisfies that condition;
- otherwise fails closed with an evidence-incomplete message instead of inventing a business explanation;
- returns normalized business evidence separately from raw technical evidence.

The frontend no longer constructs `What happened` from rule IDs.

## Current active-alert audit

Live audit of all active/open+acknowledged alerts:

- total active alert signals: 286
- evidence verified: 286
- unverified/fallback: 0

Breakdown:

- delivery.due_today: 4 / 4 verified
- delivery.overdue: 18 / 18 verified
- delivery.receiver_not_present: 16 / 16 verified
- fulfillment.backorder: 232 / 232 verified
- fulfillment.due_today: 3 / 3 verified
- fulfillment.overdue: 6 / 6 verified
- inventory.reorder: 6 / 6 verified
- inventory.target_watch: 1 / 1 verified

Current approved business-facing explanations therefore have stored evidence support for every active alert signal.

Unknown, unsupported, incomplete, or non-normalized future payloads do not receive an inferred explanation; they fall back to a safe evidence-incomplete statement.

## UI changes

The exception detail drawer now:

- shows each active signal's backend-verified `What happened`;
- marks verified explanations as `Evidence verified`;
- uses backend-returned `Why this needs attention`;
- uses backend-normalized business evidence;
- keeps raw observed/threshold payloads under expandable `Technical evidence`.

## Header defect fixed

The previous collision:

`Back to Control TowerEXCEPTION INVESTIGATION`

was replaced by a proper breadcrumb row:

`Back to Control Tower / Exception investigation`

with explicit flex layout and spacing.

## Validation

- frontend production build: PASS
- browser runtime errors at 1920x1080: 0
- browser runtime errors at 2560x1440: 0
- exception page horizontal overflow: none
- 1920x1080 page height: fits viewport
- 2560x1440 page height: fits viewport
- Invoice #308184 renders two verified explanations:
  - Receiver Not Present
  - Due Today

This checkpoint preceded the final application validation.
