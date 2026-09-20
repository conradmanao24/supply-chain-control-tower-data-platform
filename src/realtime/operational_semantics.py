from __future__ import annotations

import os

OPERATIONAL_WINDOW_DAYS = max(
    1,
    int(os.environ.get("CONTROL_TOWER_OPERATIONAL_WINDOW_DAYS", "30")),
)

DELIVERY_LIFECYCLE_MAX_DAYS = max(
    1,
    int(os.environ.get("DELIVERY_LIFECYCLE_MAX_DAYS", "180")),
)

SUPPLIER_PERFORMANCE_WINDOW_DAYS = max(
    30,
    int(os.environ.get("SUPPLIER_PERFORMANCE_WINDOW_DAYS", "180")),
)
