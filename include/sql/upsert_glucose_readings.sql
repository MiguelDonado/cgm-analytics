-- Insert one reading unless a reading with the same factory_timestamp is
-- already stored (see docs/data-model.md).

INSERT INTO glucose_readings (
    factory_timestamp, local_timestamp, value_mg_dl,
    is_high, is_low, measurement_color, reading_type
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (factory_timestamp) DO NOTHING;