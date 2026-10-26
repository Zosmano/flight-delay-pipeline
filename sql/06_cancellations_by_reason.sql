-- Cancellations by month and reason (BTS codes A-D).
SELECT f.MONTH AS month, r.reason, COUNT(*) AS cancelled_flights
FROM flights f
JOIN cancellation_reasons r ON r.code = f.CANCELLATION_CODE
WHERE f.CANCELLED = 1
GROUP BY f.MONTH, r.reason
ORDER BY f.MONTH, r.reason;
