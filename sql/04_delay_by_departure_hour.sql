-- How delays build through the day: arrival delay and late-aircraft minutes by
-- scheduled departure hour (operated flights only).
SELECT DEP_HOUR                                        AS dep_hour,
       COUNT(*)                                        AS operated_flights,
       ROUND(100.0 * SUM(ON_TIME) / COUNT(*), 2)       AS on_time_pct,
       ROUND(AVG(ARR_DELAY), 2)                        AS mean_arr_delay_min,
       ROUND(AVG(COALESCE(LATE_AIRCRAFT_DELAY, 0)), 2) AS mean_late_aircraft_min,
       ROUND(AVG(COALESCE(CARRIER_DELAY, 0)), 2)       AS mean_carrier_min,
       ROUND(AVG(COALESCE(NAS_DELAY, 0)), 2)           AS mean_nas_min,
       ROUND(AVG(COALESCE(WEATHER_DELAY, 0)), 2)       AS mean_weather_min
FROM flights
WHERE OPERATED = 1
GROUP BY DEP_HOUR
ORDER BY DEP_HOUR;
