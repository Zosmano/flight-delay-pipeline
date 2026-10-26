-- Compact extract for a BI dashboard (Tableau / Power BI):
-- one row per month x carrier x origin airport.
SELECT f.MONTH AS month, c.carrier_name, f.ORIGIN AS origin_airport,
       f.ORIGIN_STATE_ABR AS origin_state,
       COUNT(*)            AS scheduled_flights,
       SUM(f.ON_TIME)      AS on_time_flights,
       SUM(f.CANCELLED)    AS cancelled_flights,
       SUM(f.DIVERTED)     AS diverted_flights,
       SUM(f.SEVERE_DELAY) AS severe_delays,
       ROUND(SUM(COALESCE(f.CARRIER_DELAY, 0)))       AS carrier_delay_min,
       ROUND(SUM(COALESCE(f.LATE_AIRCRAFT_DELAY, 0))) AS late_aircraft_delay_min,
       ROUND(SUM(COALESCE(f.NAS_DELAY, 0)))           AS nas_delay_min,
       ROUND(SUM(COALESCE(f.WEATHER_DELAY, 0)))       AS weather_delay_min,
       ROUND(SUM(COALESCE(f.SECURITY_DELAY, 0)))      AS security_delay_min
FROM flights f
JOIN carriers c ON c.code = f.OP_UNIQUE_CARRIER
GROUP BY f.MONTH, c.carrier_name, f.ORIGIN, f.ORIGIN_STATE_ABR;
