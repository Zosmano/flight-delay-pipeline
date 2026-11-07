-- Views the insight queries read. Derived fields are computed here, so adding an insight
-- never requires reloading the 4.1M flight rows.
DROP VIEW IF EXISTS flights_v;
CREATE VIEW flights_v AS
SELECT f.*,
       MIN(CAST(f.CRS_DEP_TIME / 100 AS INTEGER), 23)                      AS DEP_HOUR,
       CASE WHEN f.OPERATED = 1 AND f.ARR_DELAY >= 180 THEN 1 ELSE 0 END  AS SEVERE_DELAY
FROM flights f;
DROP VIEW IF EXISTS airports_v;
