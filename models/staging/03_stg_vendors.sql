DROP TABLE IF EXISTS stg_vendors;
CREATE TABLE stg_vendors AS
SELECT
    id                    AS vendor_id,
    number                AS vendor_no,
    TRIM(display_name)    AS vendor_name,
    UPPER(TRIM(country))  AS country_code
FROM raw_vendors;
