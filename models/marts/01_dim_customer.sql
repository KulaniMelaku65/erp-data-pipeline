DROP TABLE IF EXISTS dim_customer;
CREATE TABLE dim_customer AS
SELECT customer_id, customer_no, customer_name, customer_type, city, country_code, email
FROM stg_customers;
