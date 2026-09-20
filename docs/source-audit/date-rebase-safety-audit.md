# 1 — Date Rebase Safety Audit

(audit complete; mutation not executed)

## Purpose

Assess whether the restored WideWorldImporters source can be deterministically rebased by +10 years before running the official WWI simulation.

## Verified findings

- WWI contains 175 date/time columns across the restored source.
- All 48 user tables contain at least one date/time column.
- 17 current tables are system-versioned temporal tables and 17 paired archive/history tables exist.
- Temporal current rows use `ValidTo = 9999-12-31 23:59:59.9999999` as the open-ended sentinel. This value must never be shifted.
- Temporal data totals 40,307 current rows plus 3,656,381 history rows.
- `Warehouse.ColdRoomTemperatures_Archive` alone contains 3,654,736 rows; `Warehouse.VehicleTemperatures` contains 65,998 rows.
- A literal all-table date rebase would potentially touch the full 4,713,833-row source and is therefore materially heavier than rebasing only the business chronology required by the portfolio.
- No user-table triggers are currently active.
- No date-related CHECK constraints were found.
- Operational `LastEditedWhen` defaults use `SYSDATETIME()`, which is appropriate for new post-rebase activity but means existing historical values must be treated deliberately.

## Temporal-table safety

The official WWI simulation already knows how to temporarily disable and re-enable system versioning. Its helper procedures explicitly turn `SYSTEM_VERSIONING` off, drop the `PERIOD FOR SYSTEM_TIME`, and later re-add the period and reactivate versioning with `DATA_CONSISTENCY_CHECK = ON`.

However, the official deactivation procedure also creates data-load triggers that write old versions into the archive tables on update. Therefore it must not be reused blindly for a one-time bulk date rebase, because doing so would create unwanted history rows while dates are being shifted.

A dedicated project rebase routine is required for the mutation step.

## Special temporal exception

`Application.Countries` contains one legitimate post-2016 temporal change:

- CountryID 222: `Turkey` -> `Türkiye`
- archive row ends at `2022-10-07 21:11:44.8930093`
- current row begins at the same 2022 timestamp

Blindly applying +10 years to this timestamp would move it to 2032 and put temporal metadata into the future. Blindly shifting only the 2013 side would also invert the archive interval. This pair therefore requires explicit exception handling.

## Simulation compatibility

`DataLoadSimulation.PopulateDataToCurrentDate` calculates:

- start date = `MAX(Sales.Orders.OrderDate) + 1 day`
- end date = yesterday according to SQL Server `SYSDATETIME()`

Therefore, if the business baseline is safely rebased so that `MAX(Sales.Orders.OrderDate) = 2026-05-31`, the first official simulation run will begin at 2026-06-01.

The generated WWI simulation logic contains several hard-coded 2013/2016 historical rules, but for dates after 2016 the main customer-order volume logic falls through to its later-year branch (`ELSE 1.26`) and sensor-recording logic remains active. The 2016-specific one-time events are already represented in the restored baseline (for example StockItemID 220-227 are present and the two 2016 SpecialDeals exist), so they do not need to be replayed.

## Conclusion

A +10-year business-date rebase is feasible, but a literal blanket `DATEADD(YEAR, 10, ...)` across every date/time value is not safe and is not the most efficient implementation.

The mutation step must:

1. rebase the business/operational chronology deterministically;
2. handle temporal current/history tables with system versioning disabled and consistency revalidated;
3. preserve the 9999 temporal sentinel;
4. explicitly handle the 2022 Turkey -> Türkiye temporal pair;
5. decide whether high-volume telemetry history is in rebase scope before touching 3.65M+ sensor-history rows;
6. verify row counts, PK/FK integrity, temporal consistency, and target max business dates after the mutation.

No source data was modified during source simulation-1.
