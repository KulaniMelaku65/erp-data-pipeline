-- Customers with cleaned names, upper-case ISO country codes and lower-case emails.
DROP TABLE IF EXISTS stg_customers;
CREATE TABLE stg_customers AS
SELECT
    id                       AS customer_id,
    number                   AS customer_no,
    TRIM(display_name)       AS customer_name,
    type                     AS customer_type,
    TRIM(city)               AS city,
    UPPER(TRIM(country))     AS country_code,
    LOWER(TRIM(email))       AS email
FROM raw_customers;
