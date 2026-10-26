-- Departure performance at each origin airport with 20,000+ scheduled departures.
-- Counts are returned so the analysis step can attach 95% Wilson intervals.
SELECT f.ORIGIN                                       AS airport,
       MIN(f.ORIGIN_CITY_NAME)                        AS city,
       COUNT(*)                                       AS scheduled_departures,
       SUM(CASE WHEN f.CANCELLED = 0 AND f.DEP_DELAY < 15 THEN 1 ELSE 0 END) AS on_time_departures,
       SUM(f.CANCELLED)                               AS cancelled,
       ROUND(AVG(CASE WHEN f.CANCELLED = 0 THEN f.DEP_DELAY END), 1) AS mean_dep_delay_min
FROM flights f
GROUP BY f.ORIGIN
HAVING COUNT(*) >= 20000
ORDER BY scheduled_departures DESC;
