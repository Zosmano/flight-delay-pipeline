# Data quality report

Generated 2026-10-25.

## Files loaded

| File | Rows read | Rows loaded |
|---|---:|---:|
| T_ONTIME_REPORTING_Apr.csv | 597,919 | 597,919 |
| T_ONTIME_REPORTING_Feb.csv | 515,037 | 515,037 |
| T_ONTIME_REPORTING_Jan.csv | 544,003 | 544,003 |
| T_ONTIME_REPORTING_Jul.csv | 631,970 | 631,970 |
| T_ONTIME_REPORTING_Jun.csv | 607,577 | 607,577 |
| T_ONTIME_REPORTING_Mar.csv | 612,102 | 612,102 |
| T_ONTIME_REPORTING_May.csv | 611,735 | 611,734 |

Exact duplicate rows removed: **1**

## Checks on the loaded table

| Check | Result | Expected |
|---|---:|---|
| Total rows loaded | 4,120,342 | matches sum of files |
| Distinct carriers | 13 | 13 or fewer |
| Carrier codes missing from lookup | 0 | 0 |
| Distinct airports (origin) | 357 | informational |
| Cancelled flights | 92,611 | informational |
| Diverted flights | 13,072 | informational |
| Cancelled flights without a reason code | 0 | 0 |
| Cancelled flights with an arrival delay recorded | 0 | 0 |
| Operated flights missing arrival delay | 0 | 0 |
| Flights 15+ min late whose cause minutes do not sum to the arrival delay | 105 | near 0; flagged, not dropped (BTS reports causes for delays of 15+ min) |
| Rows missing tail number | 13,225 | informational (mostly cancellations) |
| Scheduled departure time outside 0001-2359 | 0 | 0 |

## Validation against published DOT figures

**96 of 96** published on-time rates (89 carrier-months and 7 monthly all-carrier totals) match Table 1A of the DOT Air Travel Consumer Report within the ±0.05-point rounding band. Full comparison: `outputs/tables/validation_vs_dot_atcr.csv`.

Largest differences:

| Month | Carrier | Published | Computed | Diff |
|---:|---|---:|---:|---:|
| 3 | ALASKA AIRLINES | 76.4 | 76.350 | -0.050 |
| 7 | REPUBLIC AIRWAYS | 68.1 | 68.051 | -0.049 |
| 7 | ALLEGIANT AIR | 68.6 | 68.552 | -0.048 |
| 1 | SKYWEST AIRLINES | 74.0 | 74.048 | +0.048 |
| 2 | JETBLUE AIRWAYS | 62.3 | 62.347 | +0.047 |
