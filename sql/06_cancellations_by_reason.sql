-- Cancellations by month and reason (BTS codes A-D).
SELECT f.MONTH AS month, r.Description AS reason, COUNT(*) AS cancelled_flights
FROM flights_v f
JOIN lkp_cancellation r ON r.Code = f.CANCELLATION_CODE
WHERE f.CANCELLED = 1
GROUP BY f.MONTH, r.Description
ORDER BY f.MONTH, r.Description;
