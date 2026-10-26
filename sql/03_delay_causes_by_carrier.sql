-- Where delay minutes come from. BTS splits every arrival delay of 15+ minutes into
-- five causes. "Carrier" and "late aircraft" are largely within an airline's control;
-- weather, National Air System (NAS) and security mostly are not.
SELECT c.carrier_name,
       ROUND(SUM(COALESCE(f.CARRIER_DELAY, 0)))       AS carrier_min,
       ROUND(SUM(COALESCE(f.LATE_AIRCRAFT_DELAY, 0))) AS late_aircraft_min,
       ROUND(SUM(COALESCE(f.NAS_DELAY, 0)))           AS nas_min,
       ROUND(SUM(COALESCE(f.WEATHER_DELAY, 0)))       AS weather_min,
       ROUND(SUM(COALESCE(f.SECURITY_DELAY, 0)))      AS security_min,
       COUNT(*)                                        AS scheduled_flights
FROM flights f
JOIN carriers c ON c.code = f.OP_UNIQUE_CARRIER
GROUP BY c.carrier_name;
