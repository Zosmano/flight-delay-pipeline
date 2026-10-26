-- On-time rate (DOT definition) for each carrier and month.
-- Denominator = all scheduled flights; cancelled and diverted count as not on time.
SELECT c.carrier_name,
       f.MONTH                                   AS month,
       COUNT(*)                                  AS scheduled_flights,
       SUM(f.ON_TIME)                            AS on_time_flights,
       ROUND(100.0 * SUM(f.ON_TIME) / COUNT(*), 2)  AS on_time_pct,
       ROUND(100.0 * SUM(f.CANCELLED) / COUNT(*), 2) AS cancelled_pct
FROM flights f
JOIN carriers c ON c.code = f.OP_UNIQUE_CARRIER
GROUP BY c.carrier_name, f.MONTH
ORDER BY c.carrier_name, f.MONTH;
