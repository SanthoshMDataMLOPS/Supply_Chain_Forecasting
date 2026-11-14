-- Output table written by the inference pipeline. Created by Terraform; kept here for reference.
CREATE TABLE IF NOT EXISTS `ml.container_volume_forecasts` (
  dc_id               STRING    NOT NULL,
  forecast_date       DATE      NOT NULL,
  predicted_containers FLOAT64  NOT NULL,
  lower_bound         FLOAT64,
  upper_bound         FLOAT64,
  model_version       STRING,
  forecast_run_ts     TIMESTAMP NOT NULL
)
PARTITION BY forecast_date
CLUSTER BY dc_id;

CREATE TABLE IF NOT EXISTS `ml.model_monitoring` (
  run_ts        TIMESTAMP NOT NULL,
  model_version STRING,
  metric        STRING,     -- wape | mape | psi:<feature>
  dc_id         STRING,
  value         FLOAT64
)
PARTITION BY DATE(run_ts);
