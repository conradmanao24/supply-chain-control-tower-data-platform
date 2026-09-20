# Resolution-Adaptive Shell Fix

Date: 2026-09-17

## Problem observed

The shell looked acceptable on a ~1080p viewport but became visually underscaled on the user's larger/2K display: fixed-pixel sidebar, typography, controls, and a capped page container created a small UI island with excessive unused whitespace.

This was not true adaptive density. The implementation still behaved like a 1080p layout stretched over a larger workspace.

## Fix

The shell foundation now uses fluid desktop tokens and dimensions:

- `--sidebar-width: clamp(248px, 13vw, 320px)`
- fluid page gaps/padding/radii
- fluid brand, nav, icon, control, topbar, typography, profile, card, and shell-preview dimensions
- `page-container` changed from capped `1600px` layout to full available workspace width
- mobile behavior retained below 820px

The goal is comparable visual density across 1080p and 2K/large desktop viewports without relying on browser zoom.

## Scope

This fix changes only the shared business serving layer application shell foundation. No Control Tower business page or backend binding was added.
