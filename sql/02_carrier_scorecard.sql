-- Jan-Jul scorecard per carrier: on-time, cancellations, and severe (3h+) delays.
SELECT c.carrier_name,
       COUNT(*)                                         AS scheduled_flights,
       ROUND(100.0 * SUM(f.ON_TIME)   / COUNT(*), 2)    AS on_time_pct,
       ROUND(100.0 * SUM(f.CANCELLED) / COUNT(*), 2)    AS cancelled_pct,
       ROUND(100.0 * SUM(f.DIVERTED)  / COUNT(*), 2)    AS diverted_pct,
       ROUND(10000.0 * SUM(f.SEVERE_DELAY) / SUM(f.OPERATED), 1) AS severe_delays_per_10k_operated,
       ROUND(AVG(CASE WHEN f.OPERATED = 1 THEN f.ARR_DELAY END), 1) AS mean_arr_delay_min
FROM flights f
JOIN carriers c ON c.code = f.OP_UNIQUE_CARRIER
GROUP BY c.carrier_name
ORDER BY on_time_pct DESC;
