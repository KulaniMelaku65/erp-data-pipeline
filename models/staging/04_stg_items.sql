DROP TABLE IF EXISTS stg_items;
CREATE TABLE stg_items AS
SELECT
    id                    AS item_id,
    number                AS item_no,
    TRIM(display_name)    AS item_name,
    type                  AS item_type,
    item_category_code    AS item_category,
    unit_cost,
    unit_price
FROM raw_items;
