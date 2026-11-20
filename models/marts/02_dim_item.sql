DROP TABLE IF EXISTS dim_item;
CREATE TABLE dim_item AS
SELECT item_id, item_no, item_name, item_category, unit_cost, unit_price
FROM stg_items;
